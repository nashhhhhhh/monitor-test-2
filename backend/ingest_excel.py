import pandas as pd
import sqlite3

EXCEL_FILE = "../Temperature_Reading.xlsx"
DB_FILE = "temps.db"

def ingest():
    df = pd.read_excel(
        EXCEL_FILE,
        sheet_name="Database"
    )

    # Use Room ID directly for SVG matching
    df["base_room"] = (
        df["Room ID:"]
        .astype(str)
        .str.strip()
    )

    # Human-readable room name
    df["room_name"] = (
        df["Room Name:"]
        .astype(str)
        .str.strip()
    )

    # Ensure numeric (MATCH FRONTEND EXPECTATIONS)
    df["Actual Temp"] = pd.to_numeric(df["Most Recent Temp:"], errors="coerce")
    df["Requirement"] = pd.to_numeric(df["Actual Set Point: (℃)"], errors="coerce")
    df["temp_diff"] = pd.to_numeric(df["Temp Diff:"], errors="coerce")

    # Remove invalid Room IDs ONLY
    df = df[df["base_room"].notna()]
    df = df[df["base_room"].str.lower() != "nan"]
    df = df[df["base_room"].str.strip() != ""]

    # Clean room names
    df.loc[df["room_name"].str.lower() == "nan", "room_name"] = ""

    # Status logic (UNCHANGED BEHAVIOUR)
    def status(row):
        if pd.isna(row["Actual Temp"]) or pd.isna(row["Requirement"]):
            return "NO_DATA"

        diff = row["temp_diff"]
        if diff >= 2:
            return "CRITICAL"
        elif diff >= 1:
            return "WARNING"
        else:
            return "OK"

    df["status"] = df.apply(status, axis=1)

    # Aggregate per room (COLUMN NAMES NOW MATCH)
    room_df = (
        df.groupby("base_room", as_index=False)
        .agg({
            "room_name": "first",
            "Actual Temp": "mean",
            "Requirement": "mean",
            "temp_diff": "max",
            "status": "max"
        })
    )

    # Store
    conn = sqlite3.connect(DB_FILE)
    room_df.to_sql(
        "room_temperature",
        conn,
        if_exists="replace",
        index=False
    )
    conn.close()

    print("====== Excel ingested successfully ======")

if __name__ == "__main__":
    ingest()
