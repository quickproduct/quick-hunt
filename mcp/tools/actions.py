import asyncio
import time

from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, clamp

VALID_ACTIONS = {
    "purge-irrelevant":         "Mark jobs without PHP/Laravel relevance as ignored",
    "deduplicate":              "Remove duplicate job listings from the database",
    "reset-email-discovery":    "Reset all 'unreachable' jobs back to pending HR email discovery",
    "fill-missing-covers":      "Generate cover letters for jobs that don't have one yet",
    "backfill-hr-emails":       "Run HR email discovery for jobs missing an HR contact",
    "refresh-cover-letters":    "Regenerate stale cover letters across all jobs",
    "cleanup-old-jobs":         "Archive/remove jobs older than the configured retention window",
    "fix-placeholder-emails":   "Replace placeholder HR emails with correct ones",
    "check-cover-letter-status":"Check cover letter freshness",
    "pipeline-health-check":    "Run a full pipeline health diagnostic",
    "stale-lock-reaper":        "Release expired singleton locks left by crashed tasks",
    "purge-old-dated-jobs":     "Delete old dated new/filtered jobs",
    "priority-cover-emailed":   "Generate covers for high-priority emailed jobs first",
    "current-month-pipeline":   "Run the full pipeline for jobs scraped this month",
    "non-php-cleanup":          "Mark non-PHP jobs ignored without deleting them",
    "generate-non-php-candidates": "Assign active candidate + static cover letter to all non-PHP jobs",
}

DESTRUCTIVE_ACTIONS = {
    "purge-irrelevant",
    "deduplicate",
    "cleanup-old-jobs",
    "purge-old-dated-jobs",
    "non-php-cleanup",
}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def list_quick_actions() -> str:
        """
        List all available quick maintenance actions with descriptions.
        Use preview_quick_action(action) before destructive actions, then
        run_quick_action(action, confirm=True) after review.
        """
        lines = [f"  {name:<30} - {desc}" for name, desc in sorted(VALID_ACTIONS.items())]
        return "Available quick actions:\n\n" + "\n".join(lines)

    @mcp.tool()
    @track_duration
    async def preview_quick_action(action: str, limit: int = 20) -> str:
        """
        Preview a quick maintenance action without changing data.

        action: one of list_quick_actions(), e.g. 'deduplicate',
                'purge-irrelevant', 'backfill-hr-emails'
        limit:  number of sample rows to include, 1-100
        """
        action = action.strip().lower()
        if action not in VALID_ACTIONS:
            closest = [k for k in VALID_ACTIONS if action.replace("-", "") in k.replace("-", "")]
            hint = f"\nDid you mean: {', '.join(closest)}?" if closest else ""
            return (
                f"Unknown action '{action}'.{hint}\n"
                f"Run list_quick_actions() to see all available actions."
            )
        data = await api(
            "POST",
            f"/admin/actions/{action}/preview",
            params={"limit": clamp(limit, 1, 100)},
            cache_ttl=5,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def run_quick_action(action: str, confirm: bool = False) -> str:
        """
        Trigger a one-shot maintenance action immediately (runs as a Celery task).
        Use preview_quick_action(action) first for destructive actions.

        action: one of the maintenance action names, e.g. 'deduplicate',
                'fill-missing-covers', 'pipeline-health-check'
        confirm: must be true for destructive/bulk cleanup actions
        """
        action = action.strip().lower()
        if action not in VALID_ACTIONS:
            closest = [k for k in VALID_ACTIONS if action.replace("-", "") in k.replace("-", "")]
            hint = f"\nDid you mean: {', '.join(closest)}?" if closest else ""
            return (
                f"Unknown action '{action}'.{hint}\n"
                f"Run list_quick_actions() to see all available actions."
            )
        if action in DESTRUCTIVE_ACTIONS and not confirm:
            return (
                f"Action '{action}' requires confirm=True. "
                f"Call preview_quick_action('{action}') first, then rerun with confirm=True."
            )
        data = await api(
            "POST",
            f"/admin/quick-actions/{action}",
            params={"confirm": confirm},
            timeout="long",
            invalidate_cache=True,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_task_status(task_id: str) -> str:
        """
        Get Celery task status plus any matching cron run and recent worker events.

        task_id: Celery task id returned by run_quick_action or trigger_cron_task
        """
        if not task_id.strip():
            return '{"error": "task_id is required"}'
        data = await api("GET", f"/admin/tasks/{task_id.strip()}", cache_ttl=3)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def wait_for_task(task_id: str, timeout_seconds: int = 60, poll_seconds: int = 3) -> str:
        """
        Poll a Celery task until it finishes or times out.

        task_id: Celery task id to monitor
        timeout_seconds: max seconds to wait, 1-600
        poll_seconds: seconds between checks, 1-30
        """
        if not task_id.strip():
            return '{"error": "task_id is required"}'
        timeout_seconds = clamp(timeout_seconds, 1, 600)
        poll_seconds = clamp(poll_seconds, 1, 30)
        deadline = time.monotonic() + timeout_seconds
        last = None
        while time.monotonic() <= deadline:
            last = await api("GET", f"/admin/tasks/{task_id.strip()}", cache_ttl=0)
            if last.get("ready"):
                return fmt({"timed_out": False, **last})
            await asyncio.sleep(poll_seconds)
        return fmt({"timed_out": True, "timeout_seconds": timeout_seconds, "last_status": last})

    @mcp.tool()
    @track_duration
    async def get_action_run_summary(task_id: str) -> str:
        """
        Summarize a dispatched maintenance action using task status, cron result,
        and recent worker events.
        """
        if not task_id.strip():
            return '{"error": "task_id is required"}'
        data = await api("GET", f"/admin/tasks/{task_id.strip()}", cache_ttl=0)
        summary = {
            "task_id": data.get("task_id"),
            "state": data.get("state"),
            "ready": data.get("ready"),
            "successful": data.get("successful"),
            "failed": data.get("failed"),
            "result": data.get("result"),
            "cron_run": data.get("cron_run"),
            "recent_events": data.get("recent_events", [])[:5],
        }
        return fmt(summary)

    @mcp.tool()
    @track_duration
    async def preview_non_php_jobs(limit: int = 50) -> str:
        """
        Preview jobs that do not look PHP/Laravel-related and would be marked ignored.
        """
        data = await api(
            "GET",
            "/admin/jobs/cleanup/preview/non_php",
            params={"limit": clamp(limit, 1, 100)},
            cache_ttl=5,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def ignore_non_php_jobs(confirm: bool = False, limit: int = 200) -> str:
        """
        Mark non-PHP jobs as ignored. Does not hard-delete data.

        confirm: must be true after previewing
        limit: max jobs to update, 1-500
        """
        if not confirm:
            return "Set confirm=True after running preview_non_php_jobs()."
        data = await api(
            "POST",
            "/admin/jobs/cleanup/non-php/ignore",
            json={"confirm": True, "limit": clamp(limit, 1, 500)},
            invalidate_cache=True,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def preview_job_cleanup(kind: str, limit: int = 50) -> str:
        """
        Preview a cleanup class without mutating data.

        kind: non_php | low_score | missing_hr_email_stale | duplicate | old_terminal
        limit: number of sample jobs, 1-100
        """
        valid = {"non_php", "low_score", "missing_hr_email_stale", "duplicate", "old_terminal"}
        kind = kind.strip().lower()
        if kind not in valid:
            return f"Invalid kind '{kind}'. Choose from: {', '.join(sorted(valid))}"
        data = await api(
            "GET",
            f"/admin/jobs/cleanup/preview/{kind}",
            params={"limit": clamp(limit, 1, 100)},
            cache_ttl=5,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_pipeline_doctor() -> str:
        """
        Get a compact operator health report across system health, queues,
        workers, cron KPIs, DB/Redis health, and recommended actions.
        """
        data = await api("GET", "/admin/pipeline/doctor", timeout="long", cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def recommend_next_actions() -> str:
        """
        Return ranked maintenance recommendations with preview counts and samples.
        """
        data = await api("GET", "/admin/actions/recommendations", cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_cover_letter_status() -> str:
        """
        Show cover letter freshness statistics across all jobs:
        total jobs, how many have fresh covers, stale covers, or no cover at all,
        broken down per candidate. Useful after running fill-missing-covers or
        refresh-cover-letters.
        """
        data = await api("GET", "/admin/cover-letter-status", cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def preview_generate_non_php_candidates(limit: int = 50) -> str:
        """
        Preview non-PHP jobs that would receive a candidate assignment and
        static cover letter. Shows candidate info, affected job count, and
        sample jobs.

        limit: number of sample jobs to include, 1-100
        """
        data = await api(
            "POST",
            "/admin/actions/generate-non-php-candidates/preview",
            params={"limit": clamp(limit, 1, 100)},
            cache_ttl=5,
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def generate_non_php_candidates() -> str:
        """
        Assign the active candidate + their static cover letter to ALL non-PHP
        jobs (is_php_python=false) that are not in a terminal or filtered status.
        Sets each job's status to 'cover_generated'.

        Overwrites existing candidate_id and cover_letter on matching jobs.
        Run preview_generate_non_php_candidates() first to see what would change.
        """
        data = await api(
            "POST",
            "/admin/quick-actions/generate-non-php-candidates",
            invalidate_cache=True,
        )
        return fmt(data)
