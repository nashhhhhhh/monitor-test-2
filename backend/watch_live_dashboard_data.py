from __future__ import annotations

import time
from datetime import datetime, date
from pathlib import Path

from downtime_service import write_downtime_cache_file
from export_live_dashboard_data import SOURCE_FILE, export_dashboard_sheets


# How often to check the source workbook for saved changes.
POLL_INTERVAL_SECONDS = 60

# How long the workbook must remain unchanged before export starts.
SETTLE_SECONDS = 20
DAILY_EXPORT_HOUR = 8
DAILY_EXPORT_MINUTE = 0
DAILY_EXPORT_LABEL = f"{DAILY_EXPORT_HOUR:02d}:{DAILY_EXPORT_MINUTE:02d}"

LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "watch_live_dashboard_data.log"


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[WATCHER] {timestamp} | {message}"
    print(line)

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        # Keep the watcher alive even if file logging is unavailable.
        pass


def get_file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None

    return (stat.st_mtime_ns, stat.st_size)


def wait_for_stable_signature(path: Path, baseline: tuple[int, int] | None) -> tuple[int, int] | None:
    stable_since = time.monotonic()
    current = baseline

    while True:
        time.sleep(2)
        latest = get_file_signature(path)

        if latest != current:
            current = latest
            stable_since = time.monotonic()
            continue

        if time.monotonic() - stable_since >= SETTLE_SECONDS:
            return current


def daily_export_day(now: datetime | None = None) -> date:
    current = now or datetime.now()
    return current.date()


def is_daily_export_window_open(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    scheduled_time = current.replace(
        hour=DAILY_EXPORT_HOUR,
        minute=DAILY_EXPORT_MINUTE,
        second=0,
        microsecond=0,
    )
    return current >= scheduled_time


def should_run_daily_export(last_daily_export: date | None, now: datetime | None = None) -> bool:
    current = now or datetime.now()
    if not is_daily_export_window_open(current):
        return False
    return last_daily_export != daily_export_day(current)


def export_dashboard_and_downtime_cache() -> None:
    export_dashboard_sheets()
    cache_path = write_downtime_cache_file()
    log(f"Downtime cache refreshed: {cache_path}")


def run_watcher() -> None:
    log(f"Monitoring workbook: {SOURCE_FILE}")
    log(f"Poll interval: {POLL_INTERVAL_SECONDS}s | Settle window: {SETTLE_SECONDS}s")

    last_signature = get_file_signature(SOURCE_FILE)
    last_daily_export: date | None = None

    if last_signature is None:
        log(f"Source workbook not found yet: {SOURCE_FILE}")
    else:
        try:
            log("Initial export started.")
            export_dashboard_and_downtime_cache()
            log("Initial export completed.")
            if is_daily_export_window_open():
                last_daily_export = daily_export_day()
        except Exception as exc:
            log(f"Initial export failed: {exc}")

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        if should_run_daily_export(last_daily_export):
            try:
                log(f"Scheduled {DAILY_EXPORT_LABEL} local time reached. Starting forced daily export.")
                export_dashboard_and_downtime_cache()
                last_daily_export = daily_export_day()
                last_signature = get_file_signature(SOURCE_FILE)
                log("Forced daily export completed.")
            except Exception as exc:
                log(f"Forced daily export failed: {exc}")

        current_signature = get_file_signature(SOURCE_FILE)

        if current_signature is None:
            if last_signature is not None:
                log(f"Source workbook unavailable: {SOURCE_FILE}")
            last_signature = None
            continue

        if current_signature == last_signature:
            continue

        log("Workbook change detected. Waiting for save to settle...")
        stable_signature = wait_for_stable_signature(SOURCE_FILE, current_signature)

        if stable_signature is None:
            log("Workbook disappeared before export could run.")
            last_signature = None
            continue

        try:
            export_dashboard_and_downtime_cache()
            last_signature = stable_signature
            if is_daily_export_window_open():
                last_daily_export = daily_export_day()
            log("Export completed after workbook update.")
        except Exception as exc:
            log(f"Export failed: {exc}")


def main() -> None:
    run_watcher()


if __name__ == "__main__":
    main()
