"""Admin service layer — RabbitMQ, Redis feature flags, log reader, worker config."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx
import structlog

from services.api.core.config import get_settings

logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_INFRA_DIR = _PROJECT_ROOT / "infra"
_WORKER_CONFIG_FILE = _INFRA_DIR / "worker.config.yml"
_LOG_DIR = Path(get_settings().log_dir) if not Path(get_settings().log_dir).is_absolute() else Path(get_settings().log_dir)

_ADMIN_FEATURES_KEY = "admin:features"
_ADMIN_PORTAL_PREFIX = "admin:portal:"
_CONFIG_LOCK_KEY = "admin:lock:worker_config"
_CONFIG_LOCK_TTL = 30
_CONFIG_SNAPSHOT_KEY = "admin:config:snapshot"
_CONFIG_SNAPSHOT_TTL = 600
_PERFORMANCE_MODE_KEY = "admin:performance:mode"
_WORKER_PAUSED_PREFIX = "admin:worker:paused:"
_QUEUE_CACHE_KEY = "admin:cache:queues"
_QUEUE_CACHE_TTL = 5

ALL_PORTALS = [
    "naukri", "indeed", "shine", "internshala",
    "remoteok", "weworkremotely", "workingnomads", "jobspresso",
]

PERFORMANCE_PRESETS = {
    "turbo": {
        "scraping_bulk": {"scale": 3, "concurrency": 4},
        "scraping_realtime": {"scale": 10, "concurrency": 8},
        "enrichment": {"scale": 3, "concurrency": 4},
        "maintenance": {"scale": 2, "concurrency": 2},
        "cover_bulk": {"scale": 3, "concurrency": 3},
        "cover_ranking": {"scale": 2, "concurrency": 2},
        "cover_generation": {"scale": 5, "concurrency": 4},
        "cover_workflow": {"scale": 3, "concurrency": 3},
        "email": {"scale": 4, "concurrency": 4},
        "cover_batch": {"scale": 1, "concurrency": 1},
    },
    "economy": {
        "scraping_bulk": {"scale": 1, "concurrency": 1},
        "scraping_realtime": {"scale": 2, "concurrency": 2},
        "enrichment": {"scale": 1, "concurrency": 1},
        "maintenance": {"scale": 1, "concurrency": 1},
        "cover_bulk": {"scale": 1, "concurrency": 1},
        "cover_ranking": {"scale": 1, "concurrency": 1},
        "cover_generation": {"scale": 1, "concurrency": 1},
        "cover_workflow": {"scale": 1, "concurrency": 1},
        "email": {"scale": 1, "concurrency": 1},
        "cover_batch": {"scale": 1, "concurrency": 1},
    },
}

_NORMAL_BASELINE: dict[str, dict[str, int]] = {
    "scraping_bulk": {"scale": 1, "concurrency": 1},
    "scraping_realtime": {"scale": 2, "concurrency": 2},
    "enrichment": {"scale": 1, "concurrency": 1},
    "maintenance": {"scale": 1, "concurrency": 1},
    "cover_bulk": {"scale": 1, "concurrency": 1},
    "cover_ranking": {"scale": 1, "concurrency": 1},
    "cover_generation": {"scale": 1, "concurrency": 1},
    "cover_workflow": {"scale": 1, "concurrency": 1},
    "email": {"scale": 1, "concurrency": 1},
    "cover_batch": {"scale": 1, "concurrency": 1},
}


def _get_normal_preset() -> dict[str, dict[str, int]]:
    return dict(_NORMAL_BASELINE)


async def _get_async_redis():
    from services.api.core.cache import get_redis
    return await get_redis()


async def check_system_health() -> dict[str, str]:
    results = {}
    settings = get_settings()

    results["database"] = await _check_db()
    results["rabbitmq"] = await _check_rabbitmq(settings)
    results["redis"] = await _check_redis()
    results["ollama"] = await _check_ollama(settings)

    return results


async def _check_db() -> str:
    try:
        from sqlalchemy import text
        from services.api.core.database import get_worker_session_factory
        sf = get_worker_session_factory()
        async with sf() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("health_check_db_failed", error=str(exc))
        return f"error: {type(exc).__name__}"


async def _check_rabbitmq(settings) -> str:
    url = settings.rabbitmq_url
    if not url or not url.startswith(("amqp://", "amqps://")):
        return "not_configured"
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "rabbitmq"
        user = unquote(parsed.username or "guest")
        password = unquote(parsed.password or "guest")
        vhost = unquote(parsed.path.lstrip("/")) or "/"
        vhost_encoded = quote(vhost, safe="")
        if url.startswith("amqps://"):
            mgmt_url = f"https://{host}:443/api/aliveness-test/{vhost_encoded}"
        else:
            mgmt_url = f"http://{host}:15672/api/aliveness-test/{vhost_encoded}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(mgmt_url, auth=(user, password))
            return "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


async def _check_redis() -> str:
    try:
        r = await _get_async_redis()
        if r is None:
            return "not_configured"
        await r.ping()
        return "ok"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


async def _check_ollama(settings) -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_host}/api/tags")
            return "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
    except Exception:
        return "not_configured"


async def get_queue_stats() -> list[dict[str, Any]]:
    r_cache = await _get_async_redis()
    if r_cache:
        try:
            cached = await r_cache.get(_QUEUE_CACHE_KEY)
            if cached:
                import json as _json
                return _json.loads(cached)
        except Exception:
            pass

    settings = get_settings()
    url = settings.rabbitmq_url
    if not url or not url.startswith(("amqp://", "amqps://")):
        return []
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "rabbitmq"
        user = unquote(parsed.username or "guest")
        password = unquote(parsed.password or "guest")
        vhost = unquote(parsed.path.lstrip("/")) or "/"
        vhost_encoded = quote(vhost, safe="")
        if url.startswith("amqps://"):
            mgmt_url = f"https://{host}:443/api/queues/{vhost_encoded}"
        else:
            mgmt_url = f"http://{host}:15672/api/queues/{vhost_encoded}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                mgmt_url,
                auth=(user, password),
                params={"lengths_age": "60", "lengths_incr": "60"},
            )
            if resp.status_code != 200:
                logger.warning("rabbitmq_api_error", status=resp.status_code)
                return []
            queues = resp.json()
            result = [
                {
                    "name": q.get("name", ""),
                    "messages": q.get("messages", 0),
                    "messages_ready": q.get("messages_ready", 0),
                    "messages_unacknowledged": q.get("messages_unacknowledged", 0),
                    "consumers": q.get("consumers", 0),
                    "rate": q.get("message_stats", {}).get("publish_details", {}).get("rate", 0),
                    "deliver_rate": q.get("message_stats", {}).get("deliver_get_details", {}).get("rate", 0),
                }
                for q in queues
                if q.get("name", "").startswith("jh_")
            ]

        if r_cache:
            try:
                import json as _json
                await r_cache.set(_QUEUE_CACHE_KEY, _json.dumps(result), ex=_QUEUE_CACHE_TTL)
            except Exception:
                pass

        return result
    except Exception as exc:
        logger.warning("get_queue_stats_failed", error=str(exc))
        return []


def read_log_file(level: str, lines: int = 100) -> dict[str, Any]:
    valid_levels = {"critical", "error", "warning", "app"}
    if level not in valid_levels:
        return {"entries": [], "total_lines": 0, "level": level, "error": f"Invalid level. Use: {valid_levels}"}

    filename = f"{level}.log"
    filepath = _LOG_DIR / filename

    if not filepath.exists():
        return {"entries": [], "total_lines": 0, "level": level, "error": "File not found"}

    try:
        from collections import deque
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            tail_lines = deque(f, maxlen=lines)
            f.seek(0, 2)
            total_lines = f.tell()

        if total_lines == 0:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                total_lines = sum(1 for _ in f)

        return {
            "entries": [line.rstrip("\n") for line in tail_lines],
            "total_lines": total_lines,
            "level": level,
        }
    except Exception as exc:
        return {"entries": [], "total_lines": 0, "level": level, "error": str(exc)}


def get_log_summary() -> dict[str, Any]:
    result = {}
    for level in ["critical", "error", "warning"]:
        filepath = _LOG_DIR / f"{level}.log"
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    count = sum(1 for _ in f)
                result[level] = count
            except Exception:
                result[level] = -1
        else:
            result[level] = 0

    app_path = _LOG_DIR / "app.log"
    if app_path.exists():
        try:
            size = app_path.stat().st_size
            result["app_size_mb"] = round(size / (1024 * 1024), 2)
        except Exception:
            result["app_size_mb"] = 0
    else:
        result["app_size_mb"] = 0

    return result


async def get_features() -> dict[str, Any]:
    settings = get_settings()
    defaults = {
        "auto_send_enabled": settings.auto_send_enabled,
        "langchain_enabled": settings.langchain_enabled,
        "semantic_filter_enabled": settings.semantic_filter_enabled,
        "score_threshold": settings.score_threshold,
    }

    r = await _get_async_redis()
    if r is None:
        return defaults

    try:
        stored = await r.hgetall(_ADMIN_FEATURES_KEY)
        if stored:
            for key in ["auto_send_enabled", "langchain_enabled", "semantic_filter_enabled"]:
                if key in stored:
                    defaults[key] = stored[key] == "true"
            if "score_threshold" in stored:
                defaults["score_threshold"] = int(stored["score_threshold"])
    except Exception as exc:
        logger.warning("get_features_redis_failed", error=str(exc))

    return defaults


async def update_features(updates: dict[str, Any]) -> dict[str, Any]:
    r = await _get_async_redis()
    if r is None:
        raise RuntimeError("Redis unavailable — cannot update features")

    fields = {}
    valid_keys = {"auto_send_enabled", "langchain_enabled", "semantic_filter_enabled", "score_threshold"}
    for key, value in updates.items():
        if key not in valid_keys:
            continue
        fields[key] = str(value).lower() if isinstance(value, bool) else str(value)

    if fields:
        await r.hset(_ADMIN_FEATURES_KEY, mapping=fields)
        logger.info("admin_features_updated", **fields)

    return await get_features()


async def is_feature_enabled(feature: str) -> bool | None:
    r = await _get_async_redis()
    if r is None:
        return None
    try:
        val = await r.hget(_ADMIN_FEATURES_KEY, feature)
        if val is not None:
            return val == "true"
    except Exception:
        pass
    return None


async def get_portals() -> list[dict[str, Any]]:
    r = await _get_async_redis()
    portal_list = []
    for name in ALL_PORTALS:
        enabled = True
        if r is not None:
            try:
                val = await r.get(f"{_ADMIN_PORTAL_PREFIX}{name}:enabled")
                if val is not None:
                    enabled = val == "true"
            except Exception:
                pass
        portal_list.append({"name": name, "enabled": enabled})
    return portal_list


async def toggle_portal(portal: str, enabled: bool) -> dict[str, Any]:
    if portal not in ALL_PORTALS:
        raise ValueError(f"Unknown portal: {portal}. Valid: {ALL_PORTALS}")

    r = await _get_async_redis()
    if r is None:
        raise RuntimeError("Redis unavailable — cannot toggle portal")

    key = f"{_ADMIN_PORTAL_PREFIX}{portal}:enabled"
    await r.set(key, "true" if enabled else "false")
    logger.info("admin_portal_toggled", portal=portal, enabled=enabled)
    return {"portal": portal, "enabled": enabled}


async def is_portal_enabled(portal: str) -> bool:
    r = await _get_async_redis()
    if r is None:
        return True
    try:
        val = await r.get(f"{_ADMIN_PORTAL_PREFIX}{portal}:enabled")
        if val is not None:
            return val == "true"
    except Exception:
        pass
    return True


def get_worker_config() -> dict[str, Any]:
    if not _WORKER_CONFIG_FILE.exists():
        return {"error": "worker.config.yml not found", "workers": {}, "broker": {}, "tasks": {}}

    try:
        import yaml
        with open(_WORKER_CONFIG_FILE, "r") as f:
            cfg = yaml.safe_load(f)
        return {
            "workers": cfg.get("workers", {}),
            "broker": cfg.get("broker", {}),
            "tasks": cfg.get("tasks", {}),
            "beat_schedule": cfg.get("beat_schedule", {}),
            "logging": cfg.get("logging", {}),
        }
    except Exception as exc:
        return {"error": str(exc)}


def update_worker_scale(worker: str, scale: int | None = None, concurrency: int | None = None) -> dict[str, Any]:
    if not _WORKER_CONFIG_FILE.exists():
        raise FileNotFoundError("worker.config.yml not found")

    scale = max(1, min(10, scale)) if scale is not None else None
    concurrency = max(1, min(8, concurrency)) if concurrency is not None else None

    import yaml
    with open(_WORKER_CONFIG_FILE, "r") as f:
        cfg = yaml.safe_load(f)

    workers = cfg.get("workers", {})
    if worker not in workers:
        raise ValueError(f"Unknown worker: {worker}. Valid: {list(workers.keys())}")

    changes = {}
    if scale is not None:
        old = workers[worker].get("scale", 1)
        workers[worker]["scale"] = scale
        changes["scale"] = {"old": old, "new": scale}
    if concurrency is not None:
        old = workers[worker].get("concurrency", 1)
        workers[worker]["concurrency"] = concurrency
        changes["concurrency"] = {"old": old, "new": concurrency}

    cfg["workers"] = workers
    with open(_WORKER_CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.info("admin_worker_config_updated", worker=worker, **changes)

    env_updated = _apply_worker_config_update()

    live_results = _apply_celery_concurrency({worker: changes})
    concurrency_live = live_results.get(worker, False)

    scale_changed = "scale" in changes
    return {
        "worker": worker,
        "changes": changes,
        "restart_required": scale_changed,
        "concurrency_applied_live": concurrency_live,
        "env_updated": env_updated,
    }


def apply_performance_mode(mode: str) -> dict[str, Any]:
    if mode not in PERFORMANCE_PRESETS and mode != "normal":
        raise ValueError(f"Unknown mode: {mode}. Valid: ['turbo', 'normal', 'economy']")

    preset = _get_normal_preset() if mode == "normal" else PERFORMANCE_PRESETS[mode]

    # ── Kubernetes path ────────────────────────────────────────────────────────
    if _is_kubernetes():
        k8s_results = _apply_k8s_performance_mode(preset)
        # Still push live concurrency changes to already-running pods
        concurrency_changes = {
            w: {"concurrency": {"old": 1, "new": v["concurrency"]}}
            for w, v in preset.items()
            if v.get("concurrency", 1) != 1
        }
        live_results = _apply_celery_concurrency(concurrency_changes)
        logger.warning("admin_performance_mode_k8s_applied", mode=mode, k8s_results=k8s_results)
        return {
            "mode": mode,
            "kubernetes": True,
            "k8s_results": k8s_results,
            "concurrency_applied_live": any(live_results.values()) if live_results else False,
            "restart_required": False,
            "workers_affected": len(k8s_results),
        }

    # ── Docker Compose path ───────────────────────────────────────────────────
    if not _WORKER_CONFIG_FILE.exists():
        raise FileNotFoundError("worker.config.yml not found")

    import yaml
    with open(_WORKER_CONFIG_FILE, "r") as f:
        cfg = yaml.safe_load(f)

    workers = cfg.get("workers", {})
    changes = {}

    for worker_name, values in preset.items():
        if worker_name not in workers:
            continue
        worker_changes = {}
        for key, new_val in values.items():
            old_val = workers[worker_name].get(key, 1)
            workers[worker_name][key] = new_val
            if old_val != new_val:
                worker_changes[key] = {"old": old_val, "new": new_val}
        if worker_changes:
            changes[worker_name] = worker_changes

    cfg["workers"] = workers
    with open(_WORKER_CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    logger.warning("admin_performance_mode_applied", mode=mode, changes=changes)

    env_updated = _apply_worker_config_update()

    live_results = _apply_celery_concurrency(changes)
    any_live = any(live_results.values()) if live_results else False

    scale_changed = any("scale" in wc for wc in changes.values())

    return {
        "mode": mode,
        "kubernetes": False,
        "changes": changes,
        "restart_required": scale_changed,
        "concurrency_applied_live": any_live,
        "env_updated": env_updated,
        "workers_affected": len(changes),
    }


# Maps worker.config.yml worker key → Celery worker hostname prefix
# (matches the --hostname flag in docker-compose.yml commands)
_WORKER_HOSTNAME_PREFIX: dict[str, str] = {
    "scraping_bulk":          "scraping-bulk",
    "scraping_realtime":      "scraping-realtime",
    "enrichment":             "enrichment",
    "maintenance":            "maintenance",
    "cover_bulk":             "cover-bulk",
    "cover_ranking":          "cover-ranking",
    "cover_generation":       "cover-generation",
    "cover_workflow":         "cover-workflow",
    "email":                  "email",
    "cover_batch":            "cover-batch",
    "scraping_mnc_dispatch":  "scraping-mnc-dispatch",
    "scraping_mnc_company":   "scraping-mnc-company",
}

# ── Kubernetes-native performance mode ────────────────────────────────────────

_WORKER_K8S_DEPLOYMENT: dict[str, str] = {
    "scraping_bulk":         "worker-scraping-bulk",
    "scraping_realtime":     "worker-scraping-realtime",
    "enrichment":            "worker-enrichment",
    "maintenance":           "worker-maintenance",
    "cover_bulk":            "worker-cover-bulk",
    "cover_ranking":         "worker-cover-ranking",
    "cover_generation":      "worker-cover-generation",
    "cover_workflow":        "worker-cover-workflow",
    "email":                 "worker-email",
    "scraping_mnc_dispatch": "worker-scraping-mnc-dispatch",
    "scraping_mnc_company":  "worker-scraping-mnc-company",
    # cover_batch intentionally excluded — fixed 1 replica, no KEDA
}

# Workers that have KEDA ScaledObjects (cover_batch and maintenance do not)
_KEDA_MANAGED: frozenset[str] = frozenset({
    "scraping_bulk", "scraping_realtime", "enrichment",
    "cover_bulk", "cover_ranking", "cover_generation", "cover_workflow", "email",
    "scraping_mnc_dispatch", "scraping_mnc_company",
})


def _is_kubernetes() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST"))


def _apply_k8s_performance_mode(
    preset: dict[str, dict],
    namespace: str = "job-hunter",
) -> dict[str, Any]:
    """Patch KEDA ScaledObjects and scale Deployments for Kubernetes environments.

    For each worker in the preset:
    1. Patches the KEDA ScaledObject maxReplicaCount so KEDA can scale up to the turbo target.
    2. Immediately scales the Deployment to min(scale, 2) so pods appear without waiting for the
       next KEDA poll cycle — KEDA will then grow beyond that as queue depth demands it.
    """
    results: dict[str, Any] = {}
    for worker_name, values in preset.items():
        deployment = _WORKER_K8S_DEPLOYMENT.get(worker_name)
        if not deployment:
            continue
        scale = values.get("scale", 1)
        worker_results: dict[str, Any] = {}

        if worker_name in _KEDA_MANAGED:
            scaler = f"{deployment}-scaler"
            patch = json.dumps({"spec": {"maxReplicaCount": scale, "minReplicaCount": 1}})
            try:
                res = subprocess.run(
                    ["kubectl", "patch", "scaledobject", scaler,
                     "-n", namespace, "--type=merge", f"--patch={patch}"],
                    capture_output=True, text=True, timeout=15,
                )
                worker_results["keda_patch"] = res.returncode == 0
                if res.returncode != 0:
                    logger.warning("keda_patch_failed", worker=worker_name, stderr=res.stderr[:300])
            except Exception as exc:
                worker_results["keda_patch"] = False
                logger.warning("keda_patch_error", worker=worker_name, error=str(exc))

        # Scale deployment immediately — KEDA will grow/shrink from this baseline
        immediate_replicas = min(scale, 2)
        try:
            res = subprocess.run(
                ["kubectl", "scale", "deployment", deployment,
                 f"--replicas={immediate_replicas}", "-n", namespace],
                capture_output=True, text=True, timeout=15,
            )
            worker_results["scale"] = res.returncode == 0
            if res.returncode != 0:
                logger.warning("k8s_scale_failed", worker=worker_name, stderr=res.stderr[:300])
        except Exception as exc:
            worker_results["scale"] = False
            logger.warning("k8s_scale_error", worker=worker_name, error=str(exc))

        results[worker_name] = worker_results
    return results


def _apply_celery_concurrency(worker_changes: dict[str, dict]) -> dict[str, bool]:
    """Broadcast live pool resize to running workers via Celery control API.

    Uses pool_grow / pool_shrink so concurrency changes take effect immediately
    without restarting containers.  Scale (replica count) changes are NOT handled
    here — those require docker compose and are flagged as restart_required.

    worker_changes: {worker_name: {"concurrency": {"old": N, "new": M}, ...}}
    """
    try:
        from services.scraper.celery_app import celery_app
    except Exception:
        return {}

    results: dict[str, bool] = {}
    for worker_name, changes in worker_changes.items():
        if "concurrency" not in changes:
            continue
        old_c = changes["concurrency"].get("old", 1)
        new_c = changes["concurrency"].get("new", 1)
        if old_c == new_c:
            continue

        prefix = _WORKER_HOSTNAME_PREFIX.get(worker_name)
        if not prefix:
            continue

        # Celery hostname pattern — matches all replicas of this worker type
        destination = [f"{prefix}-*@*"]
        diff = new_c - old_c
        try:
            if diff > 0:
                celery_app.control.pool_grow(diff, destination=destination, reply=False)
            else:
                celery_app.control.pool_shrink(abs(diff), destination=destination, reply=False)
            results[worker_name] = True
            logger.info("celery_concurrency_updated", worker=worker_name, old=old_c, new=new_c)
        except Exception as exc:
            logger.warning("celery_concurrency_failed", worker=worker_name, error=str(exc)[:200])
            results[worker_name] = False

    return results


def _apply_worker_config_update() -> bool:
    try:
        script = _INFRA_DIR / "apply_worker_config.py"
        if not script.exists():
            logger.warning("apply_worker_config.py not found, skipping env update")
            return False
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_INFRA_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error(
                "apply_worker_config_failed",
                returncode=result.returncode,
                stderr=result.stderr[:500],
            )
            return False
        logger.info("worker_config_env_updated")
        return True
    except subprocess.TimeoutExpired:
        logger.error("apply_worker_config_timeout")
        return False
    except Exception as exc:
        logger.error("apply_worker_config_failed", error=str(exc))
        return False


# ── Config Lock / Snapshot / Rollback ─────────────────────────────────────────

async def acquire_config_lock(holder: str = "admin") -> bool:
    r = await _get_async_redis()
    if r is None:
        return True
    try:
        acquired = await r.set(_CONFIG_LOCK_KEY, holder, nx=True, ex=_CONFIG_LOCK_TTL)
        if acquired:
            logger.info("admin_config_lock_acquired", holder=holder)
        return bool(acquired)
    except Exception:
        return True


async def release_config_lock() -> None:
    r = await _get_async_redis()
    if r is None:
        return
    try:
        await r.delete(_CONFIG_LOCK_KEY)
    except Exception:
        pass


async def snapshot_config() -> bool:
    if not _WORKER_CONFIG_FILE.exists():
        return False
    r = await _get_async_redis()
    if r is None:
        return False
    try:
        content = _WORKER_CONFIG_FILE.read_text(encoding="utf-8")
        await r.set(_CONFIG_SNAPSHOT_KEY, content, ex=_CONFIG_SNAPSHOT_TTL)
        return True
    except Exception:
        return False


async def rollback_config() -> dict[str, Any]:
    r = await _get_async_redis()
    if r is None:
        raise RuntimeError("Redis unavailable — cannot rollback")
    content = await r.get(_CONFIG_SNAPSHOT_KEY)
    if not content:
        raise ValueError("No config snapshot found — rollback window expired (10 min)")
    _WORKER_CONFIG_FILE.write_text(content, encoding="utf-8")
    env_updated = _apply_worker_config_update()
    await r.delete(_CONFIG_SNAPSHOT_KEY)
    logger.warning("admin_config_rolled_back")
    return {"rolled_back": True, "env_updated": env_updated}


# ── Performance Mode Detection ────────────────────────────────────────────────

def _build_mode_summary(preset: dict[str, dict]) -> dict[str, Any]:
    """Return per-worker stats + totals for a given mode preset."""
    workers: dict[str, Any] = {}
    total_max_consumers = 0
    total_pods = 0
    for name, vals in preset.items():
        scale = vals.get("scale", 1)
        concurrency = vals.get("concurrency", 1)
        max_consumers = scale * concurrency
        workers[name] = {
            "max_pods": scale,
            "concurrency_per_pod": concurrency,
            "max_consumers": max_consumers,
        }
        total_max_consumers += max_consumers
        total_pods += scale
    return {
        "workers": workers,
        "total_max_pods": total_pods,
        "total_max_consumers": total_max_consumers,
    }


def get_current_performance_mode() -> dict[str, Any]:
    cfg = get_worker_config()
    if "error" in cfg and "workers" not in cfg:
        return {"mode": "unknown", "error": cfg.get("error", ""), "workers": {}}

    workers = cfg.get("workers", {})
    if not workers:
        return {"mode": "unknown", "workers": {}}

    current: dict[str, dict[str, int]] = {}
    for name, wcfg in workers.items():
        scale = wcfg.get("scale", 1)
        concurrency = wcfg.get("concurrency", 1)
        current[name] = {
            "scale": scale,
            "concurrency": concurrency,
            "max_consumers": scale * concurrency,
        }

    matched_mode = "custom"
    for mode_name, preset in PERFORMANCE_PRESETS.items():
        all_match = True
        for wname, vals in preset.items():
            if wname not in current:
                all_match = False
                break
            if current[wname]["scale"] != vals["scale"] or current[wname]["concurrency"] != vals["concurrency"]:
                all_match = False
                break
        if all_match:
            matched_mode = mode_name
            break

    if matched_mode == "custom":
        normal = _get_normal_preset()
        all_normal = True
        for wname, vals in normal.items():
            if wname not in current:
                continue
            if current[wname]["scale"] != vals["scale"] or current[wname]["concurrency"] != vals["concurrency"]:
                all_normal = False
                break
        if all_normal:
            matched_mode = "normal"

    try:
        mtime = _WORKER_CONFIG_FILE.stat().st_mtime
    except Exception:
        mtime = None

    all_presets = {**PERFORMANCE_PRESETS, "normal": _get_normal_preset()}
    mode_comparison = {name: _build_mode_summary(preset) for name, preset in all_presets.items()}

    return {
        "mode": matched_mode,
        "applied_at": mtime,
        "workers": current,
        "mode_comparison": mode_comparison,
    }


# ── Live Worker Status (Celery Inspect) ──────────────────────────────────────

async def get_workers_live_status() -> dict[str, Any]:
    try:
        from services.scraper.celery_app import celery_app
    except Exception as exc:
        return {"workers": {}, "services": {}, "error": str(exc)}

    try:
        import json
        from celery.exceptions import TimeoutError as CeleryTimeout
    except ImportError:
        pass

    timeout = 5.0
    try:
        i = celery_app.control.inspect(timeout=timeout)
        ping_data = i.ping() or {}
        active_data = i.active() or {}
        stats_data = i.stats() or {}
    except Exception as exc:
        logger.warning("celery_inspect_failed", error=str(exc)[:300])
        return {"workers": {}, "services": {}, "error": str(exc)[:200]}

    workers: dict[str, Any] = {}
    service_map: dict[str, list[str]] = {}

    for hostname in ping_data:
        service_name = _hostname_to_service(hostname)
        if service_name not in service_map:
            service_map[service_name] = []
        service_map[service_name].append(hostname)

        active_tasks = active_data.get(hostname, [])
        stats = stats_data.get(hostname, {})
        pool_config = stats.get("pool", {})
        total = stats.get("total", {})
        total_processed = sum(total.values()) if isinstance(total, dict) else 0

        workers[hostname] = {
            "hostname": hostname,
            "service": service_name,
            "status": "online",
            "uptime_seconds": stats.get("clock", 0),
            "pool_size": pool_config.get("max-concurrency", 0),
            "active_tasks": len(active_tasks),
            "active_task_names": [t.get("name", "") for t in active_tasks[:5]],
            "total_processed": total_processed,
            "pid": stats.get("pid"),
        }

    queue_stats = await get_queue_stats()
    queue_map: dict[str, dict[str, Any]] = {}
    for q in queue_stats:
        queue_map[q["name"]] = q

    cfg = get_worker_config()
    config_workers = cfg.get("workers", {})

    r = await _get_async_redis()
    paused_services: set[str] = set()
    if r:
        try:
            cursor = 0
            while True:
                cursor, keys = await r.scan(
                    cursor, match=f"{_WORKER_PAUSED_PREFIX}*", count=100
                )
                for key in keys:
                    svc = key.removeprefix(_WORKER_PAUSED_PREFIX)
                    paused_services.add(svc)
                if cursor == 0:
                    break
        except Exception:
            pass

    services: dict[str, Any] = {}
    for service_name, hostnames in service_map.items():
        worker_key = _service_to_worker_key(service_name)
        config_entry = config_workers.get(worker_key, {})
        queues_list = config_entry.get("queues", [])
        actual_concurrencies = [workers[h]["pool_size"] for h in hostnames if h in workers]
        total_active = sum(workers.get(h, {}).get("active_tasks", 0) for h in hostnames)
        total_processed = sum(workers.get(h, {}).get("total_processed", 0) for h in hostnames)
        total_depth = sum(queue_map.get(q, {}).get("messages", 0) for q in queues_list)
        total_rate = sum(queue_map.get(q, {}).get("deliver_rate", 0) for q in queues_list)

        services[service_name] = {
            "worker_key": worker_key,
            "desired_scale": config_entry.get("scale", 1),
            "actual_replicas": len(hostnames),
            "desired_concurrency": config_entry.get("concurrency", 1),
            "actual_concurrency": actual_concurrencies,
            "queues": queues_list,
            "queue_depth": total_depth,
            "deliver_rate": round(total_rate, 1),
            "total_active_tasks": total_active,
            "total_processed": total_processed,
            "health": "healthy" if len(hostnames) >= config_entry.get("scale", 1) else "degraded",
            "locked": config_entry.get("locked", False),
            "paused": service_name in paused_services,
        }

    for worker_key, config_entry in config_workers.items():
        svc = _WORKER_DOCKER_MAP.get(worker_key, f"worker-{worker_key.replace('_', '-')}")
        if svc not in services:
            queues_list = config_entry.get("queues", [])
            services[svc] = {
                "worker_key": worker_key,
                "desired_scale": config_entry.get("scale", 1),
                "actual_replicas": 0,
                "desired_concurrency": config_entry.get("concurrency", 1),
                "actual_concurrency": [],
                "queues": queues_list,
                "queue_depth": sum(queue_map.get(q, {}).get("messages", 0) for q in queues_list),
                "deliver_rate": 0,
                "total_active_tasks": 0,
                "total_processed": 0,
                "health": "offline",
                "locked": config_entry.get("locked", False),
                "paused": svc in paused_services,
            }

    return {"workers": workers, "services": services}


_WORKER_DOCKER_MAP: dict[str, str] = {
    "scraping_bulk":         "worker-scraping-bulk",
    "scraping_realtime":     "worker-scraping-realtime",
    "enrichment":            "worker-enrichment",
    "maintenance":           "worker-maintenance",
    "cover_bulk":            "worker-cover-bulk",
    "cover_ranking":         "worker-cover-ranking",
    "cover_generation":      "worker-cover-generation",
    "cover_workflow":        "worker-cover-workflow",
    "email":                 "worker-email",
    "cover_batch":           "worker-cover-batch",
    "scraping_mnc_dispatch": "worker-scraping-mnc-dispatch",
    "scraping_mnc_company":  "worker-scraping-mnc-company",
}


def _hostname_to_service(hostname: str) -> str:
    name = hostname.split("@")[0] if "@" in hostname else hostname
    parts = name.rsplit("-", 1)
    base = parts[0] if len(parts) > 1 else name
    for svc, prefix in [(k, _WORKER_HOSTNAME_PREFIX.get(k, "")) for k in _WORKER_HOSTNAME_PREFIX]:
        if base == prefix:
            return _WORKER_DOCKER_MAP.get(svc, base)
    return base


def _service_to_worker_key(service: str) -> str:
    for key, svc in _WORKER_DOCKER_MAP.items():
        if svc == service:
            return key
    return service.replace("worker-", "").replace("-", "_")


# ── Worker Actions (Restart, Pause, Resume) ──────────────────────────────────

async def restart_workers(service: str | None = None) -> dict[str, Any]:
    try:
        from services.scraper.celery_app import celery_app
    except Exception as exc:
        return {"restarted": False, "error": str(exc)}

    if service and service != "all":
        worker_key = _service_to_worker_key(service)
        prefix = _WORKER_HOSTNAME_PREFIX.get(worker_key)
        if not prefix:
            return {"restarted": False, "error": f"Unknown service: {service}"}
        destination = [f"{prefix}-*@*"]
        try:
            celery_app.control.broadcast("pool_restart", destination=destination, reply=True)
            logger.info("admin_worker_pool_restarted", service=service)
            return {"restarted": True, "service": service}
        except Exception as exc:
            logger.warning("admin_worker_restart_failed", service=service, error=str(exc)[:200])
            return {"restarted": False, "service": service, "error": str(exc)[:200]}

    try:
        celery_app.control.broadcast("pool_restart", reply=True)
        logger.info("admin_all_workers_pool_restarted")
        return {"restarted": True, "service": "all"}
    except Exception as exc:
        logger.warning("admin_all_workers_restart_failed", error=str(exc)[:200])
        return {"restarted": False, "service": "all", "error": str(exc)[:200]}


async def pause_worker(service: str) -> dict[str, Any]:
    try:
        from services.scraper.celery_app import celery_app
    except Exception as exc:
        return {"paused": False, "error": str(exc)}

    worker_key = _service_to_worker_key(service)
    config_workers = get_worker_config().get("workers", {})
    config_entry = config_workers.get(worker_key, {})
    queues = config_entry.get("queues", [])

    if not queues:
        return {"paused": False, "error": f"No queues found for {service}"}

    prefix = _WORKER_HOSTNAME_PREFIX.get(worker_key)
    if not prefix:
        return {"paused": False, "error": f"Unknown service: {service}"}

    destination = [f"{prefix}-*@*"]
    results = []
    for queue in queues:
        try:
            celery_app.control.cancel_consumer(queue, destination=destination, reply=True)
            results.append({"queue": queue, "cancelled": True})
        except Exception as exc:
            results.append({"queue": queue, "cancelled": False, "error": str(exc)[:100]})

    logger.info("admin_worker_paused", service=service, queues=queues)

    r = await _get_async_redis()
    if r:
        try:
            await r.set(f"{_WORKER_PAUSED_PREFIX}{service}", "true", ex=86400)
        except Exception:
            pass

    return {"paused": True, "service": service, "queues": results}


async def resume_worker(service: str) -> dict[str, Any]:
    try:
        from services.scraper.celery_app import celery_app
    except Exception as exc:
        return {"resumed": False, "error": str(exc)}

    worker_key = _service_to_worker_key(service)
    config_workers = get_worker_config().get("workers", {})
    config_entry = config_workers.get(worker_key, {})
    queues = config_entry.get("queues", [])

    if not queues:
        return {"resumed": False, "error": f"No queues found for {service}"}

    prefix = _WORKER_HOSTNAME_PREFIX.get(worker_key)
    if not prefix:
        return {"resumed": False, "error": f"Unknown service: {service}"}

    destination = [f"{prefix}-*@*"]
    results = []
    for queue in queues:
        try:
            celery_app.control.add_consumer(queue, destination=destination, reply=True)
            results.append({"queue": queue, "added": True})
        except Exception as exc:
            results.append({"queue": queue, "added": False, "error": str(exc)[:100]})

    logger.info("admin_worker_resumed", service=service, queues=queues)

    r = await _get_async_redis()
    if r:
        try:
            await r.delete(f"{_WORKER_PAUSED_PREFIX}{service}")
        except Exception:
            pass

    return {"resumed": True, "service": service, "queues": results}


# ── Docker Agent Bridge ──────────────────────────────────────────────────────

async def send_docker_command(action: str, params: dict | None = None, timeout: float = 10.0) -> dict[str, Any]:
    r = await _get_async_redis()
    if r is None:
        return {"error": "Redis unavailable", "success": False}

    import uuid
    cmd_id = str(uuid.uuid4())
    payload = json.dumps({"id": cmd_id, "action": action, "params": params or {}})

    pubsub = r.pubsub()
    await pubsub.subscribe("admin:docker:results")

    await r.publish("admin:docker:commands", payload)
    logger.info("docker_command_sent", action=action, id=cmd_id)

    deadline = asyncio.get_event_loop().time() + timeout
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                if data.get("id") == cmd_id:
                    return data
            except (json.JSONDecodeError, TypeError):
                continue
            if asyncio.get_event_loop().time() > deadline:
                break
    except Exception as exc:
        return {"error": str(exc), "success": False}
    finally:
        await pubsub.unsubscribe("admin:docker:results")
        await pubsub.close()

    return {"error": "timeout waiting for docker agent", "success": False}


async def get_docker_status() -> dict[str, Any]:
    r = await _get_async_redis()
    if r is None:
        return {"error": "Redis unavailable"}
    try:
        raw = await r.get("admin:docker:status")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {"error": "Docker agent status not available"}


# ── Auto-Scaler ──────────────────────────────────────────────────────────────

AUTOSCALE_KEY = "admin:autoscale:enabled"
AUTOSCALE_LOG_KEY = "admin:autoscale:log"
AUTOSCALE_POLICY_KEY = "admin:autoscale:policy"

DEFAULT_AUTOSCALE_POLICY: dict[str, dict[str, Any]] = {
    "worker-scraping-bulk":      {"queues": ["jh_scraping_bulk"],           "min": 1, "max": 5,  "scale_up_at": 50,  "scale_down_at": 5},
    "worker-scraping-realtime":  {"queues": ["jh_scraping_realtime"],       "min": 2, "max": 8,  "scale_up_at": 30,  "scale_down_at": 3},
    "worker-enrichment":         {"queues": ["jh_scraping_enrichment"],     "min": 1, "max": 5,  "scale_up_at": 40,  "scale_down_at": 5},
    "worker-maintenance":        {"queues": ["jh_jobs_maintenance"],        "min": 1, "max": 3,  "scale_up_at": 100, "scale_down_at": 10},
    # cover_bulk handles: fill_missing_covers + refresh_cover_letters + score_job
    "worker-cover-bulk":         {"queues": ["jh_cover_letter_bulk"],       "min": 1, "max": 4,  "scale_up_at": 100, "scale_down_at": 10},
    "worker-cover-ranking":      {"queues": ["jh_cover_letter_ranking"],    "min": 1, "max": 4,  "scale_up_at": 50,  "scale_down_at": 5},
    # cover_generation: on-demand single-job generation + embeddings (no separate embeddings worker)
    "worker-cover-generation":   {"queues": ["jh_cover_letter_generation", "jh_embeddings"], "min": 1, "max": 3,  "scale_up_at": 20,  "scale_down_at": 3},
    # cover_workflow: kept at min=0 — no longer dispatched from scraper
    "worker-cover-workflow":     {"queues": ["jh_cover_letter_workflow"],   "min": 0, "max": 1,  "scale_up_at": 30,  "scale_down_at": 3},
    "worker-email":              {"queues": ["jh_email_send", "jh_email_retry"], "min": 1, "max": 3, "scale_up_at": 20, "scale_down_at": 2},
}


async def is_autoscale_enabled() -> bool:
    r = await _get_async_redis()
    if r is None:
        return False
    try:
        val = await r.get(AUTOSCALE_KEY)
        return val == "true"
    except Exception:
        return False


async def set_autoscale_enabled(enabled: bool) -> bool:
    r = await _get_async_redis()
    if r is None:
        return False
    try:
        await r.set(AUTOSCALE_KEY, "true" if enabled else "false")
        logger.info("autoscale_toggled", enabled=enabled)
        return True
    except Exception:
        return False


async def run_autoscale_check() -> dict[str, Any]:
    enabled = await is_autoscale_enabled()
    if not enabled:
        return {"skipped": True, "reason": "autoscale disabled"}

    queue_stats = await get_queue_stats()
    queue_map = {q["name"]: q["messages"] for q in queue_stats}

    docker_status = await get_docker_status()
    current_replicas: dict[str, int] = {}
    if isinstance(docker_status, dict) and "error" not in docker_status:
        for svc, containers in docker_status.items():
            if isinstance(containers, list):
                current_replicas[svc] = len(containers)

    policy = DEFAULT_AUTOSCALE_POLICY
    decisions: list[dict[str, Any]] = []

    for svc, cfg in policy.items():
        total_depth = sum(queue_map.get(q, 0) for q in cfg["queues"])
        current = current_replicas.get(svc, 0)
        min_r = cfg["min"]
        max_r = cfg["max"]

        desired = current
        if total_depth > cfg["scale_up_at"]:
            desired = min(max_r, max(min_r, (total_depth // cfg["scale_up_at"]) + 1))
        elif total_depth < cfg["scale_down_at"]:
            desired = min_r

        if desired != current and desired > 0:
            decisions.append({
                "service": svc,
                "current": current,
                "desired": desired,
                "queue_depth": total_depth,
                "action": "scale_up" if desired > current else "scale_down",
            })
            result = await send_docker_command("scale", {"service": svc, "replicas": desired})
            decisions[-1]["result"] = result.get("success", False)

    log_entry = {
        "timestamp": time.time(),
        "decisions": decisions,
        "queue_depths": queue_map,
    }

    r = await _get_async_redis()
    if r is not None:
        try:
            await r.lpush(AUTOSCALE_LOG_KEY, json.dumps(log_entry))
            await r.ltrim(AUTOSCALE_LOG_KEY, 0, 99)
        except Exception:
            pass

    return {"checked": len(policy), "decisions": decisions}


# ── Celery Events Consumer + Dead Worker Detection ───────────────────────────

_EVENTS_REDIS_KEY = "admin:worker:events"
_EVENTS_TTL = 3600
_HEARTBEAT_TRACK_KEY = "admin:worker:heartbeats"
_DEAD_THRESHOLD_SECONDS = 120


async def start_events_consumer() -> None:
    try:
        from services.scraper.celery_app import celery_app
    except Exception as exc:
        logger.warning("events_consumer_cannot_start", error=str(exc)[:200])
        return

    def on_event(event: dict) -> None:
        try:
            import asyncio as _aio
            loop = _aio.new_event_loop()
            loop.run_until_complete(_store_event(event))
            loop.close()
        except Exception:
            pass

    try:
        with celery_app.connection() as conn:
            recv = celery_app.events.Receiver(
                conn,
                handlers={
                    "worker-online": on_event,
                    "worker-offline": on_event,
                    "worker-heartbeat": on_event,
                    "task-started": on_event,
                    "task-succeeded": on_event,
                    "task-failed": on_event,
                    "task-retried": on_event,
                    "*": on_event,
                },
            )
            logger.info("celery_events_consumer_started")
            recv.capture(limit=None, timeout=None, wakeup=True)
    except Exception as exc:
        logger.warning("events_consumer_stopped", error=str(exc)[:200])


async def _store_event(event: dict) -> None:
    r = await _get_async_redis()
    if r is None:
        return

    event_type = event.get("type", "unknown")
    hostname = event.get("hostname", "")
    timestamp = event.get("timestamp", time.time())

    entry = {
        "type": event_type,
        "hostname": hostname,
        "timestamp": timestamp,
        "processed_at": time.time(),
    }

    if event_type.startswith("task-"):
        entry["task_id"] = event.get("uuid", "")
        entry["task_name"] = event.get("name", "")

    try:
        await r.lpush(_EVENTS_REDIS_KEY, json.dumps(entry))
        await r.ltrim(_EVENTS_REDIS_KEY, 0, 999)
        await r.expire(_EVENTS_REDIS_KEY, _EVENTS_TTL)
    except Exception:
        pass

    if event_type == "worker-heartbeat" and hostname:
        try:
            await r.hset(_HEARTBEAT_TRACK_KEY, hostname, str(timestamp))
            await r.expire(_HEARTBEAT_TRACK_KEY, 86400)
        except Exception:
            pass


async def get_recent_events(limit: int = 50) -> list[dict[str, Any]]:
    r = await _get_async_redis()
    if r is None:
        return []
    try:
        raw = await r.lrange(_EVENTS_REDIS_KEY, 0, limit - 1)
        return [json.loads(e) for e in raw if e]
    except Exception:
        return []


async def detect_dead_workers() -> list[dict[str, Any]]:
    r = await _get_async_redis()
    if r is None:
        return []

    try:
        heartbeats = await r.hgetall(_HEARTBEAT_TRACK_KEY)
    except Exception:
        return []

    now = time.time()
    dead: list[dict[str, Any]] = []

    for hostname, last_ts_str in heartbeats.items():
        try:
            last_ts = float(last_ts_str)
        except (ValueError, TypeError):
            continue

        silence = now - last_ts
        if silence > _DEAD_THRESHOLD_SECONDS:
            dead.append({
                "hostname": hostname,
                "last_heartbeat_ago_seconds": round(silence),
                "status": "dead",
            })
        elif silence > 60:
            dead.append({
                "hostname": hostname,
                "last_heartbeat_ago_seconds": round(silence),
                "status": "suspect",
            })

    return dead


async def get_cover_letter_status() -> dict[str, Any]:
    """Get real-time cover letter freshness status across all jobs.

    Returns counts of fresh, stale, and missing cover letters per candidate.
    - Fresh: cover_letter_generated_at >= candidate.updated_at
    - Stale: cover_letter_generated_at < candidate.updated_at (candidate template changed after cover was generated)
    - Missing: cover_letter IS NULL OR cover_letter_generated_at IS NULL
    """
    SKIP_STATUSES = ["sent", "bounced", "error"]

    try:
        from sqlalchemy import Integer, func, select
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            # Get total count of non-terminal jobs
            total_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
            )
            total_jobs = total_result.scalar() or 0

            # Get count of jobs with missing covers
            missing_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
                .where(
                    (Job.cover_letter.is_(None)) |
                    (Job.cover_letter_generated_at.is_(None))
                )
            )
            missing_covers = missing_result.scalar() or 0

            # Get count of fresh covers (generated_at >= candidate.updated_at)
            fresh_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
                .where(Job.cover_letter.isnot(None))
                .where(Job.cover_letter_generated_at.isnot(None))
                .where(Job.candidate_id.isnot(None))
                .where(Candidate.id == Job.candidate_id)
                .where(Job.cover_letter_generated_at >= Candidate.updated_at)
            )
            fresh_covers = fresh_result.scalar() or 0

            # Get count of stale covers (generated_at < candidate.updated_at)
            stale_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
                .where(Job.cover_letter.isnot(None))
                .where(Job.cover_letter_generated_at.isnot(None))
                .where(Job.candidate_id.isnot(None))
                .where(Candidate.id == Job.candidate_id)
                .where(Job.cover_letter_generated_at < Candidate.updated_at)
            )
            stale_covers = stale_result.scalar() or 0

            # Get per-candidate breakdown
            candidate_stats_result = await session.execute(
                select(
                    Candidate.id,
                    Candidate.name,
                    func.count(Job.id).label("total"),
                    func.sum(
                        (Job.cover_letter.is_(None) | Job.cover_letter_generated_at.is_(None)).cast(Integer)
                    ).label("missing"),
                    func.sum(
                        (Job.cover_letter.isnot(None) & Job.cover_letter_generated_at.isnot(None) &
                         Job.candidate_id.isnot(None) & (Job.cover_letter_generated_at < Candidate.updated_at)).cast(Integer)
                    ).label("stale"),
                )
                .join(Job, Job.candidate_id == Candidate.id)
                .where(Job.status.notin_(SKIP_STATUSES))
                .group_by(Candidate.id, Candidate.name)
            )

            by_candidate = []
            for row in candidate_stats_result.all():
                candidate_total = row.total or 0
                candidate_missing = row.missing or 0
                candidate_stale = row.stale or 0
                candidate_fresh = candidate_total - candidate_missing - candidate_stale

                by_candidate.append({
                    "candidate_id": row.id,
                    "candidate_name": row.name,
                    "total": candidate_total,
                    "fresh": candidate_fresh,
                    "stale": candidate_stale,
                    "missing": candidate_missing,
                })

        # Calculate percentages
        checked_jobs = total_jobs
        stale_percentage = (stale_covers / checked_jobs * 100) if checked_jobs > 0 else 0
        missing_percentage = (missing_covers / checked_jobs * 100) if checked_jobs > 0 else 0

        return {
            "total_jobs": total_jobs,
            "fresh_covers": fresh_covers,
            "stale_covers": stale_covers,
            "missing_covers": missing_covers,
            "stale_percentage": round(stale_percentage, 2),
            "missing_percentage": round(missing_percentage, 2),
            "candidates_with_jobs": len(by_candidate),
            "by_candidate": by_candidate,
        }
    except Exception as exc:
        logger.error("get_cover_letter_status_failed", error=str(exc))
        return {
            "error": str(exc),
            "total_jobs": 0,
            "fresh_covers": 0,
            "stale_covers": 0,
            "missing_covers": 0,
            "stale_percentage": 0,
            "missing_percentage": 0,
            "candidates_with_jobs": 0,
            "by_candidate": [],
        }
