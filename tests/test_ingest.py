import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from app.ingest import clean_and_prepare_df, derive_percentile_thresholds, create_sample_dataset

def test_csv_cleaning_and_null_conversion(tmp_path: Path):
    """Test -200 is replaced with NaN and timestamps are parsed correctly (TECHNICAL §5.1 & §9)."""
    test_csv = tmp_path / "test_data.csv"
    create_sample_dataset(test_csv)
    
    df = clean_and_prepare_df(test_csv)
    assert not df.empty
    assert "timestamp" in df.columns
    assert isinstance(df["timestamp"].iloc[0], pd.Timestamp)
    
    # Assert -200 does not exist anywhere as a numeric value
    for col in df.select_dtypes(include=[np.number]).columns:
        assert (df[col] == -200).sum() == 0

def test_derive_percentile_thresholds(tmp_path: Path):
    """Test static thresholds derivation low < high."""
    test_csv = tmp_path / "test_data.csv"
    create_sample_dataset(test_csv)
    df = clean_and_prepare_df(test_csv)
    
    thresholds = derive_percentile_thresholds(df)
    assert "PT08.S1(CO)" in thresholds
    t = thresholds["PT08.S1(CO)"]
    assert t["low"] < t["high"]
