from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, validate_choice, clamp

KNOWN_CRON_TASKS = {
    "scheduled_scrape",
    "backfill_hr_emails_task",
    "fix_placeholder_emails_task",
    "fill_missing_covers_task",
    "refresh_cover_letters_task",
    "deduplicate_jobs_task",
    "cleanup_old_jobs_task",
    "pipeline_health_check_task",
    "stale_lock_reaper_task",
    "check_cover_letter_status_task",
    "purge_old_cron_runs_task",
    "retry_failed_sends_task",
}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_cron_status() -> str:
        """
        Show the circuit-breaker state, singleton lock, and rate-limit counter
        for every scheduled cron task. Helps identify which tasks are stuck,
        tripped, or rate-limited right now.
        """
        data = await api("GET", "/admin/cron/status", cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_cron_runs(
        task: str = "",
        status: str = "",
        limit: int = 20,
    ) -> str:
        """
        List recent cron job execution history, newest first.

        task:   filter by task name (e.g. 'scheduled_scrape'), or leave empty for all
        status: filter by status - 'success', 'failed', 'running', or empty for all
        limit:  number of records to return, 1-100 (default: 20)
        """
        params: dict = {"limit": clamp(limit, 1, 100)}
        if task.strip():
            params["task"] = task.strip()
        if status.strip():
            params["status"] = status.strip()
        data = await api("GET", "/admin/cron/runs", params=params, cache_ttl=5)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_cron_run_detail(run_id: int) -> str:
        """
        Get the full execution detail for a single cron run, including every
        step in the timeline, error tracebacks, and pre/post state snapshots
        (e.g. DB row counts before and after the run).

        run_id: the integer ID from get_cron_runs
        """
        data = await api("GET", f"/admin/cron/runs/{run_id}")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def reset_cron_circuit(task_name: str) -> str:
        """
        Reset the circuit breaker for a cron task that has tripped due to
        repeated failures. This allows the task to run again on its next
        scheduled interval.

        task_name: one of the known cron task names (see get_cron_status)
        """
        task_name = task_name.strip()
        err = validate_choice(task_name, KNOWN_CRON_TASKS, "task_name")
        if err:
            return err
        data = await api("POST", f"/admin/cron/{task_name}/reset_circuit")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def release_cron_lock(task_name: str) -> str:
        """
        Force-release the singleton lock for a cron task that got stuck
        mid-execution (e.g. worker crashed while the task was running).
        Without this, the task will refuse to start again until the lock TTL expires.

        task_name: one of the known cron task names (see get_cron_status)
        """
        task_name = task_name.strip()
        err = validate_choice(task_name, KNOWN_CRON_TASKS, "task_name")
        if err:
            return err
        data = await api("POST", f"/admin/cron/{task_name}/release_lock")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def reset_cron_rate_limit(task_name: str) -> str:
        """
        Clear the rate-limit counter for a cron task so it can run again
        before its normal cooldown window expires.

        task_name: one of the known cron task names (see get_cron_status)
        """
        task_name = task_name.strip()
        err = validate_choice(task_name, KNOWN_CRON_TASKS, "task_name")
        if err:
            return err
        data = await api("POST", f"/admin/cron/{task_name}/reset_rate_limit")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_cron_kpis() -> str:
        """
        Return aggregated cron health metrics for the last 24 hours:
        running_now, failures_24h, total_runs_24h, success_rate_24h (%), avg_duration_ms.
        Use this for a quick pulse-check before drilling into individual runs.
        """
        data = await api("GET", "/admin/cron/kpis", cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_cron_tasks() -> str:
        """
        List the full catalog of registered cron tasks with their schedule expression,
        destination queue, and category (scraping/ai/email/maintenance).
        Useful for understanding what runs automatically and how often.
        """
        data = await api("GET", "/admin/cron/tasks", cache_ttl=60)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def trigger_cron_task(
        task_name: str,
        bypass_lock: bool = False,
        bypass_rate_limit: bool = False,
    ) -> str:
        """
        Directly trigger a cron task RIGHT NOW, bypassing the beat schedule.
        The task is dispatched to its normal Celery queue and runs immediately.

        Use this when you want to run a maintenance task on demand rather than
        waiting for the next scheduled interval.

        task_name:         one of the known cron task names (see get_cron_tasks):
                              scheduled_scrape, backfill_hr_emails_task,
                              fix_placeholder_emails_task, fill_missing_covers_task,
                              refresh_cover_letters_task, check_cover_letter_status_task,
                              deduplicate_jobs_task,
                              cleanup_old_jobs_task, pipeline_health_check_task,
                              stale_lock_reaper_task, purge_old_cron_runs_task,
                              retry_failed_sends_task
        bypass_lock:       if True, releases the singleton lock first so the task
                           can run even if a previous execution is still holding it.
                           WARNING: may result in two instances running concurrently.
        bypass_rate_limit: if True, clears the rate-limit counter so the task
                           can run even if it has already hit its hourly limit.
        """
        task_name = task_name.strip()
        err = validate_choice(task_name, KNOWN_CRON_TASKS, "task_name")
        if err:
            return err

        body: dict = {
            "bypass_lock": bypass_lock,
            "bypass_rate_limit": bypass_rate_limit,
        }
        data = await api(
            "POST",
            f"/admin/cron/{task_name}/trigger",
            json=body,
            timeout="long",
        )
        return fmt(data)
