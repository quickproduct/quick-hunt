from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, validate_choice, clamp

_VALID_MODES = {"turbo", "normal", "economy"}
_VALID_WORKERS = {
    "scraping_bulk", "scraping_realtime", "enrichment", "maintenance",
    "cover_bulk", "cover_ranking", "cover_generation", "cover_workflow",
    "email", "cover_batch",
}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_queue_depths() -> str:
        """
        Show message counts and consumer counts for every RabbitMQ queue
        (jh_scraping_bulk, jh_cover_letter_*, jh_email_*, etc.).
        High message count + low consumers = backlog worth investigating.
        """
        data = await api("GET", "/admin/queues", cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_worker_live_status() -> str:
        """
        Query the live Celery inspect API to see which workers are online,
        what tasks they are currently executing, and their active/reserved queues.
        """
        data = await api("GET", "/admin/workers/live-status", timeout="long")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_worker_events(limit: int = 50) -> str:
        """
        Fetch recent Celery task events (task-started, task-succeeded,
        task-failed, worker-heartbeat) stored in Redis.

        limit: number of events to return, 1-200 (default: 50)
        """
        limit = clamp(limit, 1, 200)
        data = await api("GET", "/admin/workers/events", params={"limit": limit}, cache_ttl=5)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def detect_dead_workers() -> str:
        """
        Find Celery workers whose heartbeats are more than 120 seconds old -
        these are likely crashed or stuck. Returns worker hostname and how long
        ago the last heartbeat was received.
        """
        data = await api("GET", "/admin/workers/dead", cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_performance_mode() -> str:
        """
        Show the active worker performance preset: turbo (max throughput),
        normal (balanced), or economy (low resource usage).
        """
        data = await api("GET", "/admin/workers/performance-mode", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def set_performance_mode(mode: str) -> str:
        """
        Apply a performance preset to all workers at once.

        mode: 'turbo' | 'normal' | 'economy'
          turbo   - max scale + concurrency for all workers
          economy - minimum scale, suitable for low-traffic periods
          normal  - balanced defaults
        """
        err = validate_choice(mode, _VALID_MODES, "mode")
        if err:
            return err
        data = await api(
            "POST", "/admin/workers/performance-mode",
            json={"mode": mode.strip().lower()},
            invalidate_cache=True,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def pause_worker(service: str) -> str:
        """
        Stop a worker from consuming new tasks from its queues (in-flight
        tasks finish normally). Useful for draining a worker before debugging.

        service: worker service name, e.g. 'enrichment', 'cover_generation'
        """
        data = await api("POST", "/admin/workers/pause", json={"service": service.strip()})
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def resume_worker(service: str) -> str:
        """
        Re-enable a previously paused worker so it starts consuming queues again.

        service: worker service name, e.g. 'enrichment', 'cover_generation'
        """
        data = await api("POST", "/admin/workers/resume", json={"service": service.strip()})
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def restart_workers(service: str = "") -> str:
        """
        Restart one or all Celery worker pool(s).

        service: specific worker name to restart (e.g. 'enrichment'), or leave
                 empty to restart all workers at once.
        """
        body: dict = {}
        if service.strip():
            body["service"] = service.strip()
        data = await api("POST", "/admin/workers/restart", json=body, timeout="long")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def scale_worker(worker: str, scale: int, concurrency: int) -> str:
        """
        Update the scale (number of replicas) and concurrency (threads per
        replica) for a specific worker in worker.config.yml.

        worker:      one of: scraping_bulk, scraping_realtime, enrichment,
                     maintenance, cover_bulk, cover_ranking, cover_generation,
                     cover_workflow, email, cover_batch
        scale:       number of container replicas (1-10)
        concurrency: number of concurrent tasks per replica (1-8)
        """
        err = validate_choice(worker, _VALID_WORKERS, "worker")
        if err:
            return err
        scale = clamp(scale, 1, 10)
        concurrency = clamp(concurrency, 1, 8)
        data = await api(
            "PUT", "/admin/workers/scale",
            json={"worker": worker.strip().lower(), "scale": scale, "concurrency": concurrency},
            invalidate_cache=True,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def rollback_worker_config() -> str:
        """
        Restore the worker configuration from the last snapshot saved in Redis
        (taken automatically before any scale/performance-mode change).
        Use this to undo an accidental config change.
        """
        data = await api("POST", "/admin/workers/rollback", invalidate_cache=True)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_worker_config() -> str:
        """
        Read the current worker.config.yml showing scale, concurrency, and
        queue assignments for every worker.
        """
        data = await api("GET", "/admin/workers/config", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_autoscale_status() -> str:
        """
        Check whether the auto-scaler is enabled or disabled, and view recent
        scaling decisions.
        """
        data = await api("GET", "/admin/autoscale/status", cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def toggle_autoscale(enabled: bool) -> str:
        """
        Enable or disable the auto-scaler that automatically adjusts worker
        scale based on queue backlog.

        enabled: true to enable, false to disable
        """
        data = await api("POST", "/admin/autoscale/toggle", json={"enabled": enabled})
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def trigger_autoscale_check() -> str:
        """
        Trigger an immediate auto-scale check that evaluates queue depths and
        adjusts worker replicas if needed.
        """
        data = await api("POST", "/admin/autoscale/check", timeout="long")
        return fmt(data)
