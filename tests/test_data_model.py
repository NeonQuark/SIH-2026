import sqlite3
import pytest
from sqlalchemy import inspect
from backend.db.session import engine, SessionLocal, DB_PATH
from backend.db.migrations.migration_001_initial_schema import run_migration
from backend.db.models import (
    VictimProfile, InteractionLog, DistressScore, RiskAlert, InterventionRecommendation
)

@pytest.fixture(autouse=True)
def setup_db():
    run_migration(engine)

def test_migration_table_creation():
    """Verify that all 5 core tables are created in the database."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected_tables = {
        "victims",
        "interaction_logs",
        "distress_scores",
        "risk_alerts",
        "intervention_recommendations"
    }
    for table in expected_tables:
        assert table in tables, f"Table '{table}' should exist in database schema"

def test_pii_encryption_at_rest():
    """Verify that PII fields are encrypted at rest in raw DB storage and decrypted via ORM getters."""
    db = SessionLocal()
    try:
        # Create victim with PII
        victim = VictimProfile(
            case_id="SC-ST-2026-9042",
            name="Priya Sharma",
            phone="9123456789",
            address="Village Rampur, District Hathras",
            contact="relative@email.com",
            district="Hathras",
            state="Uttar Pradesh",
            caste_category="SC",
            gender="Female"
        )
        db.add(victim)
        db.commit()
        victim_id = victim.victim_id

        # 1. ORM Decryption check
        fetched = db.query(VictimProfile).filter_by(victim_id=victim_id).first()
        assert fetched.case_id == "SC-ST-2026-9042"
        assert fetched.name == "Priya Sharma"
        assert fetched.phone == "9123456789"
        assert fetched.address == "Village Rampur, District Hathras"
        assert fetched.contact == "relative@email.com"

        # 2. Raw SQLite query check - ensure ciphertext in DB, zero plaintext PII
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT case_id_enc, name_enc, phone_enc, address_enc, contact_enc FROM victims WHERE victim_id=?", (victim_id,))
        raw_row = cursor.fetchone()
        conn.close()

        case_enc, name_enc, phone_enc, address_enc, contact_enc = raw_row

        # Ciphertext assertions
        assert "SC-ST-2026-9042" not in case_enc
        assert "Priya Sharma" not in name_enc
        assert "9123456789" not in phone_enc
        assert "Village Rampur" not in address_enc

        assert name_enc.startswith("gAAAAA")  # Fernet token header

    finally:
        db.close()

def test_pseudonymized_analytics_joins():
    """Verify that analytics tables join strictly via pseudonymized victim_id."""
    db = SessionLocal()
    try:
        victim = VictimProfile(
            case_id="SC-ST-2026-1102",
            name="Anonymized Victim",
            district="Lucknow",
            state="Uttar Pradesh",
            caste_category="ST"
        )
        db.add(victim)
        db.commit()
        vid = victim.victim_id

        # 1. Add InteractionLog
        log = InteractionLog(
            victim_id=vid,
            channel="chatbot",
            transcript_text="I feel unsafe in my village.",
            raw_sentiment_score=-0.75,
            raw_emotion_scores={"fear": 0.85, "anxiety": 0.9}
        )
        db.add(log)

        # 2. Add DistressScore
        ds = DistressScore(
            victim_id=vid,
            score=82.5,
            contributing_factors={"mood": 4, "anxiety": 5, "safety": 5},
            model_version="v1.0.0-rf160",
            confidence=0.92
        )
        db.add(ds)
        db.commit()

        # 3. Add RiskAlert
        alert = RiskAlert(
            victim_id=vid,
            distress_score_id=ds.id,
            trigger_reason="High distress score threshold breach (>80) with safety concern",
            threshold_crossed="Critical Threshold 80.0",
            assigned_officer_or_counsellor="Officer_Kumar_Hathras",
            status="Open"
        )
        db.add(alert)

        # 4. Add InterventionRecommendation
        rec = InterventionRecommendation(
            victim_id=vid,
            linked_case_id="SC-ST-2026-1102",
            intervention_type="Immediate_Police_Escort",
            status="Pending",
            recommendation_details={"action": "Dispatch patrol team to site"}
        )
        db.add(rec)
        db.commit()

        # Verify ORM Relationships
        refreshed_victim = db.query(VictimProfile).filter_by(victim_id=vid).first()
        assert len(refreshed_victim.interaction_logs) == 1
        assert refreshed_victim.interaction_logs[0].channel == "chatbot"
        assert refreshed_victim.interaction_logs[0].raw_emotion_scores["fear"] == 0.85

        assert len(refreshed_victim.distress_scores) == 1
        assert refreshed_victim.distress_scores[0].score == 82.5

        assert len(refreshed_victim.risk_alerts) == 1
        assert refreshed_victim.risk_alerts[0].status == "Open"

        assert len(refreshed_victim.intervention_recommendations) == 1
        assert refreshed_victim.intervention_recommendations[0].intervention_type == "Immediate_Police_Escort"

    finally:
        db.close()
