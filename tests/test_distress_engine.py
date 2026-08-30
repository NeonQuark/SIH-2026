import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.distress_engine import DynamicDistressEngine, distress_engine
from backend.db.session import SessionLocal
from backend.db.models import VictimProfile, DistressScore

client = TestClient(app)

def test_distress_score_low_risk():
    nlp_output = {
        "sentiment_score": 0.60,
        "sentiment_label": "positive",
        "emotion_labels": {"fear": 0.05, "anxiety": 0.10, "sadness": 0.05, "anger": 0.0, "neutral": 0.80},
        "voice_stress_score": 0.10,
        "confidence": 0.90
    }
    behavioral_signals = {
        "engagement_frequency": 5,
        "missed_checkins": 0,
        "response_latency_hours": 1.5,
        "drop_off_rate": 0.05
    }

    engine = DynamicDistressEngine()
    res = engine.calculate_score(nlp_output, behavioral_signals, save_to_db=False)

    assert res["distress_score"] < 35.0
    assert res["risk_level"] == "Low"
    assert "explainability" in res
    assert len(res["explainability"]["feature_contributions"]) == 7

def test_distress_score_critical_risk_and_explainability():
    nlp_output = {
        "sentiment_score": -0.85,
        "sentiment_label": "negative",
        "emotion_labels": {"fear": 0.92, "anxiety": 0.80, "sadness": 0.60, "anger": 0.20, "neutral": 0.02},
        "voice_stress_score": 0.88,
        "confidence": 0.95
    }
    behavioral_signals = {
        "engagement_frequency": 1,
        "missed_checkins": 4,
        "response_latency_hours": 48.0,
        "drop_off_rate": 0.75
    }

    engine = DynamicDistressEngine()
    res = engine.calculate_score(nlp_output, behavioral_signals, save_to_db=False)

    assert res["distress_score"] >= 80.0
    assert res["risk_level"] == "Critical"

    explainability = res["explainability"]
    assert explainability["method"] == "Additive Rule-Based Feature Attribution"
    top_feature = explainability["feature_contributions"][0]
    assert top_feature["impact_points"] > 10.0
    assert top_feature["feature"] in ["fear_emotion", "missed_checkins", "negative_sentiment", "voice_stress"]

def test_longitudinal_trend_analysis():
    db = SessionLocal()
    try:
        victim = VictimProfile(name="Trend Test Victim")
        db.add(victim)
        db.commit()
        vid = victim.victim_id

        now = datetime.now(timezone.utc)
        # Add historical scores (early = 20, recent = 80)
        ds1 = DistressScore(victim_id=vid, score=20.0, timestamp=now - timedelta(days=20))
        ds2 = DistressScore(victim_id=vid, score=25.0, timestamp=now - timedelta(days=15))
        ds3 = DistressScore(victim_id=vid, score=80.0, timestamp=now - timedelta(days=5))
        ds4 = DistressScore(victim_id=vid, score=85.0, timestamp=now - timedelta(days=1))
        db.add_all([ds1, ds2, ds3, ds4])
        db.commit()

        trend = distress_engine.compute_longitudinal_trend(victim_id=vid, window_days=30, db=db)

        assert trend["window_days"] == 30
        assert trend["direction"] == "worsening"
        assert trend["delta_points"] > 10.0
        assert trend["record_count"] == 4
    finally:
        db.close()

def test_api_distress_calculate_endpoint():
    payload = {
        "victim_id": "test-victim-123",
        "nlp_output": {
            "sentiment_score": -0.50,
            "emotion_labels": {"fear": 0.60, "anxiety": 0.50},
            "voice_stress_score": 0.65
        },
        "behavioral_signals": {
            "missed_checkins": 2,
            "response_latency_hours": 24.0,
            "drop_off_rate": 0.30
        }
    }

    res = client.post("/api/distress/calculate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "distress_score" in data
    assert "risk_level" in data
    assert "explainability" in data
    assert data["explainability"]["method"] == "Additive Rule-Based Feature Attribution"

def test_api_distress_history_endpoint():
    res = client.get("/api/distress/history/test-victim-123?window_days=30")
    assert res.status_code == 200
    data = res.json()
    assert data["window_days"] == 30
    assert "direction" in data
    assert "historical_avg" in data
