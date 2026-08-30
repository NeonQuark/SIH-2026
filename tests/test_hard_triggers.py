import uuid
import pytest
from backend.services.nlp_pipeline import nlp_pipeline
from backend.services.distress_engine import distress_engine
from backend.services.alerting_service import alerting_service

def test_hard_trigger_forces_high_risk_level():
    phrase = "I don't see any point in living, I want to kill myself"
    nlp_res = nlp_pipeline.analyze_text(phrase)

    assert nlp_res["hard_trigger_detected"] is True
    assert "kill myself" in nlp_res["hard_trigger_matched_terms"]

    # Calculate score with zero behavioral signals (low raw composite baseline)
    distress_res = distress_engine.calculate_distress_score(
        victim_id=f"v_ht_{uuid.uuid4().hex[:6]}",
        nlp_output=nlp_res,
        behavioral_signals={}
    )

    assert distress_res["risk_level"] in ["High", "Critical"]
    assert distress_res["explainability"]["hard_trigger_override"] is True
    assert "Hard-trigger safety override applied" in distress_res["explainability"]["safety_override_note"]

def test_hard_trigger_dispatches_immediate_override_alert():
    vid = f"v_ht_alert_{uuid.uuid4().hex[:6]}"
    phrase = "he showed me a knife and threatened to kill me"
    nlp_res = nlp_pipeline.analyze_text(phrase)

    assert nlp_res["hard_trigger_detected"] is True
    assert "knife" in nlp_res["hard_trigger_matched_terms"]

    # Dispatch alert with hard_trigger_detected flag
    alert_res = alerting_service.dispatch_alert(
        victim_id=vid,
        risk_prediction={
            "risk_tier": "low",  # Low tier model prediction forced to critical override
            "hard_trigger_detected": True,
            "projected_score_next_period": 35.0
        }
    )

    assert alert_res["status"] == "dispatched"
    assert alert_res["risk_tier"] == "critical"
    assert alert_res["alert_reason"] == "hard_trigger_override"

def test_normal_non_trigger_phrase_unaffected():
    phrase = "thank you for sending the application update"
    nlp_res = nlp_pipeline.analyze_text(phrase)

    assert nlp_res["hard_trigger_detected"] is False
    assert len(nlp_res["hard_trigger_matched_terms"]) == 0

    distress_res = distress_engine.calculate_distress_score(
        victim_id=f"v_norm_{uuid.uuid4().hex[:6]}",
        nlp_output=nlp_res,
        behavioral_signals={}
    )

    assert distress_res["risk_level"] == "Low"
    assert distress_res["explainability"]["hard_trigger_override"] is False
    assert distress_res["explainability"]["safety_override_note"] is None
