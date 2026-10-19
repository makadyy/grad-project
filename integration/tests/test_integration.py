from run_all import run_all


def test_offline_cross_workstream_smoke():
    result = run_all()
    assert result["status"] == "PASS"
    assert result["a2_session_features"]["event_count"] == 4
    assert result["a4"]["generated_artifacts"] == 20
    assert "H04" in result["a4"]["honey_lures"]
    assert result["a3"]["requested_action"] == result["a3"]["executed_action"]
    assert result["a3"]["shielded"] is False
    assert result["a1"] == "offline_pipeline_available_but_real_dataset_outputs_missing"
