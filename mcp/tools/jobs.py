"""MCP tools for admin job management — search, view, update, delete."""
from mcp.server.fastmcp import FastMCP
from ._http import api, fmt, _cache_invalidate
from ._base import track_duration, validate_choice, clamp

_VALID_STATUSES = {
    "new", "scraped", "scored", "cover_generated", "hr_found",
    "email_queued", "pending_approval", "sent", "bounced",
    "ignored", "error", "filtered", "unreachable",
}

_VALID_HR_DISCOVERY_STATUSES = {"pending", "found", "not_found", "unreachable"}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def search_jobs(
        status: str = "",
        company: str = "",
        portal: str = "",
        search: str = "",
        candidate_id: str = "",
        min_score: float = 0.0,
        has_hr_email: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """
        Search and filter jobs across all tenants (operator view).

        status:       pipeline stage — new, scraped, scored, cover_generated, hr_found,
                      email_queued, pending_approval, sent, bounced, ignored, error, filtered
        company:      partial match on company name
        portal:       exact portal name (naukri, indeed, shine, etc.)
        search:       partial match on job_title or company
        candidate_id: filter by candidate UUID
        min_score:    minimum relevance score (0–100)
        has_hr_email: "yes" to require HR email present, "no" for missing, "" for all
        limit:        rows to return (1–500, default 20)
        offset:       pagination offset (default 0)
        """
        params: dict = {
            "limit": clamp(limit, 1, 500),
            "offset": max(0, offset),
        }
        if status.strip():
            params["status"] = status.strip()
        if company.strip():
            params["company"] = company.strip()
        if portal.strip():
            params["portal"] = portal.strip()
        if search.strip():
            params["search"] = search.strip()
        if candidate_id.strip():
            params["candidate_id"] = candidate_id.strip()
        if min_score > 0:
            params["min_score"] = min_score
        if has_hr_email.strip().lower() == "yes":
            params["has_hr_email"] = "true"
        elif has_hr_email.strip().lower() == "no":
            params["has_hr_email"] = "false"

        data = await api("GET", "/admin/jobs", params=params, cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_job_detail(job_id: str) -> str:
        """
        Get the full detail for a single job including cover letter text,
        score breakdown JSON, HR discovery status, and all metadata.

        job_id: the UUID of the job
        """
        if not job_id.strip():
            return '{"error": "job_id is required"}'
        data = await api("GET", f"/admin/jobs/{job_id.strip()}")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def update_job(
        job_id: str,
        status: str = "",
        hr_email: str = "",
        relevance_score: float = -1.0,
        cover_letter: str = "",
        hr_email_discovery_status: str = "",
    ) -> str:
        """
        Update one or more fields on a job. Only provide the fields you want to change.

        job_id:                    required — UUID of the job to update
        status:                    new pipeline status (see search_jobs for valid values)
        hr_email:                  set or overwrite the HR email address
        relevance_score:           new score value (0–100), pass -1 to skip
        cover_letter:              replace the cover letter text
        hr_email_discovery_status: pending | found | not_found | unreachable
        """
        if not job_id.strip():
            return '{"error": "job_id is required"}'

        body: dict = {}

        if status.strip():
            err = validate_choice(status.strip(), _VALID_STATUSES, "status")
            if err:
                return err
            body["status"] = status.strip()

        if hr_email.strip():
            body["hr_email"] = hr_email.strip()

        if relevance_score >= 0:
            body["relevance_score"] = relevance_score

        if cover_letter.strip():
            body["cover_letter"] = cover_letter.strip()

        if hr_email_discovery_status.strip():
            err = validate_choice(
                hr_email_discovery_status.strip(),
                _VALID_HR_DISCOVERY_STATUSES,
                "hr_email_discovery_status",
            )
            if err:
                return err
            body["hr_email_discovery_status"] = hr_email_discovery_status.strip()

        if not body:
            return '{"error": "No fields to update — provide at least one field to change."}'

        data = await api("PATCH", f"/admin/jobs/{job_id.strip()}", json=body, invalidate_cache=True)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def delete_job(job_id: str, confirm: bool = False) -> str:
        """
        Permanently delete a job and its associated send_logs and embeddings.
        This action is irreversible.

        job_id:  UUID of the job to delete
        confirm: must be True to proceed (safety guard)
        """
        if not job_id.strip():
            return '{"error": "job_id is required"}'
        if not confirm:
            return (
                '{"error": "Deletion aborted — set confirm=True to permanently delete this job '
                'and all its send_logs and embeddings."}'
            )
        data = await api("DELETE", f"/admin/jobs/{job_id.strip()}", invalidate_cache=True)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def bulk_update_jobs(
        job_ids: list[str],
        status: str,
        dry_run: bool = False,
    ) -> str:
        """
        Update the status of multiple jobs at once (max 200 per call).

        job_ids: list of job UUIDs to update
        status:  new status for all jobs (see search_jobs for valid values)
        dry_run: if True, returns how many would be updated without making changes
        """
        if not job_ids:
            return '{"error": "job_ids list is empty"}'
        if len(job_ids) > 200:
            return '{"error": "Maximum 200 jobs per bulk operation"}'
        err = validate_choice(status.strip(), _VALID_STATUSES, "status")
        if err:
            return err

        body = {"job_ids": job_ids, "status": status.strip(), "dry_run": dry_run}
        data = await api("POST", "/admin/jobs/bulk-update", json=body, invalidate_cache=True)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def bulk_delete_jobs(
        job_ids: list[str],
        confirm: bool = False,
    ) -> str:
        """
        Permanently delete multiple jobs and their send_logs and embeddings (max 200).
        This action is irreversible.

        job_ids: list of job UUIDs to delete
        confirm: must be True to proceed (safety guard)
        """
        if not job_ids:
            return '{"error": "job_ids list is empty"}'
        if len(job_ids) > 200:
            return '{"error": "Maximum 200 jobs per bulk operation"}'
        if not confirm:
            return (
                f'{{"error": "Deletion aborted — set confirm=True to permanently delete '
                f'{len(job_ids)} jobs and all their associated records."}}'
            )
        body = {"job_ids": job_ids}
        data = await api("DELETE", "/admin/jobs/bulk-delete", json=body, invalidate_cache=True)
        return fmt(data)
