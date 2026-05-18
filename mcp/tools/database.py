from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_db_health() -> str:
        """
        Check database connection health: pool utilization, active connections,
        response latency (ping), and pool configuration.
        """
        data = await api("GET", "/admin/db/health", cache_ttl=15, timeout="quick")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_table_stats() -> str:
        """
        Show row counts for all major tables: jobs (by status), candidates,
        send_logs, cron_runs, search_tasks, embeddings, and blacklisted_companies.
        """
        data = await api("GET", "/admin/db/tables", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_slow_queries() -> str:
        """
        List the top 10 slowest queries from pg_stat_statements.
        Shows query text, total execution time, call count, and mean time.
        Requires pg_stat_statements extension to be enabled.
        """
        data = await api("GET", "/admin/db/slow-queries", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_db_size() -> str:
        """
        Show database size, individual table sizes (data + indexes), and
        total index size. Useful for tracking growth over time.
        """
        data = await api("GET", "/admin/db/size", cache_ttl=60)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_migration_status() -> str:
        """
        Show current Alembic migration revision and any pending migrations
        that haven't been applied yet.
        """
        data = await api("GET", "/admin/db/migrations", cache_ttl=60)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_lock_status() -> str:
        """
        Detect active database locks, blocking queries, and potential deadlocks.
        Shows blocked PIDs, lock types, and the queries causing the block.
        """
        data = await api("GET", "/admin/db/locks", cache_ttl=5)
        return fmt(data)
