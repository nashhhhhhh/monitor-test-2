from __future__ import annotations

import sys

from export_live_dashboard_data import SOURCE_FILE, refresh_source_workbook


def main() -> int:
    try:
        refresh_source_workbook(SOURCE_FILE, force=True)
        print(f"[OK] BMS workbook refreshed and saved: {SOURCE_FILE}")
        return 0
    except Exception as exc:
        print(f"[ERROR] BMS workbook refresh failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
