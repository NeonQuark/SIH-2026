from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.models import DistressScore, RiskAlert, VictimProfile
from backend.ml.escalation_model import predictive_risk_model

def predict_risk_for_victim(victim_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
    """Retrieve longitudinal distress scores for victim, run escalation prediction, and handle auto-alerts."""
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        records = (
            db.query(DistressScore)
            .filter(DistressScore.victim_id == victim_id)
            .order_by(DistressScore.timestamp.asc())
            .all()
        )

        scores = [r.score for r in records] if records else [0.0]
        prediction = predictive_risk_model.predict(scores)
        prediction["victim_id"] = victim_id

        # Auto-create RiskAlert if critical risk forecasted
        if prediction["risk_tier"] == "critical":
            last_ds_id = records[-1].id if records else None
            trigger_msg = (
                f"Predictive Escalation Warning: Projected score {prediction['projected_score_next_period']} "
                f"with {int(prediction['escalation_probability']*100)}% escalation probability."
            )
            
            # Check if an open alert already exists
            existing_open = (
                db.query(RiskAlert)
                .filter(RiskAlert.victim_id == victim_id, RiskAlert.status == "Open")
                .first()
            )
            
            if not existing_open:
                alert = RiskAlert(
                    victim_id=victim_id,
                    distress_score_id=last_ds_id,
                    trigger_reason=trigger_msg,
                    threshold_crossed=f"Forecasted Score {prediction['projected_score_next_period']}",
                    status="Open"
                )
                db.add(alert)
                db.commit()
                prediction["auto_alert_created"] = True
            else:
                prediction["auto_alert_created"] = False

        return prediction
    finally:
        if close_session:
            db.close()
