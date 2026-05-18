import sys
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, validate_choice, clamp

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import LOG_DIR

_VALID_LEVELS = {"critical", "error", "warning", "app"}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_log_summary() -> str:
        """
        Return line counts for each log file (critical, error, warning) plus
        the size of app.log. Quick way to see how noisy the system is right now.
        """
        data = await api("GET", "/admin/logs-summary", cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_logs(level: str = "error", lines: int = 100) -> str:
        """
        Read the last N lines from a log file.

        level: one of 'critical', 'error', 'warning', 'app' (default: error)
        lines: number of tail lines to return, 1-500 (default: 100)
        """
        err = validate_choice(level, _VALID_LEVELS, "level")
        if err:
            return err
        lines = clamp(lines, 1, 500)
        data = await api("GET", f"/admin/logs/{level}", params={"lines": lines})
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def search_logs(pattern: str, level: str = "app", lines: int = 500) -> str:
        """
        Search log files for lines matching a keyword or substring.
        Reads directly from the log file on disk (no API hop).

        pattern: text to search for (case-insensitive)
        level:   log file to search - 'critical', 'error', 'warning', 'app' (default: app)
        lines:   how many tail lines to scan before searching (default: 500)

        Returns up to 100 matching lines with their line numbers.
        """
        err = validate_choice(level, _VALID_LEVELS, "level")
        if err:
            return err

        filename = "errors.log" if level == "error" else f"{level}.log"
        log_path = LOG_DIR / filename

        if not log_path.exists():
            return f"Log file not found: {log_path}"

        pattern_lower = pattern.lower()
        matches = []
        try:
            with open(log_path, "r", errors="replace") as f:
                all_lines = f.readlines()
        except OSError as exc:
            return f"Could not read log file: {exc}"

        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
        offset = len(all_lines) - len(tail) + 1
        for i, line in enumerate(tail):
            if pattern_lower in line.lower():
                matches.append({"line_number": offset + i, "text": line.rstrip()})
            if len(matches) >= 100:
                break

        if not matches:
            return f"No lines matching '{pattern}' found in last {len(tail)} lines of {filename}."

        summary = f"Found {len(matches)} match(es) for '{pattern}' in {filename}"
        return summary + "\n\n" + fmt(matches)
