from __future__ import annotations

import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from export_live_dashboard_data import export_dashboard_sheets


# Daily export time in 24-hour local time.
# Edit these values if you want the built-in scheduler to run at a different time.
SCHEDULE_HOUR = 0
SCHEDULE_MINUTE = 5

# How often the runner wakes up to check whether it is time to export.
CHECK_INTERVAL_SECONDS = 30

# Small retry window for temporary read/write issues during the scheduled export.
MAX_RUN_RETRIES = 3
RETRY_DELAY_SECONDS = 15


@dataclass(slots=True)
class SchedulerState:
    keep_running: bool = True


STATE = SchedulerState()


def handle_shutdown_signal(signum: int, _frame: object) -> None:
    signal_name = signal.Signals(signum).name
    print(f"[SCHEDULER] Received {signal_name}. Stopping daily export runner.")
    STATE.keep_running = False


def get_next_run_time(now: datetime) -> datetime:
    scheduled = now.replace(
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        second=0,
        microsecond=0,
    )

    if scheduled <= now:
        scheduled += timedelta(days=1)

    return scheduled


def sleep_until(target_time: datetime) -> None:
    while STATE.keep_running:
        remaining_seconds = (target_time - datetime.now()).total_seconds()

        if remaining_seconds <= 0:
            return

        time.sleep(min(CHECK_INTERVAL_SECONDS, max(1, remaining_seconds)))


def run_export_with_retry() -> bool:
    for attempt in range(1, MAX_RUN_RETRIES + 1):
        try:
            print(
                f"[SCHEDULER] Starting scheduled export "
                f"(attempt {attempt}/{MAX_RUN_RETRIES})."
            )
            export_dashboard_sheets()
            print("[SCHEDULER] Scheduled export completed successfully.")
            return True
        except Exception as exc:
            print(f"[SCHEDULER] Scheduled export failed: {exc}")

            if attempt < MAX_RUN_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    print("[SCHEDULER] Scheduled export failed after all retries.")
    return False


def run_scheduler() -> int:
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    print(
        "[SCHEDULER] Daily dashboard export runner started. "
        f"Scheduled time: {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}"
    )

    while STATE.keep_running:
        now = datetime.now()
        next_run = get_next_run_time(now)
        print(f"[SCHEDULER] Next export scheduled for {next_run:%Y-%m-%d %H:%M:%S}")

        sleep_until(next_run)
        if not STATE.keep_running:
            break

        run_export_with_retry()

    print("[SCHEDULER] Daily export runner stopped.")
    return 0


def main() -> int:
    try:
        return run_scheduler()
    except KeyboardInterrupt:
        print("[SCHEDULER] Stopped by user.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
