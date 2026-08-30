"""Migration 001: Initial Core Data Model Schema for Victim Distress Monitoring.

Creates tables:
- victims (Victim/Complainant profile with PII fields encrypted at rest)
- interaction_logs (Multi-channel intake records)
- distress_scores (Longitudinal distress scores & model metrics)
- risk_alerts (Officer & counsellor alerts)
- intervention_recommendations (Intervention SOP recommendations)
"""
import logging
from backend.db.session import engine, Base
from backend.db.models import (
    VictimProfile, InteractionLog, DistressScore, RiskAlert, InterventionRecommendation, AuditLog, ChannelConsent
)

logger = logging.getLogger(__name__)

def run_migration(target_engine=None):
    if target_engine is None:
        target_engine = engine
    logger.info("Executing Migration 001: Initial Core Schema creation...")
    Base.metadata.create_all(bind=target_engine)

    # Ensure alter columns exist for risk_alerts table on existing SQLite DBs
    try:
        with target_engine.connect() as conn:
            columns_to_add = [
                ("jurisdiction_level", "VARCHAR(20) DEFAULT 'district'"),
                ("district", "VARCHAR(100)"),
                ("state", "VARCHAR(100)"),
                ("recipient_role", "VARCHAR(50)"),
                ("recipient_contact", "VARCHAR(100)"),
                ("delivery_channels", "TEXT"),
                ("cooldown_until", "DATETIME"),
                ("sla_due_at", "DATETIME"),
                ("acknowledged_at", "DATETIME"),
                ("acknowledged_by", "VARCHAR(100)"),
                ("sla_status", "VARCHAR(20) DEFAULT 'IN_SLA'")
            ]
            for col_name, col_type in columns_to_add:
                try:
                    conn.execute(f"ALTER TABLE risk_alerts ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass  # Column already exists
    except Exception:
        pass

    logger.info("Migration 001 completed successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
