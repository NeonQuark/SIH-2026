import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.intervention_engine import intervention_engine, InterventionRecommendationEngine
from backend.db.session import SessionLocal
from backend.db.models import InterventionRecommendation, VictimProfile

client = TestClient(app)

def test_rule_based_recommendations_witness_intimidation():
    vid = f"victim_int_{uuid.uuid4().hex[:6]}"
    risk_profile = {"risk_tier": "critical", "distress_score": 85.0}

    res = intervention_engine.get_recommendations(
        victim_id=vid,
        case_type="witness_intimidation",
        risk_profile=risk_profile
    )

    assert res["case_type"] == "witness_intimidation"
    assert res["total_recommendations"] > 0
    rec_cats = [r["intervention_type"] for r in res["recommendations"]]
    assert "witness_protection" in rec_cats
    assert "legal_aid" in rec_cats
    assert "relocation" in rec_cats

def test_admin_rules_update_and_persistence():
    current_rules = intervention_engine.load_rules()
    assert "caste_violence" in current_rules

    # Modify rule in memory & save
    temp_rules = dict(current_rules)
    temp_rules["test_case_type"] = {
        "mandatory": ["counselling"],
        "risk_dependent": {"critical": ["witness_protection"]}
    }

    res_save = intervention_engine.save_rules(temp_rules)
    assert res_save["status"] == "updated"

    loaded = intervention_engine.load_rules()
    assert "test_case_type" in loaded

    # Clean up test rule
    del temp_rules["test_case_type"]
    intervention_engine.save_rules(temp_rules)

def test_ml_feedback_logging_and_scoring_boost():
    vid = f"victim_fb_{uuid.uuid4().hex[:6]}"
    res = intervention_engine.get_recommendations(
        victim_id=vid,
        case_type="caste_violence",
        risk_profile={"risk_tier": "high"}
    )
    assert len(res["recommendations"]) > 0

    first_rec = res["recommendations"][0]
    rec_id = first_rec["recommendation_id"]
    cat = first_rec["intervention_type"]

    # Log acted_upon feedback
    fb_res = intervention_engine.log_feedback(
        recommendation_id=rec_id,
        status="acted_upon",
        feedback_notes="Counselor dispatched emergency legal aid team."
    )
    assert fb_res["status"] == "logged"
    assert fb_res["feedback_status"] == "acted_upon"

    # Verify DB update
    db = SessionLocal()
    try:
        db_rec = db.query(InterventionRecommendation).filter_by(id=rec_id).first()
        assert db_rec.status == "acted_upon"
        assert db_rec.recommendation_details["feedback_notes"] == "Counselor dispatched emergency legal aid team."
    finally:
        db.close()

def test_api_intervention_endpoints():
    vid = f"api_victim_{uuid.uuid4().hex[:6]}"
    payload = {
        "victim_id": vid,
        "case_type": "sexual_assault_rape",
        "risk_profile": {"risk_tier": "critical"}
    }

    # POST /api/interventions/recommend
    res = client.post("/api/interventions/recommend", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["case_type"] == "sexual_assault_rape"
    assert len(data["recommendations"]) > 0
    rec_id = data["recommendations"][0]["recommendation_id"]

    # GET /api/interventions/rules
    res_rules = client.get("/api/interventions/rules")
    assert res_rules.status_code == 200
    assert "sexual_assault_rape" in res_rules.json()

    # PATCH /api/interventions/{id}/feedback
    fb_payload = {"status": "acted_upon", "feedback_notes": "Medical unit assigned."}
    res_fb = client.patch(f"/api/interventions/{rec_id}/feedback", json=fb_payload)
    assert res_fb.status_code == 200
    assert res_fb.json()["status"] == "logged"
