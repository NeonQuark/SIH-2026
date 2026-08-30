import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.ml.dataset_generator import generate_synthetic_dataset, generate_engineered_features
from backend.ml.escalation_model import predictive_risk_model, PredictiveRiskModel
from backend.services.predictive_risk_service import predict_risk_for_victim
from backend.db.session import SessionLocal
from backend.db.models import VictimProfile, DistressScore, RiskAlert

client = TestClient(app)

def test_synthetic_dataset_generation():
    X, y_reg, y_cls, feature_names = generate_synthetic_dataset(n_trajectories=100)
    assert X.shape[0] > 0
    assert X.shape[1] == 8
    assert len(y_reg) == X.shape[0]
    assert len(y_cls) == X.shape[0]
    assert len(feature_names) == 8

def test_engineered_features_extraction():
    scores = [20.0, 25.0, 30.0, 45.0, 60.0]
    feats = generate_engineered_features(scores)
    assert feats["recent_score"] == 60.0
    assert feats["score_velocity"] > 0.0
    assert feats["consecutive_increases"] == 4.0

def test_model_training_and_low_risk_prediction():
    model = PredictiveRiskModel()
    train_res = model.train()
    assert train_res["status"] == "trained"
    assert train_res["samples"] > 1000

    # Improving low-risk trajectory
    improving_scores = [70.0, 55.0, 40.0, 25.0, 15.0]
    res = model.predict(improving_scores)

    assert "escalation_probability" in res
    assert "projected_score_next_period" in res
    assert res["risk_tier"] in ["low", "medium"]
    assert res["crisis_threshold_crossed_forecast"] is False
    assert "feature_importances" in res

def test_model_critical_risk_escalation_prediction():
    model = PredictiveRiskModel()
    model.load()

    # Accelerating crisis trajectory
    crisis_scores = [35.0, 48.0, 62.0, 76.0, 88.0]
    res = model.predict(crisis_scores)

    assert res["projected_score_next_period"] >= 70.0
    assert res["escalation_probability"] > 0.50
    assert res["risk_tier"] == "critical"
    assert res["crisis_threshold_crossed_forecast"] is True

def test_predictive_risk_service_auto_alert():
    db = SessionLocal()
    try:
        victim = VictimProfile(name="Risk Test Victim")
        db.add(victim)
        db.commit()
        vid = victim.victim_id

        # Insert escalating scores
        for score_val in [40.0, 55.0, 70.0, 85.0]:
            ds = DistressScore(victim_id=vid, score=score_val)
            db.add(ds)
        db.commit()

        # Run service prediction
        res = predict_risk_for_victim(vid, db=db)
        assert res["risk_tier"] == "critical"
        assert res["auto_alert_created"] is True

        # Check DB for created RiskAlert
        alert = db.query(RiskAlert).filter_by(victim_id=vid).first()
        assert alert is not None
        assert alert.status == "Open"
        assert "Predictive Escalation Warning" in alert.trigger_reason
    finally:
        db.close()

def test_api_risk_predict_endpoint():
    payload = {"scores": [30.0, 45.0, 60.0, 75.0]}
    res = client.post("/api/risk/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "escalation_probability" in data
    assert "projected_score_next_period" in data
    assert "risk_tier" in data
    assert "feature_importances" in data

def test_api_risk_predict_victim_endpoint():
    res = client.get("/api/risk/predict/non-existent-victim")
    assert res.status_code == 200
    data = res.json()
    assert data["risk_tier"] == "low"
