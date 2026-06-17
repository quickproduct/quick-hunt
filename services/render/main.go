// render-svc — a bounded HTTP fetch/render service for the job scraper.
//
// It replaces the in-Python Playwright/Chromium with one Go process that owns a
// single shared headless Chrome and a fixed pool of tabs. Python adapters call
// POST /fetch and keep all their parsing/selectors — this service only fetches
// HTML (plain HTTP first, browser fallback), so the heavy, unbounded per-pod
// Chromium footprint collapses into one tightly-bounded service.
//
// Contract mirrors base_adapter._get_page_html / _get_page_html_http:
//
//	POST /fetch  {url, wait_selector?, http_first, content_marker?, block_assets, timeout_ms?}
//	          -> {html, via:"http"|"browser", status, elapsed_ms, error?}
//	GET  /healthz -> 200 "ok"
package main

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/cdproto/cdp"
	"github.com/chromedp/cdproto/fetch"
	"github.com/chromedp/cdproto/network"
	"github.com/chromedp/chromedp"
)

const minHTMLBytes = 2048

const userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
	"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

// Resource types and analytics hosts that never contribute job content — the
// same set base_adapter blocks, so render parity holds.
var blockedResourceTypes = map[network.ResourceType]bool{
	network.ResourceTypeImage:      true,
	network.ResourceTypeMedia:      true,
	network.ResourceTypeFont:       true,
	network.ResourceTypeStylesheet: true,
}

var blockedHostFragments = []string{
	"googletagmanager.com", "google-analytics.com", "doubleclick.net",
	"googlesyndication.com", "adsystem.com", "connect.facebook.net",
	"facebook.com/tr", "hotjar.com", "segment.com", "segment.io",
	"newrelic.com", "nr-data.net", "sentry-cdn.com", "fullstory.com",
	"clarity.ms", "mixpanel.com", "amplitude.com", "criteo.com",
	"scorecardresearch.com", "quantserve.com",
}

// Chromium flags mirror base_adapter._LAUNCH_ARGS (container-optimized, capped
// JS heap, no /dev/shm). --single-process/--no-zygote are deliberately absent.
var chromeFlags = []chromedp.ExecAllocatorOption{
	chromedp.NoSandbox,
	chromedp.DisableGPU,
	chromedp.Flag("disable-dev-shm-usage", true),
	chromedp.Flag("disable-setuid-sandbox", true),
	chromedp.Flag("disable-software-rasterizer", true),
	chromedp.Flag("blink-settings", "imagesEnabled=false"),
	chromedp.Flag("disable-extensions", true),
	chromedp.Flag("disable-background-networking", true),
	chromedp.Flag("disable-background-timer-throttling", true),
	chromedp.Flag("disable-default-apps", true),
	chromedp.Flag("disable-sync", true),
	chromedp.Flag("disable-translate", true),
	chromedp.Flag("mute-audio", true),
	chromedp.Flag("no-first-run", true),
	chromedp.Flag("metrics-recording-only", true),
	chromedp.Flag("js-flags", "--max-old-space-size=256"),
	chromedp.Flag("headless", true),
	chromedp.UserAgent(userAgent),
}

type fetchRequest struct {
	URL           string `json:"url"`
	WaitSelector  string `json:"wait_selector"`
	HTTPFirst     bool   `json:"http_first"`
	ContentMarker string `json:"content_marker"`
	BlockAssets   bool   `json:"block_assets"`
	TimeoutMS     int    `json:"timeout_ms"`
}

type fetchResponse struct {
	HTML      string `json:"html"`
	Via       string `json:"via"`
	Status    int    `json:"status"`
	ElapsedMS int64  `json:"elapsed_ms"`
	Error     string `json:"error,omitempty"`
}

type server struct {
	allocCtx   context.Context
	sem        chan struct{} // bounds concurrent tabs
	httpClient *http.Client
	navTimeout time.Duration
}

func hostBlocked(rawURL string) bool {
	for _, frag := range blockedHostFragments {
		if strings.Contains(rawURL, frag) {
			return true
		}
	}
	return false
}

// tryHTTP fetches the page with a plain HTTP GET. Returns ok=false when the
// response doesn't look like a usable page so the caller falls back to a browser.
func (s *server) tryHTTP(ctx context.Context, url, marker string) (string, int, bool) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", 0, false
	}
	req.Header.Set("User-Agent", userAgent)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return "", 0, false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", resp.StatusCode, false
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 5<<20)) // 5 MiB cap
	if err != nil {
		return "", resp.StatusCode, false
	}
	html := string(body)
	if len(html) < minHTMLBytes {
		return "", resp.StatusCode, false
	}
	if marker != "" && !strings.Contains(html, marker) {
		return "", resp.StatusCode, false
	}
	return html, resp.StatusCode, true
}

// renderBrowser fetches the page through the shared Chrome, under the tab
// semaphore. Optionally aborts heavy assets and analytics via the Fetch domain.
func (s *server) renderBrowser(parent context.Context, req fetchRequest) (string, error) {
	s.sem <- struct{}{}
	defer func() { <-s.sem }()

	tabCtx, cancelTab := chromedp.NewContext(s.allocCtx)
	defer cancelTab()

	timeout := s.navTimeout
	if req.TimeoutMS > 0 {
		timeout = time.Duration(req.TimeoutMS) * time.Millisecond
	}
	ctx, cancel := context.WithTimeout(tabCtx, timeout)
	defer cancel()

	if req.BlockAssets {
		chromedp.ListenTarget(ctx, func(ev interface{}) {
			paused, ok := ev.(*fetch.EventRequestPaused)
			if !ok {
				return
			}
			go func() {
				c := chromedp.FromContext(ctx)
				exec := cdp.WithExecutor(ctx, c.Target)
				if blockedResourceTypes[paused.ResourceType] || hostBlocked(paused.Request.URL) {
					_ = fetch.FailRequest(paused.RequestID, network.ErrorReasonBlockedByClient).Do(exec)
					return
				}
				_ = fetch.ContinueRequest(paused.RequestID).Do(exec)
			}()
		})
		if err := chromedp.Run(ctx, fetch.Enable()); err != nil {
			return "", err
		}
	}

	if err := chromedp.Run(ctx, chromedp.Navigate(req.URL)); err != nil {
		return "", err
	}

	// Best-effort wait for the content selector — a timeout here is fine
	// (mirrors base_adapter logging a wait_selector_timeout but still parsing).
	if req.WaitSelector != "" {
		wctx, wcancel := context.WithTimeout(ctx, 5*time.Second)
		_ = chromedp.Run(wctx, chromedp.WaitReady(req.WaitSelector, chromedp.ByQuery))
		wcancel()
	}

	var html string
	if err := chromedp.Run(ctx, chromedp.OuterHTML("html", &html, chromedp.ByQuery)); err != nil {
		return "", err
	}
	return html, nil
}

func (s *server) handleFetch(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var req fetchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.URL == "" {
		writeJSON(w, http.StatusBadRequest, fetchResponse{Error: "invalid request body"})
		return
	}

	resp := fetchResponse{}

	if req.HTTPFirst {
		if html, status, ok := s.tryHTTP(r.Context(), req.URL, req.ContentMarker); ok {
			resp.HTML, resp.Via, resp.Status = html, "http", status
			resp.ElapsedMS = time.Since(start).Milliseconds()
			writeJSON(w, http.StatusOK, resp)
			return
		}
	}

	html, err := s.renderBrowser(r.Context(), req)
	if err != nil {
		resp.Error = err.Error()
		resp.ElapsedMS = time.Since(start).Milliseconds()
		writeJSON(w, http.StatusBadGateway, resp)
		return
	}
	resp.HTML, resp.Via, resp.Status = html, "browser", http.StatusOK
	resp.ElapsedMS = time.Since(start).Milliseconds()
	writeJSON(w, http.StatusOK, resp)
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func main() {
	maxTabs := envInt("RENDER_MAX_TABS", 3)
	navTimeoutMS := envInt("RENDER_NAV_TIMEOUT_MS", 45000)
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	// One shared Chrome process for the lifetime of the service.
	opts := chromeFlags
	if p := os.Getenv("RENDER_CHROME_PATH"); p != "" {
		opts = append(opts, chromedp.ExecPath(p))
	}
	allocCtx, cancelAlloc := chromedp.NewExecAllocator(context.Background(), opts...)
	defer cancelAlloc()
	// Warm the browser in the background so the HTTP server (and the /healthz
	// readiness probe) come up immediately even if Chrome is slow to launch.
	warmCtx, cancelWarm := chromedp.NewContext(allocCtx)
	go func() {
		if err := chromedp.Run(warmCtx); err != nil {
			log.Printf("warning: browser warm-up failed: %v", err)
		}
	}()

	s := &server{
		allocCtx:   allocCtx,
		sem:        make(chan struct{}, maxTabs),
		httpClient: &http.Client{Timeout: 20 * time.Second},
		navTimeout: time.Duration(navTimeoutMS) * time.Millisecond,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/fetch", s.handleFetch)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, "ok")
	})

	srv := &http.Server{Addr: ":" + port, Handler: mux}
	var once sync.Once
	shutdown := func() {
		once.Do(func() {
			cancelWarm()
			ctx, c := context.WithTimeout(context.Background(), 5*time.Second)
			defer c()
			_ = srv.Shutdown(ctx)
		})
	}
	defer shutdown()

	log.Printf("render-svc listening on :%s (max_tabs=%d, nav_timeout=%dms)", port, maxTabs, navTimeoutMS)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server error: %v", err)
	}
}
