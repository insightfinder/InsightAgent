#!/usr/bin/env python3
"""
Standalone CLI for the main-agent + email-subagent demo (II-24784). Talks
to main-agent's REST API directly (no auth, matching this repo's other
internal service-to-service calls). main-agent itself calls the
email-subagent Pod over HTTP -- this script never talks to the subagent
directly.

Usage:
    python demo_cli.py [--base-url http://localhost:8007]
"""
import argparse
import sys
import time

import requests

DEFAULT_DRAFT_DELAY = 90
POLL_INTERVAL = 5
STARTUP_GRACE = 20


def _fetch(base_url: str, task_id: str, tolerate_missing_until: float = 0.0):
    """Returns None while the workflow is not queryable yet.

    A GET issued in the first moments after POST /tasks can 404: Temporal
    cannot answer a query until the worker has completed the first workflow
    task, which is noticeably slower right after a pod restart.
    """
    resp = requests.get(f"{base_url}/tasks/{task_id}")
    if resp.status_code == 404 and time.monotonic() < tolerate_missing_until:
        return None
    resp.raise_for_status()
    return resp.json()


def poll_until(base_url: str, task_id: str, terminal_statuses: set) -> dict:
    while True:
        status = _fetch(base_url, task_id)
        if status["status"] in terminal_statuses:
            return status
        time.sleep(2)


def countdown_until_drafted(base_url: str, task_id: str, seconds: int) -> dict:
    """Show a live countdown while the subagent drafts.

    The subagent deliberately pauses (EMAIL_SUBAGENT_DRAFT_DELAY_SECONDS, 90s
    by default) so the workflow's latency is legible on AW's trace view. The
    countdown mirrors that pause, but the real task status is what ends it --
    so this stays honest if the pause is retuned or the draft lands early.
    """
    terminal = {"awaiting_confirmation", "failed", "cancelled", "sent"}
    deadline = time.monotonic() + seconds
    next_poll = 0.0
    grace_until = time.monotonic() + STARTUP_GRACE
    while True:
        # Tick the display every second, but poll only every POLL_INTERVAL:
        # each status GET is itself traced, so polling once a second across a
        # 90s pause would bury the workflow's own trace under ~90 junk ones.
        if time.monotonic() >= next_poll:
            status = _fetch(base_url, task_id, grace_until)
            next_poll = time.monotonic() + POLL_INTERVAL
            if status is not None and status["status"] in terminal:
                print("\r" + " " * 60 + "\r", end="", flush=True)
                return status
        remaining = int(round(deadline - time.monotonic()))
        if remaining > 0:
            print(f"\r  Subagent drafting ... {remaining:3d}s remaining", end="", flush=True)
        else:
            print(f"\r  Subagent drafting ... still working ({-remaining}s over)",
                  end="", flush=True)
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8007")
    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_DRAFT_DELAY,
        help="Seconds to count down while the subagent drafts (match the "
             "subagent's EMAIL_SUBAGENT_DRAFT_DELAY_SECONDS).",
    )
    args = parser.parse_args()

    to_email = input("Recipient email: ").strip()
    subject = input("Email subject/title: ").strip()
    topic = input("What should the email body say? ").strip()

    resp = requests.post(
        f"{args.base_url}/tasks",
        json={"user_message": topic, "to_email": to_email, "subject": subject},
    )
    resp.raise_for_status()
    task_id = resp.json()["task_id"]
    print(f"Started task {task_id} ...")

    status = countdown_until_drafted(args.base_url, task_id, args.delay)
    if status["status"] == "failed":
        sys.exit(f"Workflow failed: {status.get('error')}")

    print("\n--- Drafted Email ---")
    print(status["draft"])
    print("---------------------\n")

    confirmed = input("Send this email? [y/n]: ").strip().lower() == "y"
    requests.post(f"{args.base_url}/tasks/{task_id}/confirm", json={"confirmed": confirmed})

    final = poll_until(args.base_url, task_id, {"sent", "cancelled", "failed"})
    print("Final result:", final)


if __name__ == "__main__":
    main()
