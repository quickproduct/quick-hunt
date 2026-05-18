from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, validate_choice

_VALID_PORTALS = {
    "naukri", "indeed", "shine", "internshala",
    "remoteok", "weworkremotely", "workingnomads", "jobspresso",
}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_features() -> str:
        """
        Read all runtime feature flags currently active: auto_send_enabled,
        langchain_enabled, semantic_filter_enabled, score_threshold.
        These are stored in Redis and take effect immediately when changed.
        """
        data = await api("GET", "/admin/features", cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def update_features(
        auto_send_enabled: bool | None = None,
        langchain_enabled: bool | None = None,
        semantic_filter_enabled: bool | None = None,
        score_threshold: float | None = None,
    ) -> str:
        """
        Update one or more runtime feature flags. Only pass the flags you want
        to change - omit the rest to leave them unchanged.

        auto_send_enabled:       allow automatic email sending without manual approval
        langchain_enabled:       use LangChain for cover letter generation (vs fallback template)
        semantic_filter_enabled: use vector similarity to pre-filter jobs before scoring
        score_threshold:         minimum relevance score (0.0-1.0) for a job to be processed
        """
        updates: dict = {}
        if auto_send_enabled is not None:
            updates["auto_send_enabled"] = auto_send_enabled
        if langchain_enabled is not None:
            updates["langchain_enabled"] = langchain_enabled
        if semantic_filter_enabled is not None:
            updates["semantic_filter_enabled"] = semantic_filter_enabled
        if score_threshold is not None:
            if not (0.0 <= score_threshold <= 1.0):
                return "score_threshold must be between 0.0 and 1.0"
            updates["score_threshold"] = score_threshold
        if not updates:
            return "No flags provided. Pass at least one flag to update."
        data = await api(
            "PUT", "/admin/features", json=updates,
            invalidate_cache=True,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_portals() -> str:
        """
        List all job portal scrapers with their enabled/disabled status.
        Portals: naukri, indeed, shine, internshala, remoteok,
                 weworkremotely, workingnomads, jobspresso.
        """
        data = await api("GET", "/admin/portals", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def toggle_portal(portal: str, enabled: bool) -> str:
        """
        Enable or disable a specific job portal scraper.

        portal:  one of naukri, indeed, shine, internshala, remoteok,
                 weworkremotely, workingnomads, jobspresso
        enabled: true to enable, false to disable
        """
        err = validate_choice(portal, _VALID_PORTALS, "portal")
        if err:
            return err
        data = await api(
            "PUT", f"/admin/portals/{portal.strip().lower()}/toggle",
            json={"enabled": enabled},
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_scrape_filter() -> str:
        """
        Read the current scraping date-filter settings:
        max_job_age_days — how old a job posting can be before it's rejected,
        strict_date_mode — when true, jobs with unparseable dates are also rejected.
        """
        data = await api("GET", "/admin/scrape-filter", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def update_scrape_filter(
        max_job_age_days: int | None = None,
        strict_date_mode: bool | None = None,
    ) -> str:
        """
        Update the scraping date-filter settings. Pass only the fields you want to change.

        max_job_age_days: maximum age of accepted job postings — must be one of
                          7, 14, 30, 60, 90, or 180
        strict_date_mode: true → reject jobs whose posting date cannot be parsed;
                          false → accept jobs with unknown/missing dates
        """
        _VALID_AGE_DAYS = {7, 14, 30, 60, 90, 180}
        updates: dict = {}
        if max_job_age_days is not None:
            if max_job_age_days not in _VALID_AGE_DAYS:
                return f"max_job_age_days must be one of {sorted(_VALID_AGE_DAYS)}"
            updates["max_job_age_days"] = max_job_age_days
        if strict_date_mode is not None:
            updates["strict_date_mode"] = strict_date_mode
        if not updates:
            return "No fields provided. Pass max_job_age_days and/or strict_date_mode."
        data = await api("PUT", "/admin/scrape-filter", json=updates, invalidate_cache=True)
        return fmt(data)
