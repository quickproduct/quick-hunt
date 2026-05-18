#!/usr/bin/env python3
"""Apply worker.config.yml settings to infra/.env and optionally restart containers.

Usage:
    python infra/apply_worker_config.py            # update .env only
    python infra/apply_worker_config.py --restart  # update .env + restart containers
    python infra/apply_worker_config.py --dry-run  # preview changes without writing
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "worker.config.yml"
ENV_FILE = SCRIPT_DIR / ".env"

# Maps worker.config.yml key → (docker-compose service name, env var prefix)
# These MUST match the service names in docker-compose.yml exactly.
WORKER_GROUPS = {
    "scraping_bulk":     ("worker-scraping-bulk",      "WORKER_SCRAPING_BULK"),
    "scraping_realtime": ("worker-scraping-realtime",   "WORKER_SCRAPING_REALTIME"),
    "enrichment":        ("worker-enrichment",          "WORKER_ENRICHMENT"),
    "maintenance":       ("worker-maintenance",         "WORKER_MAINTENANCE"),
    "cover_bulk":        ("worker-cover-bulk",          "WORKER_COVER_BULK"),
    "cover_ranking":     ("worker-cover-ranking",       "WORKER_COVER_RANKING"),
    "cover_generation":  ("worker-cover-generation",    "WORKER_COVER_GENERATION"),
    "cover_workflow":    ("worker-cover-workflow",       "WORKER_COVER_WORKFLOW"),
    "email":             ("worker-email",               "WORKER_EMAIL"),
    "cover_batch":       ("worker-cover-batch",         "WORKER_COVER_BATCH"),
}

# ANSI colours
_use_colour = sys.stdout.isatty() and os.name != "nt"
GREEN  = "\033[32m" if _use_colour else ""
YELLOW = "\033[33m" if _use_colour else ""
GREY   = "\033[90m" if _use_colour else ""
RESET  = "\033[0m"  if _use_colour else ""
BOLD   = "\033[1m"  if _use_colour else ""


# ── Validation ────────────────────────────────────────────────────────────────
_VALID_LOG_LEVELS    = {"DEBUG", "INFO", "WARNING", "ERROR"}
_VALID_BROKER_PRIMARY = {"rabbitmq", "redis"}


def _err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def validate(cfg: dict) -> None:
    workers = cfg.get("workers", {})
    if not workers:
        _err("workers section is empty — define at least one worker group")

    for key, group in workers.items():
        scale       = group.get("scale", 1)
        concurrency = group.get("concurrency", 1)
        queues      = group.get("queues", [])
        if not isinstance(scale, int) or scale < 1:
            _err(f"workers.{key}.scale must be an integer ≥ 1 (got {scale!r})")
        if not isinstance(concurrency, int) or concurrency < 1:
            _err(f"workers.{key}.concurrency must be an integer ≥ 1 (got {concurrency!r})")
        if not queues or not isinstance(queues, list):
            _err(f"workers.{key}.queues must be a non-empty list")
        if key not in WORKER_GROUPS:
            _err(f"Unknown worker group '{key}'. Valid groups: {list(WORKER_GROUPS)}")

    b       = cfg.get("broker", {})
    primary = b.get("primary", "rabbitmq")
    pool    = b.get("pool_limit", 3)
    if primary not in _VALID_BROKER_PRIMARY:
        _err(f"broker.primary must be one of {_VALID_BROKER_PRIMARY} (got {primary!r})")
    if not isinstance(pool, int) or pool < 1:
        _err(f"broker.pool_limit must be an integer ≥ 1 (got {pool!r})")

    t    = cfg.get("tasks", {})
    soft = t.get("soft_time_limit", 600)
    hard = t.get("hard_time_limit", 720)
    pre  = t.get("prefetch_multiplier", 4)
    if not isinstance(soft, int) or soft < 1:
        _err(f"tasks.soft_time_limit must be an integer ≥ 1 (got {soft!r})")
    if not isinstance(hard, int) or hard < 1:
        _err(f"tasks.hard_time_limit must be an integer ≥ 1 (got {hard!r})")
    if hard <= soft:
        _err(f"tasks.hard_time_limit ({hard}) must be > soft_time_limit ({soft})")
    if not isinstance(pre, int) or pre < 1:
        _err(f"tasks.prefetch_multiplier must be an integer ≥ 1 (got {pre!r})")

    log_level = cfg.get("logging", {}).get("level", "INFO").upper()
    if log_level not in _VALID_LOG_LEVELS:
        _err(f"logging.level must be one of {_VALID_LOG_LEVELS} (got {log_level!r})")


# ── Connection budget check ───────────────────────────────────────────────────
def _check_connection_budget(cfg: dict) -> None:
    """Warn if estimated AMQP connections exceed CloudAMQP free tier (20 limit)."""
    workers = cfg.get("workers", {})
    # Each container: 1 main process + concurrency pool connections
    worker_conns = sum(
        g.get("scale", 1) * (1 + g.get("concurrency", 1))
        for g in workers.values()
    )
    overhead = 5  # beat(1) + flower(1) + api-pool(3)
    total = worker_conns + overhead
    if total > 20:
        print(f"\n  {YELLOW}⚠ WARNING: Estimated AMQP connections = {total} (CloudAMQP free tier cap = 20){RESET}")
        print(f"  {YELLOW}  Worker connections: {worker_conns}  Overhead: {overhead}{RESET}")
        print(f"  {YELLOW}  Reduce scale or concurrency to stay under the limit.{RESET}\n")
    else:
        print(f"  {GREY}Connection budget: ~{total}/20 AMQP connections{RESET}")


# ── Config → env vars mapping ─────────────────────────────────────────────────
def _sec(value: int, multiplier: int) -> int:
    """Convert a time value to seconds by multiplying with the given multiplier."""
    return value * multiplier

def build_env_vars(cfg: dict) -> dict[str, str]:
    workers = cfg.get("workers", {})
    b  = cfg.get("broker", {})
    t  = cfg.get("tasks", {})
    bs = cfg.get("beat_schedule", {})
    lg = cfg.get("logging", {})

    broker_primary = b.get("primary", "rabbitmq")
    if broker_primary == "rabbitmq":
        effective_weight = 100
    env: dict[str, str] = {}

    # Per-worker-group env vars
    for key, group in workers.items():
        _, env_prefix = WORKER_GROUPS[key]
        env[f"{env_prefix}_SCALE"]       = str(group.get("scale", 1))
        env[f"{env_prefix}_CONCURRENCY"] = str(group.get("concurrency", 2))
        env[f"{env_prefix}_QUEUES"]      = ",".join(group.get("queues", [key]))

    # Broker
    env["RABBITMQ_WEIGHT"]          = str(effective_weight)
    env["BROKER_POOL_LIMIT"]        = str(b.get("pool_limit", 3))

    # Task tuning
    env["WORKER_PREFETCH_MULTIPLIER"] = str(t.get("prefetch_multiplier", 4))
    env["TASK_SOFT_TIME_LIMIT"]       = str(t.get("soft_time_limit", 600))
    env["TASK_TIME_LIMIT"]            = str(t.get("hard_time_limit", 720))

    # Beat schedule
    env["BEAT_SCRAPE_INTERVAL"]           = str(_sec(bs.get("scrape_interval_hours", 3), 3600))
    env["BEAT_REFRESH_COVERS_INTERVAL"]   = str(_sec(bs.get("refresh_covers_interval_hours", 4), 3600))
    env["BEAT_FILL_COVERS_INTERVAL"]      = str(_sec(bs.get("fill_missing_covers_interval_minutes", 15), 60))
    env["BEAT_PURGE_INTERVAL"]            = str(_sec(bs.get("purge_irrelevant_interval_minutes", 15), 60))
    env["BEAT_RETRY_SENDS_INTERVAL"]      = str(_sec(bs.get("retry_failed_sends_interval_minutes", 30), 60))
    env["BEAT_CLEANUP_INTERVAL"]          = str(_sec(bs.get("cleanup_old_jobs_interval_days", 7), 86400))
    env["BEAT_FIX_PLACEHOLDER_INTERVAL"] = str(_sec(bs.get("fix_placeholder_emails_interval_minutes", 30), 60))
    env["BEAT_DEDUPLICATE_INTERVAL"]     = str(_sec(bs.get("deduplicate_interval_minutes", 5), 60))
    env["BEAT_DISPATCH_READY_INTERVAL"]  = str(_sec(bs.get("dispatch_ready_interval_minutes", 5), 60))
    env["BEAT_AUTO_APPROVE_INTERVAL"]    = str(_sec(bs.get("auto_approve_interval_minutes", 10), 60))
    env["BEAT_COVER_READY_HR_INTERVAL"]  = str(_sec(bs.get("cover_ready_hr_fetch_interval_minutes", 5), 60))

    # Logging
    env["LOG_LEVEL"] = lg.get("level", "INFO").upper()

    return env


# ── .env read / write ─────────────────────────────────────────────────────────
_BLOCK_HEADER = "# ── Worker Config (managed by worker.config.yml) ──"
_BLOCK_FOOTER = "# ── End Worker Config ──"


def read_env(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def apply_env_vars(env_text: str, new_vars: dict[str, str]) -> tuple[str, list[tuple]]:
    changes   = []
    lines     = env_text.splitlines(keepends=True)
    remaining = dict(new_vars)

    updated_lines = []
    for line in lines:
        m = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', line.rstrip("\n\r"))
        if m and m.group(1) in remaining:
            key, old_val = m.group(1), m.group(2)
            new_val = remaining.pop(key)
            if old_val != new_val:
                changes.append((key, old_val, new_val))
                updated_lines.append(f"{key}={new_val}\n")
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    result = "".join(updated_lines)

    if remaining:
        result = re.sub(
            rf"{re.escape(_BLOCK_HEADER)}.*?{re.escape(_BLOCK_FOOTER)}\n?",
            "",
            result,
            flags=re.DOTALL,
        )
        result = result.rstrip("\n") + "\n\n"
        block  = [_BLOCK_HEADER + "\n"]
        for key, val in remaining.items():
            changes.append((key, None, val))
            block.append(f"{key}={val}\n")
        block.append(_BLOCK_FOOTER + "\n")
        result += "".join(block)

    return result, changes


# ── Scale detection ───────────────────────────────────────────────────────────
def get_current_scale(service: str) -> int:
    try:
        out = subprocess.check_output(
            ["docker", "compose", "ps", "--quiet", service],
            cwd=SCRIPT_DIR,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return len([l for l in out.strip().splitlines() if l.strip()])
    except Exception:
        return 0


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Apply worker.config.yml to infra/.env")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--restart", action="store_true", help="Restart affected containers after applying")
    args = parser.parse_args()

    if not CONFIG_FILE.exists():
        _err(f"Config file not found: {CONFIG_FILE}")
    with CONFIG_FILE.open() as f:
        cfg = yaml.safe_load(f)
    if not cfg:
        _err("worker.config.yml is empty or invalid")

    validate(cfg)

    new_vars     = build_env_vars(cfg)
    env_text     = read_env(ENV_FILE)
    updated_text, changes = apply_env_vars(env_text, new_vars)

    # ── Print summary ─────────────────────────────────────────────────────
    print(f"\n{BOLD}Worker Config → .env{RESET}  ({CONFIG_FILE.name})\n")

    _check_connection_budget(cfg)
    print()

    if not changes:
        print(f"{GREY}  No env changes — .env is already up to date.{RESET}")
    else:
        for key, old, new in changes:
            if old is None:
                print(f"  {GREEN}+ {key}={new}{RESET}  {GREY}(new){RESET}")
            else:
                print(f"  {YELLOW}~ {key}{RESET}  {GREY}{old}{RESET} → {GREEN}{new}{RESET}")

    # Scale changes
    workers      = cfg.get("workers", {})
    scale_changes = []
    for key, group in workers.items():
        svc, _     = WORKER_GROUPS[key]
        desired    = group.get("scale", 1)
        current    = get_current_scale(svc)
        if current != desired:
            scale_changes.append((svc, current, desired))
            print(f"  {YELLOW}~ {svc} scale:{RESET}  {current} → {desired}")

    if args.dry_run:
        print(f"\n{GREY}Dry run — no files written.{RESET}\n")
        return

    # ── Write .env ────────────────────────────────────────────────────────
    if changes:
        ENV_FILE.write_text(updated_text, encoding="utf-8")
        print(f"\n{GREEN}✓ {ENV_FILE} updated ({len(changes)} change(s)){RESET}")
    else:
        print(f"\n{GREY}✓ {ENV_FILE} unchanged{RESET}")

    # ── Restart ───────────────────────────────────────────────────────────
    if args.restart:
        if changes or scale_changes:
            print(f"\n  Restarting workers and beat...")

            # Build scale flags for all worker groups
            scale_flags = []
            for key, group in workers.items():
                svc, _ = WORKER_GROUPS[key]
                scale_flags += ["--scale", f"{svc}={group.get('scale', 1)}"]

            all_services = [WORKER_GROUPS[k][0] for k in workers] + ["beat"]
            cmd = ["docker", "compose", "up", "-d"] + scale_flags + all_services
            result = subprocess.run(cmd, cwd=SCRIPT_DIR)
            if result.returncode != 0:
                print(f"\n{YELLOW}WARNING: docker compose returned exit code {result.returncode}{RESET}")
            else:
                print(f"\n{GREEN}✓ Containers restarted{RESET}")
        else:
            print(f"{GREY}  No changes — skipping restart.{RESET}")
    else:
        if changes or scale_changes:
            scale_flags = " ".join(
                f"--scale {WORKER_GROUPS[k][0]}={g.get('scale',1)}"
                for k, g in workers.items()
            )
            all_services = " ".join(WORKER_GROUPS[k][0] for k in workers)
            print(f"\n{GREY}Tip: run with --restart to apply changes.")
            print(f"Manual: cd infra && docker compose up -d {scale_flags} {all_services} beat{RESET}")

    print()


if __name__ == "__main__":
    main()
