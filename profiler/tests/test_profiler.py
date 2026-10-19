import json
import pytest
from features import FeatureExtractor, FEATURE_NAMES
from events import NormalizedEvent

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


def test_deduplication_is_source_scoped_and_ids_required():
    x=FeatureExtractor()
    x.add_event(ev(event_id="shared",source="cowrie"))
    x.add_event(ev(event_id="shared",source="portal"))
    assert x.features_for("s1")["event_count"]==2
    with pytest.raises(ValueError,match="event_id is required"):
        x.add_event(ev(event_id=" "))

def test_authentication_metrics_are_portal_scoped():
    x=FeatureExtractor()
    x.add_events([ev(event_id="1",event_type="login_attempt"),
                  ev(event_id="2",source="portal",event_type="portal_auth_attempt"),
                  ev(event_id="3",source="portal",event_type="portal_auth_failure")])
    row=x.features_for("s1")
    assert row["login_attempt_count"]==1
    assert row["login_failure_count"]==1
    assert row["portal_auth_failure_count"]==1

def test_event_features_are_scoped_to_their_documented_sources():
    x=FeatureExtractor()
    x.add_events([
      ev(event_id="c1",source="cowrie",event_type="command_executed"),
      ev(event_id="c2",source="cowrie",event_type="file_download"),
      ev(event_id="c3",source="cowrie",event_type="connect"),
      ev(event_id="p1",source="portal",event_type="auth_failure"),
      ev(event_id="p2",source="portal",event_type="admin_action"),
      ev(event_id="d1",source="database",event_type="select"),
      ev(event_id="d2",source="database",event_type="update"),
      ev(event_id="x1",source="wazuh",event_type="command_download_connect_auth_failure_admin_action_select_delete"),
      ev(event_id="x2",source="portal",event_type="db_write_download_connect"),
      ev(event_id="x3",source="database",event_type="portal_admin_auth_failure"),
    ])
    row=x.features_for("s1")
    assert row["command_event_count"]==1
    assert row["file_download_event_count"]==1 and row["network_connection_count"]==1
    assert row["login_failure_count"]==1 and row["portal_auth_failure_count"]==1
    assert row["portal_admin_action_count"]==1
    assert row["database_read_count"]==1 and row["database_write_count"]==1
    assert row["database_delete_count"]==0

def test_reject_nonfinite_and_boolean_numbers():
    for field,value in [("bytes_in",float("nan")),("bytes_out",float("inf")),("duration_seconds",True)]:
        with pytest.raises(ValueError): NormalizedEvent.from_mapping(ev(**{field:value}))

def test_snapshot_rejects_corrupt_or_nonfinite_values():
    x=FeatureExtractor(); x.add_event(ev())
    bad=json.loads(json.dumps(x.snapshot())); bad["sessions"]["s1"]["bytes_in_total"]=float("nan")
    with pytest.raises(ValueError): FeatureExtractor.from_snapshot(bad)
    with pytest.raises(ValueError): FeatureExtractor.from_snapshot({"sessions":{"s1":{"event_count":99}}})

def test_shap_shapes_and_inputs_are_checked():
    np=pytest.importorskip("numpy")
    from explain import ShapService
    class Explainer:
        def __init__(self, values, base): self.values=values; self.base_values=base
        def __call__(self,row): return self
    svc=ShapService(object(),["a","b"]); svc._explainer=Explainer(np.zeros((1,3)),np.array([0.]))
    with pytest.raises(ValueError,match="Unexpected SHAP values shape"): svc.explain_one({"a":1,"b":2})
    with pytest.raises(ValueError,match="finite"): svc.explain_one({"a":float("nan"),"b":2})
    with pytest.raises(ValueError,match="top_k"): svc.explain_one({"a":1,"b":2},top_k=True)


def test_huge_byte_counts_saturate_instead_of_wrapping_to_zero():
    from features import FeatureExtractor, MAX_BYTES
    fx = FeatureExtractor()
    for i in range(2):
        fx.add_event({"session_id": "s", "source": "cowrie", "event_id": f"e{i}",
                      "event_type": "network_connection", "timestamp": "2026-01-01T00:00:0%dZ" % i,
                      "bytes_in": 1e308, "bytes_out": 1e308})
    f = fx.features_for("s")
    assert f["bytes_in_total"] == MAX_BYTES and f["bytes_out_total"] == MAX_BYTES
    assert f["bytes_total"] == MAX_BYTES
