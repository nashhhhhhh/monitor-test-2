from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from export_live_dashboard_data import SOURCE_FILE, export_dashboard_sheets


# How often to check the source workbook for saved changes.
POLL_INTERVAL_SECONDS = 60

# How long the workbook must remain unchanged before export starts.
SETTLE_SECONDS = 20

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


def run_watcher() -> None:
    log(f"Monitoring workbook: {SOURCE_FILE}")
    log(f"Poll interval: {POLL_INTERVAL_SECONDS}s | Settle window: {SETTLE_SECONDS}s")

    last_signature = get_file_signature(SOURCE_FILE)

    if last_signature is None:
        log(f"Source workbook not found yet: {SOURCE_FILE}")
    else:
        try:
            log("Initial export started.")
            export_dashboard_sheets()
            log("Initial export completed.")
        except Exception as exc:
            log(f"Initial export failed: {exc}")

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
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
            export_dashboard_sheets()
            last_signature = stable_signature
            log("Export completed after workbook update.")
        except Exception as exc:
            log(f"Export failed: {exc}")


def main() -> None:
    run_watcher()


if __name__ == "__main__":
    main()
