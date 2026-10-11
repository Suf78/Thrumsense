import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
import numpy as np

from app.config import DATA_PATH, THRESHOLDS
from app.db import get_readings_col, create_indexes, get_db
from app.detect import set_derived_thresholds

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Column metadata definition per TECHNICAL.md section 4.1 & PRD
VARIABLES_META: Dict[str, Dict[str, str]] = {
    "CO(GT)": {"kind": "reference", "unit": "mg/m^3"},
    "PT08.S1(CO)": {"kind": "raw_sensor", "unit": "sensor_response"},
    "NMHC(GT)": {"kind": "reference", "unit": "ug/m^3"},
    "C6H6(GT)": {"kind": "reference", "unit": "ug/m^3"},
    "PT08.S2(NMHC)": {"kind": "raw_sensor", "unit": "sensor_response"},
    "NOx(GT)": {"kind": "reference", "unit": "ppb"},
    "PT08.S3(NOx)": {"kind": "raw_sensor", "unit": "sensor_response"},
    "NO2(GT)": {"kind": "reference", "unit": "ug/m^3"},
    "PT08.S4(NO2)": {"kind": "raw_sensor", "unit": "sensor_response"},
    "PT08.S5(O3)": {"kind": "raw_sensor", "unit": "sensor_response"},
    "T": {"kind": "weather", "unit": "degC"},
    "RH": {"kind": "weather", "unit": "%"},
    "AH": {"kind": "weather", "unit": "g/m^3"},
}

def clean_and_prepare_df(csv_path: Path) -> pd.DataFrame:
    """
    Parse and clean CSV per TECHNICAL.md section 5.1:
    - Delimiter ';' and decimal ','
    - Combine Date (DD/MM/YYYY) and Time (HH.MM.SS)
    - Replace -200 with NaN (which becomes None in Mongo)
    - Drop empty trailing rows and columns
    """
    logger.info("Reading CSV from %s", csv_path)
    df = pd.read_csv(csv_path, sep=";", decimal=",", low_memory=False)

    # Drop unnamed/empty columns and rows
    df = df.dropna(how="all", axis=1)
    df = df.dropna(how="all", axis=0)

    # Filter rows that have Date and Time
    df = df[df["Date"].notna() & df["Time"].notna()].copy()

    # Clean Time string (e.g., '18.00.00' -> '18:00:00')
    time_clean = df["Time"].astype(str).str.replace(".", ":", regex=False)
    datetime_str = df["Date"].astype(str).str.strip() + " " + time_clean.str.strip()
    df["timestamp"] = pd.to_datetime(datetime_str, format="%d/%m/%Y %H:%M:%S")

    # Replace -200 with NaN
    for col in VARIABLES_META.keys():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[df[col] == -200.0, col] = np.nan

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df

def derive_percentile_thresholds(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Compute 1st and 99th percentiles of non-null values per variable (TECHNICAL §5.2)."""
    thresholds: Dict[str, Dict[str, float]] = {}
    low_pct = float(THRESHOLDS.get("defaults", {}).get("low_pct", 1.0))
    high_pct = float(THRESHOLDS.get("defaults", {}).get("high_pct", 99.0))

    for col in VARIABLES_META.keys():
        if col in df.columns:
            series = df[col].dropna()
            if not series.empty:
                low_val = float(np.percentile(series, low_pct))
                high_val = float(np.percentile(series, high_pct))
                thresholds[col] = {"low": round(low_val, 3), "high": round(high_val, 3)}
    return thresholds

def ingest_data(reset: bool = False, csv_path: Path = DATA_PATH) -> int:
    """
    Melt wide dataframe to long format and batch-insert into MongoDB readings collection.
    Creates indexes after bulk write.
    """
    if not csv_path.exists():
        logger.warning("Dataset file not found at %s. Creating synthetic dataset fallback.", csv_path)
        create_sample_dataset(csv_path)

    df = clean_and_prepare_df(csv_path)
    logger.info("Cleaned dataset contains %d hourly timestamps", len(df))

    # Derive static thresholds and save in memory
    derived = derive_percentile_thresholds(df)
    set_derived_thresholds(derived)
    logger.info("Derived static thresholds for %d variables", len(derived))

    readings_col = get_readings_col()
    if reset:
        logger.info("Reset flag specified. Dropping existing readings and alerts collections.")
        db = get_db()
        db["readings"].drop()
        db["alerts"].drop()

    # Melt to long format
    id_vars = ["timestamp"]
    value_vars = [col for col in VARIABLES_META.keys() if col in df.columns]
    melted = df.melt(id_vars=id_vars, value_vars=value_vars, var_name="sensor_id", value_name="value")

    # Batch insert into MongoDB
    batch_size = 5000
    docs_to_insert: List[Dict[str, Any]] = []
    total_inserted = 0

    for row in melted.itertuples(index=False):
        meta = VARIABLES_META.get(row.sensor_id, {"kind": "raw_sensor", "unit": "unknown"})
        val = None if (pd.isna(row.value) or np.isnan(row.value)) else float(row.value)
        doc = {
            "timestamp": row.timestamp.to_pydatetime(),
            "sensor_id": row.sensor_id,
            "kind": meta["kind"],
            "value": val,
            "unit": meta["unit"],
            "source": "UCI Air Quality",
        }
        docs_to_insert.append(doc)
        if len(docs_to_insert) >= batch_size:
            readings_col.insert_many(docs_to_insert, ordered=False)
            total_inserted += len(docs_to_insert)
            docs_to_insert = []

    if docs_to_insert:
        readings_col.insert_many(docs_to_insert, ordered=False)
        total_inserted += len(docs_to_insert)

    logger.info("Bulk inserted %d readings documents into MongoDB", total_inserted)

    # Create indexes per TECHNICAL §4.1
    create_indexes()
    logger.info("MongoDB indexes created successfully.")
    return total_inserted

def create_sample_dataset(dest_path: Path) -> None:
    """Generate sample UCI Air Quality CSV format if actual file is missing."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Generating standard synthetic dataset at %s for initial testing", dest_path)
    timestamps = pd.date_range("2004-03-10 18:00:00", periods=200, freq="h")
    data = {
        "Date": timestamps.strftime("%d/%m/%Y"),
        "Time": timestamps.strftime("%H.%M.%S"),
        "CO(GT)": [f"{2.0 + np.sin(i/10):.1f}".replace(".", ",") if i % 10 != 0 else "-200" for i in range(len(timestamps))],
        "PT08.S1(CO)": [f"{1300 + 100 * np.sin(i/10):.0f}" for i in range(len(timestamps))],
        "NMHC(GT)": [f"{150 + 20 * np.cos(i/10):.0f}" for i in range(len(timestamps))],
        "C6H6(GT)": [f"{10.0 + 2 * np.sin(i/10):.1f}".replace(".", ",") for i in range(len(timestamps))],
        "PT08.S2(NMHC)": [f"{1000 + 50 * np.cos(i/10):.0f}" for i in range(len(timestamps))],
        "NOx(GT)": [f"{160 + 30 * np.sin(i/10):.0f}" for i in range(len(timestamps))],
        "PT08.S3(NOx)": [f"{1050 + 40 * np.sin(i/10):.0f}" for i in range(len(timestamps))],
        "NO2(GT)": [f"{110 + 15 * np.cos(i/10):.0f}" for i in range(len(timestamps))],
        "PT08.S4(NO2)": [f"{1600 + 100 * np.sin(i/10):.0f}" for i in range(len(timestamps))],
        "PT08.S5(O3)": [f"{1200 + 80 * np.cos(i/10):.0f}" for i in range(len(timestamps))],
        "T": [f"{15.0 + 5 * np.sin(i/12):.1f}".replace(".", ",") for i in range(len(timestamps))],
        "RH": [f"{50.0 + 10 * np.cos(i/12):.1f}".replace(".", ",") for i in range(len(timestamps))],
        "AH": [f"{0.8 + 0.1 * np.sin(i/12):.4f}".replace(".", ",") for i in range(len(timestamps))],
    }
    sample_df = pd.DataFrame(data)
    sample_df.to_csv(dest_path, sep=";", index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest UCI Air Quality dataset into MongoDB.")
    parser.add_argument("--reset", action="store_true", help="Drop existing database collections before reload")
    parser.add_argument("--file", type=str, default=str(DATA_PATH), help="Path to AirQualityUCI.csv")
    args = parser.parse_args()
    ingest_data(reset=args.reset, csv_path=Path(args.file))
