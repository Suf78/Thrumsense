from datetime import datetime
import pytest
from app.detect import (
    check_static_threshold,
    check_adaptive_spike,
    check_faults,
    determine_severity,
    set_derived_thresholds,
)

def setup_module():
    set_derived_thresholds({
        "PT08.S1(CO)": {"low": 800.0, "high": 1800.0}
    })

def test_static_threshold_detection():
    # Value in range -> no alert
    assert check_static_threshold("PT08.S1(CO)", 1200.0) is None

    # Value above threshold -> THRESHOLD_HIGH
    alert_high = check_static_threshold("PT08.S1(CO)", 2200.0)
    assert alert_high is not None
    assert alert_high["type"] == "THRESHOLD_HIGH"

    # Value below threshold -> THRESHOLD_LOW
    alert_low = check_static_threshold("PT08.S1(CO)", 500.0)
    assert alert_low is not None
    assert alert_low["type"] == "THRESHOLD_LOW"

def test_adaptive_spike_detection():
    # Regular window with median ~1000 and low variance
    window = [1000.0 + (i % 5) * 5.0 for i in range(24)]
    
    # Normal point
    assert check_adaptive_spike("PT08.S1(CO)", 1010.0, window, z_limit=3.5) is None

    # Extreme spike
    alert = check_adaptive_spike("PT08.S1(CO)", 2500.0, window, z_limit=3.5)
    assert alert is not None
    assert alert["type"] == "ADAPTIVE_SPIKE"

def test_sensor_fault_detection():
    # Dropout rule: 3 or more consecutive nulls
    dropout_alert = check_faults("PT08.S1(CO)", consecutive_nulls=3, recent_values=[], dropout_hours=3)
    assert dropout_alert is not None
    assert dropout_alert["type"] == "SENSOR_DROPOUT"

    # Flatline rule: 4 or more identical values
    flatline_values = [1250.0, 1250.0, 1250.0, 1250.0]
    flatline_alert = check_faults("PT08.S1(CO)", consecutive_nulls=0, recent_values=flatline_values, flatline_hours=4)
    assert flatline_alert is not None
    assert flatline_alert["type"] == "FLATLINE"

def test_severity_levels():
    limits = {"low": 500.0, "high": 1500.0}
    # Single rule -> info
    assert determine_severity(has_threshold=True, has_adaptive=False, has_fault=False, value=1600.0, threshold_limits=limits) == "info"
    # Both rules -> warning
    assert determine_severity(has_threshold=True, has_adaptive=True, has_fault=False, value=1700.0, threshold_limits=limits) == "warning"
    # Both rules + extreme (>1.5x) -> critical
    assert determine_severity(has_threshold=True, has_adaptive=True, has_fault=False, value=2500.0, threshold_limits=limits) == "critical"
