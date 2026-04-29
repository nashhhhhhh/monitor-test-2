from __future__ import annotations

import csv
import io
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from downtime_service import write_downtime_cache_file


# External source workbook path.
# Edit this if the live workbook is moved later.
SOURCE_FILE = Path(r"C:\Users\merri\Downloads\data\BMS\main.xlsx")

# Local export directory for dashboard data files.
# Edit this if your project data folder moves.
EXPORT_DIR = Path(__file__).resolve().parents[1] / "data"

# Source sheet to dashboard export mapping.
# If sheet names differ slightly in the source workbook, adjust them here.
# Add more sheet mappings later using the same sheet-purpose-to-filename pattern.
SHEET_EXPORT_MAP = {
    "SM_PMMDB6_ENERGY": {
        "export_filename": "mdb6_energy.csv",
        "history_name": "SM/PM-MDB-6_Energy",
    },
    "SM_PMMDB7_ENERGY": {
        "export_filename": "mdb7_energy.csv",
        "history_name": "SM/PM-MDB-7_Energy",
    },
    "SM_PMMDB8_ENERGY": {
        "export_filename": "mdb8_energy.csv",
        "history_name": "SM/PM-MDB-8_Energy",
    },
    "SM_PMMDB9_ENERGY": {
        "export_filename": "mdb9_energy.csv",
        "history_name": "SM/PM-MDB-9_Energy",
    },
    "SM_PMMDB10_ENERGY": {
        "export_filename": "mdb10_energy.csv",
        "history_name": "SM/PM-MDB-10_Energy",
    },
    "SM_PMEMDB1_ENERGY": {
        "export_filename": "mdb_emdb.csv",
        "history_name": "SM/PM-MAIN-EDB-OF_Energy",
    },
    "SM_PMBOILERPANEL1INDIRECT_ENERG": {
        "export_filename": "boiler_indirect_energy.csv",
        "history_name": "SM/PM-BOILER-PANEL-1-IN-DIRECT_Energy",
    },
    "SM_PMBOILERPANEL2DIRECT_ENERGY ": {
        "export_filename": "boiler_direct_energy.csv",
        "history_name": "SM/PM-BOILER-PANEL-2-DIRECT_Energy",
    },
    "SM_PMWWTPCONTROLPANEL_ENERGY": {
        "export_filename": "_PM-WWTP-CONTROL-PANEL_Energy.csv",
        "history_name": "SM/PM-WWTP-CONTROL-PANEL_Energy",
    },
}

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
SOURCE_TIME_OFFSET_HOURS = 0
REFRESH_SOURCE_WORKBOOK_BEFORE_EXPORT = os.environ.get("SFST_REFRESH_EXCEL_BEFORE_EXPORT", "0") == "1"
EXCEL_REFRESH_TIMEOUT_SECONDS = 240


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def refresh_source_workbook(source_file: Path, force: bool = False) -> bool:
    """Open the BMS workbook in Excel, refresh linked data, save it, then close Excel."""
    if not force and not REFRESH_SOURCE_WORKBOOK_BEFORE_EXPORT:
        return False

    if not source_file.exists():
        raise FileNotFoundError(f"Source workbook not found: {source_file}")

    workbook_path = powershell_quote(str(source_file))
    script = f"""
$ErrorActionPreference = 'Stop'
$path = {workbook_path}
$directory = [System.IO.Path]::GetDirectoryName($path)
$stem = [System.IO.Path]::GetFileNameWithoutExtension($path)
$tempPath = [System.IO.Path]::Combine($directory, "$stem.refreshing.xlsx")
$excel = $null
$workbook = $null
$savedCopy = $false
try {{
    if (Test-Path -LiteralPath $tempPath) {{
        Remove-Item -LiteralPath $tempPath -Force
    }}

    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $excel.EnableEvents = $false

    $workbook = $excel.Workbooks.Open($path, 3, $false)

    foreach ($connection in $workbook.Connections) {{
        try {{
            if ($connection.OLEDBConnection -ne $null) {{
                $connection.OLEDBConnection.BackgroundQuery = $false
            }}
        }} catch {{}}
        try {{
            if ($connection.ODBCConnection -ne $null) {{
                $connection.ODBCConnection.BackgroundQuery = $false
            }}
        }} catch {{}}
    }}

    foreach ($sheet in $workbook.Worksheets) {{
        foreach ($queryTable in $sheet.QueryTables) {{
            try {{
                $queryTable.BackgroundQuery = $false
            }} catch {{}}
        }}
        foreach ($listObject in $sheet.ListObjects) {{
            try {{
                if ($listObject.QueryTable -ne $null) {{
                    $listObject.QueryTable.BackgroundQuery = $false
                }}
            }} catch {{}}
        }}
    }}

    $workbook.RefreshAll()

    for ($i = 0; $i -lt 12; $i++) {{
        try {{
            $excel.CalculateUntilAsyncQueriesDone()
        }} catch {{
            # Older Excel builds may not expose this method; the save below still captures synchronous refreshes.
        }}
        Start-Sleep -Seconds 5
    }}

    $excel.CalculateFullRebuild()
    $workbook.Saved = $false
    $workbook.Save()
    $workbook.SaveCopyAs($tempPath)
    $savedCopy = $true
}} finally {{
    if ($workbook -ne $null) {{
        $workbook.Close($false)
    }}
    if ($excel -ne $null) {{
        $excel.Quit()
    }}
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}}

if ($savedCopy -and (Test-Path -LiteralPath $tempPath)) {{
    Copy-Item -LiteralPath $tempPath -Destination $path -Force
    Remove-Item -LiteralPath $tempPath -Force
}}
"""

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=EXCEL_REFRESH_TIMEOUT_SECONDS,
    )

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Excel refresh/save failed: {details}")

    print(f"[OK] Refreshed and saved source workbook: {source_file}")
    return True


def normalize_column_name(name: object) -> str:
    text = str(name).strip().lower()
    text = text.replace("\n", " ")
    text = "_".join(text.split())

    for old, new in {
        "/": "_",
        "-": "_",
        "(": "",
        ")": "",
        "%": "pct",
        ".": "",
        ",": "",
    }.items():
        text = text.replace(old, new)

    while "__" in text:
        text = text.replace("__", "_")

    return text.strip("_")


def is_unnamed_column(name: object) -> bool:
    return str(name).strip().lower().startswith("unnamed")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()

    cleaned = cleaned.loc[:, [col for col in cleaned.columns if not is_unnamed_column(col)]]
    cleaned.columns = [normalize_column_name(col) for col in cleaned.columns]
    cleaned = cleaned.loc[:, [col for col in cleaned.columns if col]]

    return cleaned


def build_column_lookup(columns: pd.Index) -> dict[str, str]:
    return {
        normalize_column_name(column): str(column)
        for column in columns
        if normalize_column_name(column)
    }


def require_column(column_lookup: dict[str, str], *candidates: str) -> str:
    for candidate in candidates:
        normalized = normalize_column_name(candidate)
        if normalized in column_lookup:
            return column_lookup[normalized]

    raise KeyError(
        "None of the expected columns were found: "
        + ", ".join(candidates)
    )


def format_timestamp_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        invalid_count = int(parsed.isna().sum())
        raise ValueError(f"Found {invalid_count} invalid timestamp value(s)")

    parsed = parsed + pd.to_timedelta(SOURCE_TIME_OFFSET_HOURS, unit="h")

    return parsed.map(
        lambda value: value.strftime("%d-%b-%y %I:%M:%S %p").lstrip("0") + " ICT"
    )


def format_value_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        invalid_count = int(numeric.isna().sum())
        raise ValueError(f"Found {invalid_count} invalid numeric value(s)")

    return numeric.map(lambda value: f"{value:.2f}")


def build_energy_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    filtered_df = df.loc[:, [col for col in df.columns if not is_unnamed_column(col)]].copy()
    column_lookup = build_column_lookup(filtered_df.columns)

    timestamp_col = require_column(
        column_lookup,
        "Timestamp",
        "Date Time",
        "Datetime",
        "Time",
    )
    trend_flags_col = require_column(
        column_lookup,
        "TrendFlags_Tag",
        "Trend Flags",
        "TrendFlag",
        "Trend_Flags",
    )
    status_col = require_column(column_lookup, "Status_Tag", "Status")
    value_col = require_column(
        column_lookup,
        "Value (kW-hr)",
        "Value",
        "kWh",
        "Energy",
    )

    export_df = pd.DataFrame(
        {
            "Timestamp": format_timestamp_series(filtered_df[timestamp_col]),
            "Trend Flags": filtered_df[trend_flags_col].fillna("{ }").astype(str).str.strip(),
            "Status": filtered_df[status_col].fillna("{ok}").astype(str).str.strip(),
            "Value (kW-hr)": format_value_series(filtered_df[value_col]),
        }
    )

    # Remove fully empty rows after alignment and keep source order.
    export_df = export_df.dropna(how="all")
    return export_df


def retryable_open_source(source_file: Path) -> BinaryIO:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Open the workbook in binary read-only mode so the source is never modified.
            return source_file.open("rb")
        except OSError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                print(
                    f"[RETRY] Source workbook unavailable "
                    f"(attempt {attempt}/{MAX_RETRIES}): {exc}"
                )
                time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"Failed to access source workbook after {MAX_RETRIES} attempts: {source_file}"
    ) from last_error


def load_workbook(source_file: Path) -> pd.ExcelFile:
    with retryable_open_source(source_file) as handle:
        # Read workbook contents through a read-only file handle.
        workbook_bytes = handle.read()

    return pd.ExcelFile(io.BytesIO(workbook_bytes), engine="openpyxl")


def write_mdb_csv_with_retry(
    df: pd.DataFrame,
    export_path: Path,
    history_name: str,
) -> None:
    last_error: Exception | None = None
    export_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, MAX_RETRIES + 1):
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f"{export_path.stem}_",
                suffix=export_path.suffix,
                dir=export_path.parent,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)

            with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
                handle.write(f"history:{history_name}\n\n")
                writer = csv.writer(handle)
                writer.writerow(df.columns)
                writer.writerows(df.itertuples(index=False, name=None))

            temp_path.replace(export_path)
            return
        except OSError as exc:
            last_error = exc
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

            if attempt < MAX_RETRIES:
                print(
                    f"[RETRY] Could not write export file '{export_path.name}' "
                    f"(attempt {attempt}/{MAX_RETRIES}): {exc}"
                )
                time.sleep(RETRY_DELAY_SECONDS)
        except Exception:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

    raise RuntimeError(
        f"Failed to write export file after {MAX_RETRIES} attempts: {export_path}"
    ) from last_error


def export_sheet(
    workbook: pd.ExcelFile,
    sheet_name: str,
    export_filename: str,
    history_name: str,
) -> None:
    if sheet_name not in workbook.sheet_names:
        print(f"[WARN] Sheet not found, skipped: {sheet_name}")
        return

    df = pd.read_excel(workbook, sheet_name=sheet_name, engine="openpyxl")
    cleaned = build_energy_export_dataframe(df)

    export_path = EXPORT_DIR / export_filename
    write_mdb_csv_with_retry(cleaned, export_path, history_name)

    print(
        f"[OK] Exported '{sheet_name}' -> '{export_filename}' "
        f"({len(cleaned)} rows)"
    )


def export_dashboard_sheets() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Source workbook not found: {SOURCE_FILE}")

    refresh_source_workbook(SOURCE_FILE)
    workbook = load_workbook(SOURCE_FILE)

    for sheet_name, export_config in SHEET_EXPORT_MAP.items():
        try:
            export_sheet(
                workbook,
                sheet_name,
                export_config["export_filename"],
                export_config["history_name"],
            )
        except Exception as exc:
            print(f"[ERROR] Failed to export '{sheet_name}': {exc}")


def main() -> None:
    export_dashboard_sheets()
    try:
        cache_path = write_downtime_cache_file()
        print(f"[OK] Exported downtime cache -> '{cache_path}'")
    except Exception as exc:
        print(f"[WARN] Failed to export downtime cache: {exc}")


if __name__ == "__main__":
    main()
