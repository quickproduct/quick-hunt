#!/usr/bin/env python3
"""Queue-depth-based auto-scaler for Celery workers.

Monitors RabbitMQ queue depths via the Management API and scales Docker
Compose worker services up/down based on configurable thresholds.

Usage:
    # Dry run (show what would change)
    python infra/autoscale_workers.py --dry-run

    # Apply scaling changes
    python infra/autoscale_workers.py

    # Custom config file
    python infra/autoscale_workers.py --config infra/autoscale.yml

    # One-shot check (no loop)
    python infra/autoscale_workers.py --once

Requires: requests, pyyaml
    pip install requests pyyaml

Environment variables (or autoscale.yml):
    RABBITMQ_MANAGEMENT_URL  — e.g. http://jobhunter:jobhunter@localhost:15672
    SCALE_UP_THRESHOLD       — queue depth to trigger scale-up (default: 50)
    SCALE_DOWN_THRESHOLD     — queue depth to trigger scale-down (default: 5)
    CHECK_INTERVAL_SECONDS   — seconds between checks (default: 60)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


# ── Default scaling policy ──────────────────────────────────────────────────
# Maps Docker Compose service names to their queue subscriptions and
# min/max replica bounds.  The scaler adjusts `docker compose up -d
# --scale <service>=N` within these bounds.
#
# IMPORTANT: Queue names here MUST match the Celery task routing in
# backend/services/scraper/celery_app.py → task_routes dict.
# Service names MUST match infra/docker-compose.yml service names.
DEFAULT_POLICY = {
    "worker-scraping-bulk": {
        "queues": ["jh_scraping_bulk"],
        "min_replicas": 1,
        "max_replicas": 5,
        "scale_up_at": 50,
        "scale_down_at": 5,
    },
    "worker-scraping-realtime": {
        "queues": ["jh_scraping_realtime"],
        "min_replicas": 2,
        "max_replicas": 8,
        "scale_up_at": 30,
        "scale_down_at": 3,
    },
    "worker-enrichment": {
        "queues": ["jh_scraping_enrichment"],
        "min_replicas": 1,
        "max_replicas": 5,
        "scale_up_at": 40,
        "scale_down_at": 5,
    },
    "worker-maintenance": {
        "queues": ["jh_jobs_maintenance"],
        "min_replicas": 1,
        "max_replicas": 3,
        "scale_up_at": 100,
        "scale_down_at": 10,
    },
    "worker-cover-bulk": {
        "queues": ["jh_cover_letter_bulk"],
        "min_replicas": 1,
        "max_replicas": 4,
        "scale_up_at": 100,
        "scale_down_at": 10,
    },
    "worker-cover-ranking": {
        "queues": ["jh_cover_letter_ranking"],
        "min_replicas": 1,
        "max_replicas": 4,
        "scale_up_at": 50,
        "scale_down_at": 5,
    },
    "worker-cover-generation": {
        "queues": ["jh_cover_letter_generation"],
        "min_replicas": 2,
        "max_replicas": 6,
        "scale_up_at": 50,
        "scale_down_at": 5,
    },
    "worker-cover-workflow": {
        "queues": ["jh_cover_letter_workflow"],
        "min_replicas": 1,
        "max_replicas": 4,
        "scale_up_at": 30,
        "scale_down_at": 3,
    },
    "worker-email": {
        "queues": ["jh_email_send", "jh_email_retry"],
        "min_replicas": 1,
        "max_replicas": 3,
        "scale_up_at": 20,
        "scale_down_at": 2,
    },
}


def get_rabbitmq_queues(management_url: str) -> dict[str, int]:
    """Fetch queue depths from RabbitMQ Management API.

    Returns dict mapping queue name → message count.
    """
    # management_url is like http://user:pass@host:15672
    api_url = f"{management_url}/api/queues"
    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        queues = resp.json()
        return {q["name"]: q.get("messages", 0) for q in queues}
    except Exception as e:
        print(f"ERROR: Failed to fetch RabbitMQ queues: {e}", file=sys.stderr)
        return {}


def get_current_replicas(compose_dir: str) -> dict[str, int]:
    """Get current replica counts for all worker services via docker compose ps."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {}

        replicas: dict[str, int] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                svc = json.loads(line)
                name = svc.get("Service", svc.get("service", ""))
                if name:
                    replicas[name] = replicas.get(name, 0) + 1
            except json.JSONDecodeError:
                continue
        return replicas
    except Exception as e:
        print(f"ERROR: Failed to get current replicas: {e}", file=sys.stderr)
        return {}


def calculate_desired_replicas(
    policy: dict,
    queue_depths: dict[str, int],
) -> dict[str, int]:
    """Calculate desired replica count for each service based on queue depths."""
    desired = {}
    for service, config in policy.items():
        queues = config["queues"]
        min_rep = config["min_replicas"]
        max_rep = config["max_replicas"]
        scale_up_at = config["scale_up_at"]
        scale_down_at = config["scale_down_at"]

        # Sum messages across all queues for this service
        total_depth = sum(queue_depths.get(q, 0) for q in queues)

        if total_depth > scale_up_at:
            # Scale up: 1 replica per scale_up_at messages, capped at max
            target = min(max_rep, max(min_rep, (total_depth // scale_up_at) + 1))
        elif total_depth < scale_down_at:
            # Scale down to minimum
            target = min_rep
        else:
            # Keep current — we'll handle this in the main loop
            target = -1  # sentinel: don't change

        desired[service] = target
    return desired


def scale_service(
    compose_dir: str,
    service: str,
    replicas: int,
    dry_run: bool = False,
) -> bool:
    """Scale a Docker Compose service to the given replica count."""
    cmd = [
        "docker", "compose",
        "up", "-d",
        f"--scale={service}={replicas}",
        service,
    ]
    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(cmd)}")
        return True

    try:
        result = subprocess.run(
            cmd,
            cwd=compose_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  ✓ Scaled {service} to {replicas} replicas")
            return True
        else:
            print(f"  ✗ Failed to scale {service}: {result.stderr}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"  ✗ Error scaling {service}: {e}", file=sys.stderr)
        return False


def run_scaler(
    management_url: str,
    policy: dict,
    compose_dir: str,
    interval: int = 60,
    dry_run: bool = False,
    once: bool = False,
) -> None:
    """Main scaler loop."""
    while True:
        print(f"\n{'='*60}")
        print(f"Auto-scaler check at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # 1. Get queue depths
        queue_depths = get_rabbitmq_queues(management_url)
        if not queue_depths:
            print("No queue data available, skipping...")
            if once:
                break
            time.sleep(interval)
            continue

        print(f"\nQueue depths:")
        for q, depth in sorted(queue_depths.items()):
            if depth > 0:
                print(f"  {q}: {depth} messages")

        # 2. Get current replicas
        current = get_current_replicas(compose_dir)
        print(f"\nCurrent replicas:")
        for svc in policy:
            print(f"  {svc}: {current.get(svc, 0)}")

        # 3. Calculate desired
        desired = calculate_desired_replicas(policy, queue_depths)

        # 4. Apply scaling
        print(f"\nScaling decisions:")
        any_changed = False
        for service, target in desired.items():
            curr = current.get(service, 0)
            if target == -1:
                print(f"  {service}: no change (depth in normal range, current={curr})")
                continue
            if target == curr:
                print(f"  {service}: no change (already at {curr})")
                continue

            print(f"  {service}: {curr} → {target}")
            scale_service(compose_dir, service, target, dry_run=dry_run)
            any_changed = True

        if not any_changed:
            print("  No scaling changes needed")

        if once:
            break

        time.sleep(interval)


def load_config(config_path: str | None) -> dict:
    """Load scaling policy from YAML config file if provided."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Celery worker auto-scaler")
    parser.add_argument("--dry-run", action="store_true", help="Show scaling decisions without applying")
    parser.add_argument("--once", action="store_true", help="Single check, no loop")
    parser.add_argument("--config", type=str, help="Path to autoscale.yml config")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    args = parser.parse_args()

    # Resolve RabbitMQ Management URL
    mgmt_url = os.environ.get(
        "RABBITMQ_MANAGEMENT_URL",
        "http://jobhunter:jobhunter@localhost:15672",
    )

    # Load config
    user_config = load_config(args.config)
    policy = user_config.get("policy", DEFAULT_POLICY)

    # Override thresholds from env vars if set
    global_up = int(os.environ.get("SCALE_UP_THRESHOLD", "0"))
    global_down = int(os.environ.get("SCALE_DOWN_THRESHOLD", "0"))
    if global_up:
        for svc in policy.values():
            svc["scale_up_at"] = global_up
    if global_down:
        for svc in policy.values():
            svc["scale_down_at"] = global_down

    interval = int(os.environ.get("CHECK_INTERVAL_SECONDS", str(args.interval)))

    compose_dir = str(Path(__file__).parent)

    print(f"Auto-scaler starting")
    print(f"  RabbitMQ: {mgmt_url.split('@')[-1] if '@' in mgmt_url else mgmt_url}")
    print(f"  Interval: {interval}s")
    print(f"  Dry run:  {args.dry_run}")
    print(f"  Services: {len(policy)}")

    run_scaler(
        management_url=mgmt_url,
        policy=policy,
        compose_dir=compose_dir,
        interval=interval,
        dry_run=args.dry_run,
        once=args.once,
    )


if __name__ == "__main__":
    main()