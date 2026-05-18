"""MCP tools for admin candidate management — list, view, update."""
from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def list_candidates(include_inactive: bool = True) -> str:
        """
        List all candidate profiles across all tenants.
        Returns name, email, active status, years of experience, and target roles.

        include_inactive: set to False to show only active candidates (default True — show all)
        """
        data = await api(
            "GET",
            "/admin/candidates",
            params={"include_inactive": str(include_inactive).lower()},
        )
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_candidate(candidate_id: str) -> str:
        """
        Get the full profile of a candidate, including cover letter template,
        static cover letter text, skills list, target roles/locations, and bio.

        candidate_id: UUID of the candidate
        """
        if not candidate_id.strip():
            return '{"error": "candidate_id is required"}'
        data = await api("GET", f"/admin/candidates/{candidate_id.strip()}")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def update_candidate_profile(
        candidate_id: str,
        name: str = "",
        email: str = "",
        bio: str = "",
        years_experience: int = -1,
        is_active: str = "",
        cover_letter_template: str = "",
        static_cover_letter: str = "",
        skills: list[str] | None = None,
        target_roles: list[str] | None = None,
        target_locations: list[str] | None = None,
    ) -> str:
        """
        Update one or more fields on a candidate profile.
        Only supply the fields you want to change — all others are left unchanged.

        candidate_id:           required — UUID of the candidate
        name:                   display name
        email:                  contact email address
        bio:                    short bio / professional summary
        years_experience:       integer years (pass -1 to skip)
        is_active:              "true" or "false" to activate/deactivate the candidate
        cover_letter_template:  Jinja-style template used for AI-generated covers
        static_cover_letter:    Fixed cover letter text (used when AI is disabled)
        skills:                 list of skill strings e.g. ["Python", "FastAPI"]
        target_roles:           list of job titles to target e.g. ["Backend Engineer"]
        target_locations:       list of preferred locations e.g. ["Remote", "Bangalore"]
        """
        if not candidate_id.strip():
            return '{"error": "candidate_id is required"}'

        body: dict = {}

        if name.strip():
            body["name"] = name.strip()
        if email.strip():
            body["email"] = email.strip()
        if bio.strip():
            body["bio"] = bio.strip()
        if years_experience >= 0:
            body["years_experience"] = years_experience
        if is_active.strip().lower() == "true":
            body["is_active"] = True
        elif is_active.strip().lower() == "false":
            body["is_active"] = False
        if cover_letter_template.strip():
            body["cover_letter_template"] = cover_letter_template.strip()
        if static_cover_letter.strip():
            body["static_cover_letter"] = static_cover_letter.strip()
        if skills is not None:
            body["skills"] = skills
        if target_roles is not None:
            body["target_roles"] = target_roles
        if target_locations is not None:
            body["target_locations"] = target_locations

        if not body:
            return '{"error": "No fields to update — provide at least one field to change."}'

        data = await api(
            "PATCH",
            f"/admin/candidates/{candidate_id.strip()}",
            json=body,
        )
        return fmt(data)
