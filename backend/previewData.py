import pandas as pd

EXCEL_FILE = "../Stage2_UC_Database_Raphael.xlsx"
SHEET_NAME = "Database"

def inspect_excel():
    # Load Excel
    df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)

    print("\n==============================")
    print("RAW COLUMN HEADERS (EXACT)")
    print("==============================")
    for col in df.columns:
        print(repr(col))  # shows hidden spaces / symbols

    print("\n==============================")
    print("COLUMN DATA TYPES")
    print("==============================")
    print(df.dtypes)

    print("\n==============================")
    print("FIRST 5 ROWS (PREVIEW)")
    print("==============================")
    print(df.head())

    print("\n==============================")
    print("SAMPLE VALUE + TYPE PER COLUMN")
    print("==============================")
    for col in df.columns:
        first_valid = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
        print(f"{repr(col)} → value: {first_valid}, type: {type(first_valid)}")

    print("\n==============================")
    print("FUZZY MATCH HELPERS")
    print("==============================")
    print("Columns containing 'Room':")
    print([col for col in df.columns if "Room" in col])

    print("\nColumns containing 'Temp':")
    print([col for col in df.columns if "Temp" in col])

    print("\nColumns containing 'Set':")
    print([col for col in df.columns if "Set" in col])

    print("\n✅ Inspection complete")

if __name__ == "__main__":
    inspect_excel()
