#!/usr/bin/env python3
"""
run_task.py — manually trigger any Celery task from the host.

Usage:
  ./run_task.py                        # interactive menu
  ./run_task.py scheduled_scrape       # run by name directly
  ./run_task.py scrape_portal naukri <candidate_id>
  ./run_task.py --list                 # list all tasks
"""

import argparse
import json
import re
import subprocess
import sys

# ── Colour helpers ─────────────────────────────────────────────────────────────
R = "\033[0;31m"; G = "\033[0;32m"; Y = "\033[1;33m"
B = "\033[0;34m"; C = "\033[0;36m"; W = "\033[1m"; N = "\033[0m"

def red(s): return f"{R}{s}{N}"
def grn(s): return f"{G}{s}{N}"
def yel(s): return f"{Y}{s}{N}"
def blu(s): return f"{B}{s}{N}"
def cyn(s): return f"{C}{s}{N}"
def bld(s): return f"{W}{s}{N}"

# ── Task catalogue ─────────────────────────────────────────────────────────────
# key → (celery_path, queue, [arg_names], description, cron_schedule)
TASKS = {
    # ── Scraping ──────────────────────────────────────────────────────────────
    "scheduled_scrape": (
        "services.scraper.tasks.scheduled_scrape",
        "jh_scraping_bulk", [],
        "Scrape ALL portals for all candidates (Naukri, Indeed, Glassdoor, LinkedIn, AngelList)",
        "0 */2 * * *",                    # Every 2 hours: 12AM, 2AM, 4AM, 6AM, 8AM, 10AM, 12PM, 2PM, 4PM, 6PM, 8PM, 10PM
    ),
    "scrape_portal": (
        "services.scraper.tasks.scrape_portal_task",
        "jh_scraping_realtime", ["portal_name", "candidate_id"],
        "Scrape a single portal  [portal: naukri|indeed|glassdoor|linkedin|angellist]",
        "On-demand",
    ),
    "backfill_hr_emails": (
        "services.scraper.tasks.backfill_hr_emails_task",
        "jh_scraping_enrichment", [],
        "Backfill missing HR emails — priority: cover_generated → current-month → rest (batch 100)",
        "1,6,11,16,21,26,31,36,41,46,51,56 * * * *",  # Every 5 min, offset :01 to stagger
    ),
    "fix_placeholder_emails": (
        "services.scraper.tasks.fix_placeholder_emails_task",
        "jh_scraping_enrichment", [],
        "Replace Indeed placeholder emails with real HR contacts",
        "*/30 * * * *",                   # Every 30 min
    ),
    "deduplicate_jobs": (
        "services.scraper.tasks.deduplicate_jobs_task",
        "jh_jobs_maintenance", [],
        "Remove duplicate job listings (advisory lock + CTE, keeps highest-status row)",
        "0,5,10,15,20,25,30,35,40,45,50,55 * * * *",  # Every 5 min, offset :00
    ),
    "cleanup_old_jobs": (
        "services.scraper.tasks.cleanup_old_jobs_task",
        "jh_jobs_maintenance", [],
        "Delete terminal-status jobs older than 30 days",
        "0 5 * * 0",                      # Weekly Sunday 5AM
    ),
    "pipeline_health_check": (
        "services.scraper.tasks.pipeline_health_check_task",
        "jh_jobs_maintenance", [],
        "Detect and auto-fix pipeline stalls (stuck scoring, send-ready count)",
        "4,19,34,49 * * * *",             # Every 15 min, offset :04
    ),
    "stale_lock_reaper": (
        "services.scraper.tasks.stale_lock_reaper_task",
        "jh_jobs_maintenance", [],
        "Clean up orphaned Redis cron locks (cron:lock:* keys with no TTL)",
        "3,13,23,33,43,53 * * * *",       # Every 10 min, offset :03
    ),

    # ── AI / Cover Letters ────────────────────────────────────────────────────
    "fill_missing_covers": (
        "services.ai.tasks.fill_missing_covers_task",
        "jh_cover_letter_bulk", [],
        "Generate covers — tier1: jobs with hr_email (current month), tier2: all others (batch 50)",
        "2,7,12,17,22,27,32,37,42,47,52,57 * * * *",  # Every 5 min, offset :02
    ),
    "refresh_cover_letters": (
        "services.ai.tasks.refresh_cover_letters_task",
        "jh_cover_letter_bulk", [],
        "Re-generate stale cover letters with the latest template",
        "0 3 * * 0",                      # Weekly Sunday 3AM
    ),
    "rank_jobs": (
        "services.ai.tasks.rank_jobs_task",
        "jh_cover_letter_ranking", ["candidate_id"],
        "Score & rank all jobs for a specific candidate",
        "*/10 * * * *",                   # Every 10 min - fast ranking
    ),
    "generate_cover_letter": (
        "services.ai.tasks.generate_cover_letter_task",
        "jh_cover_letter_generation", ["job_id", "candidate_id"],
        "Generate cover letter for one job + candidate pair",
        "On-demand",
    ),
    "run_application_workflow": (
        "services.ai.tasks.run_application_workflow_task",
        "jh_cover_letter_workflow", ["job_id", "candidate_id"],
        "Full workflow: rank → cover letter → queue email for one job",
        "*/3 * * * *",                    # Every 3 min - rapid application sending
    ),

    # ── Email / Sending ───────────────────────────────────────────────────────
    "dispatch_ready_to_send": (
        "services.sender.tasks.dispatch_ready_to_send_task",
        "jh_email_send", [],
        "Dispatch jobs ready to send (cover_generated + hr_email) into email pipeline",
        "*/5 * * * *",                    # Every 5 min - pump jobs into email queue
    ),
    "auto_approve_pending_jobs": (
        "services.sender.tasks.auto_approve_pending_jobs_task",
        "jh_email_send", [],
        "Auto-approve pending_approval jobs and dispatch for tenants with auto_send=True",
        "*/10 * * * *",                   # Every 10 min - unblock pending jobs
    ),
    "retry_failed_sends": (
        "services.sender.tasks.retry_failed_sends_task",
        "jh_email_retry", [],
        "Retry all failed / soft-bounced email sends",
        "*/10 * * * *",                   # Every 10 min
    ),

}

SECTIONS = [
    ("SCRAPING", ["scheduled_scrape", "scrape_portal", "backfill_hr_emails",
                  "fix_placeholder_emails", "purge_irrelevant_jobs",
                  "deduplicate_jobs", "cleanup_old_jobs"]),
    ("AI / COVER LETTERS", ["fill_missing_covers", "refresh_cover_letters",
                             "rank_jobs", "generate_cover_letter",
                             "run_application_workflow"]),
    ("MAINTENANCE", ["pipeline_health_check", "stale_lock_reaper"]),
    ("EMAIL", ["dispatch_ready_to_send", "auto_approve_pending_jobs", "retry_failed_sends"]),
]


def find_worker_container() -> str:
    """Return the name of a running worker container."""
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=infra-worker", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    containers = [c for c in result.stdout.strip().splitlines() if c]
    if not containers:
        sys.exit(red("No worker container found. Is the stack running?  →  cd infra && docker compose up -d"))
    return containers[0]


def dispatch(key: str, positional_args: list[str], container: str) -> None:
    path, queue, arg_names, desc, _ = TASKS[key]

    # Prompt for missing args interactively
    args = list(positional_args)
    for i, name in enumerate(arg_names):
        if i >= len(args):
            args.append(input(f"  Enter {bld(name)}: ").strip())

    args_json = json.dumps(args)

    print(f"\n{cyn('→')} Dispatching {bld(key)}")
    print(f"  Queue : {yel(queue)}")
    print(f"  Path  : {queue}")
    if args:
        print(f"  Args  : {args_json}")

    cmd = [
        "docker", "exec", container,
        "celery", "-A", "services.scraper.celery_app", "call",
        path,
        f"--args={args_json}",
        f"--queue={queue}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()

    task_id_match = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        output,
    )

    if result.returncode != 0 and not task_id_match:
        print(red(f"Error: {output}"))
        sys.exit(1)

    if task_id_match:
        task_id = task_id_match.group(0)
        print(grn(f"\n✓ Task queued successfully!"))
        print(f"  Task ID : {bld(task_id)}")
    else:
        print(yel("⚠ Task may be queued (no task ID returned)."))

    print(f"  Monitor : {cyn('http://localhost:5555')}  (Flower)")
    print(f"  Logs    : docker compose logs -f worker worker-cover worker-email\n")


def print_menu() -> None:
    print(f"\n{bld('╔══════════════════════════════════════════════════════════════╗')}")
    print(f"{bld('║         AI Job Hunter — Manual Task Runner                  ║')}")
    print(f"{bld('╚══════════════════════════════════════════════════════════════╝')}\n")

    num = 1
    menu_map: dict[int, str] = {}
    for section, keys in SECTIONS:
        print(blu(f"── {section} {'─' * (52 - len(section))}"))
        for k in keys:
            _, _, arg_names, desc, _ = TASKS[k]
            arg_hint = f"  {yel('[' + ', '.join(arg_names) + ']')}" if arg_names else ""
            print(f"  {yel(str(num).rjust(2))}  {bld(k.ljust(28))} {desc}{arg_hint}")
            menu_map[num] = k
            num += 1
        print()

    print(f"  {yel(' q')}  Quit\n")
    return menu_map


def interactive(container: str) -> None:
    while True:
        menu_map = print_menu()
        choice = input(bld("Select task (number or name): ")).strip()

        if choice.lower() == "q":
            print("Bye.")
            break

        key = None
        if choice.isdigit() and int(choice) in menu_map:
            key = menu_map[int(choice)]
        elif choice in TASKS:
            key = choice
        else:
            print(yel(f"⚠ Unknown choice '{choice}'"))
            continue

        dispatch(key, [], container)

        again = input(bld("Run another task? [y/N]: ")).strip().lower()
        if again != "y":
            print("Bye.")
            break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manually trigger any Celery task/cron.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            [f"  {k.ljust(30)} {v[3]}" for k, v in TASKS.items()]
        ),
    )
    parser.add_argument("task", nargs="?", help="Task name (omit for interactive menu)")
    parser.add_argument("args", nargs="*", help="Positional args for the task")
    parser.add_argument("--list", action="store_true", help="List all available tasks")
    ns = parser.parse_args()

    if ns.list:
        print(f"\n{'TASK'.ljust(32)} {'QUEUE'.ljust(14)} {'SCHEDULE'.ljust(16)} DESCRIPTION")
        print("─" * 100)
        for k, (_, q, args, desc, cron) in TASKS.items():
            arg_str = f"  [{', '.join(args)}]" if args else ""
            print(f"{bld(k.ljust(32))} {yel(q.ljust(14))} {cyn(cron.ljust(16))} {desc}{arg_str}")
        print(f"\n{cyn('ℹ')} All scheduled tasks have cron_safe validation enabled:")
        print(f"   • {yel('Singleton lock')} - Prevents overlapping executions")
        print(f"   • {yel('Rate limiting')} - Max runs per hour enforced")
        print(f"   • {yel('Queue depth check')} - Skips if queues are overwhelmed")
        print(f"   • {yel('Circuit breaker')} - Stops on repeated failures")
        print()
        return

    container = find_worker_container()

    if ns.task:
        if ns.task not in TASKS:
            sys.exit(red(f"Unknown task '{ns.task}'. Run --list to see all tasks."))
        dispatch(ns.task, ns.args, container)
    else:
        interactive(container)


if __name__ == "__main__":
    main()
