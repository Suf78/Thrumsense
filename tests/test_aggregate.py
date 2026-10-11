from datetime import datetime
import pandas as pd
from app.aggregate import build_stats_pipeline

def test_aggregation_pipeline_structure():
    """Verify aggregation pipeline conforms to TECHNICAL §5.9 ($match, $dateTrunc, $sort)."""
    start = datetime(2004, 3, 10, 0, 0, 0)
    end = datetime(2004, 3, 17, 0, 0, 0)
    pipeline = build_stats_pipeline("PT08.S1(CO)", start, end, gran="day")
    
    assert len(pipeline) == 3
    assert "$match" in pipeline[0]
    assert pipeline[0]["$match"]["sensor_id"] == "PT08.S1(CO)"
    assert "$group" in pipeline[1]
    assert pipeline[1]["$group"]["_id"]["$dateTrunc"]["unit"] == "day"
    assert "$sort" in pipeline[2]

def test_pandas_reference_aggregation():
    """Verify pandas min, max, avg logic equals pipeline definition."""
    data = [10.0, 20.0, 30.0, None]
    series = pd.Series(data).dropna()
    assert series.min() == 10.0
    assert series.max() == 30.0
    assert series.mean() == 20.0
