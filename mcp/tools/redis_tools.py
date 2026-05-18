from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_redis_health() -> str:
        """
        Check Redis server health: memory usage, connected clients, uptime,
        commands processed/sec, and replication status.
        """
        data = await api("GET", "/admin/redis/health", cache_ttl=15, timeout="quick")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_redis_keyspace() -> str:
        """
        Show Redis keyspace statistics: total keys per database, key count
        breakdown by prefix pattern (admin:*, cron:*, jobs:*, etc.), and
        expiration stats.
        """
        data = await api("GET", "/admin/redis/keyspace", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_redis_cache_stats() -> str:
        """
        Show Redis cache performance: hit/miss ratio, eviction count, key
        space hits vs misses, and top cached keys by TTL.
        """
        data = await api("GET", "/admin/redis/cache-stats", cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_redis_pubsub() -> str:
        """
        Show active Redis Pub/Sub channels and subscriber counts.
        Monitors the docker-agent command/result channels and any other
        active subscriptions.
        """
        data = await api("GET", "/admin/redis/pubsub", cache_ttl=10)
        return fmt(data)
