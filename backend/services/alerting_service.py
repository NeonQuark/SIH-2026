from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.models import RiskAlert, VictimProfile

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class DashboardNotifier:
    @staticmethod
    def send(recipient: str, message: str) -> Dict[str, Any]:
        return {"status": "sent", "channel": "dashboard", "recipient": recipient, "payload": message}

class SMSNotifier:
    @staticmethod
    def send(phone: str, message: str) -> Dict[str, Any]:
        return {"status": "sent", "channel": "sms", "recipient": phone, "payload": message}

class EmailNotifier:
    @staticmethod
    def send(email: str, subject: str, body: str) -> Dict[str, Any]:
        return {"status": "sent", "channel": "email", "recipient": email, "subject": subject, "payload": body}


class RealtimeAlertingService:
    """Real-Time Alerting Service with Jurisdictional Escalation, Multi-Channel Delivery, Cooldown Deduplication, and SLA Tracking."""

    COOLDOWN_MINUTES = 60

    def resolve_jurisdiction(self, victim: VictimProfile, risk_prediction: Dict[str, Any]) -> Dict[str, Any]:
        """Determine recipient and SLA target based on case jurisdiction (District -> State -> National)."""
        district = victim.district or "Default_District"
        state = victim.state or "Default_State"
        risk_tier = risk_prediction.get("risk_tier", "high")
        trend_direction = risk_prediction.get("trend", {}).get("direction", "stable")

        # Routing rules:
        # 1. Critical + Worsening -> State Commission
        # 2. Critical/High -> District Officer
        if risk_tier == "critical" and trend_direction == "worsening":
            level = "state"
            role = f"State_SC_ST_Commission_{state}"
            contact = f"state_commission@{state.lower().replace(' ', '')}.gov.in"
            sla_minutes = 60
        else:
            level = "district"
            role = f"District_Officer_{district}"
            contact = f"district_officer@{district.lower().replace(' ', '')}.gov.in"
            sla_minutes = 30 if risk_tier == "critical" else 120

        return {
            "jurisdiction_level": level,
            "district": district,
            "state": state,
            "recipient_role": role,
            "recipient_contact": contact,
            "sla_minutes": sla_minutes
        }

    def dispatch_alert(
        self,
        victim_id: str,
        risk_prediction: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Process risk event, apply deduplication cooldown, route jurisdictionally, dispatch multi-channel alerts, and log SLA."""
        hard_trigger_detected = bool(risk_prediction.get("hard_trigger_detected"))
        alert_reason = "hard_trigger_override" if hard_trigger_detected else risk_prediction.get("alert_reason", "model_driven_escalation")

        if hard_trigger_detected:
            risk_tier = "critical"
            risk_prediction["risk_tier"] = "critical"
        else:
            risk_tier = risk_prediction.get("risk_tier", "high")
            if risk_tier not in ["high", "critical"]:
                return {"status": "ignored", "reason": f"Risk tier '{risk_tier}' does not require escalation alert"}

        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            now = utcnow()

            # 1. Deduplication Cooldown Check
            existing_active = (
                db.query(RiskAlert)
                .filter(
                    RiskAlert.victim_id == victim_id,
                    RiskAlert.status.in_(["Open", "In_Review"]),
                    RiskAlert.cooldown_until >= now
                )
                .first()
            )

            if existing_active:
                return {
                    "status": "deduplicated",
                    "reason": "Suppressed repeated alert trigger within 60-minute cooldown window",
                    "alert_id": existing_active.id,
                    "cooldown_until": existing_active.cooldown_until.isoformat()
                }

            # 2. Fetch Victim Profile & Resolve Jurisdiction
            victim = db.query(VictimProfile).filter_by(victim_id=victim_id).first()
            if not victim:
                victim = VictimProfile(victim_id=victim_id, district="Default_District", state="Default_State")
                db.add(victim)
                db.commit()

            routing = self.resolve_jurisdiction(victim, risk_prediction)
            sla_due_at = now + timedelta(minutes=routing["sla_minutes"])
            cooldown_until = now + timedelta(minutes=self.COOLDOWN_MINUTES)

            # 3. Multi-Channel Alert Delivery
            msg_text = (
                f"ALERT [{risk_tier.upper()} RISK]: Victim {victim_id[:8]}... in {routing['district']} "
                f"has projected distress score {risk_prediction.get('projected_score_next_period', 75.0)}. "
                f"SLA Target: Respond within {routing['sla_minutes']} mins."
            )

            dash_res = DashboardNotifier.send(routing["recipient_role"], msg_text)
            sms_res = SMSNotifier.send(routing["recipient_contact"], msg_text)
            email_res = EmailNotifier.send(routing["recipient_contact"], f"Urgent: {risk_tier.upper()} Distress Alert", msg_text)

            channels = [dash_res, sms_res, email_res]

            # 4. Database Log & SLA Tracking
            alert = RiskAlert(
                victim_id=victim_id,
                trigger_reason=f"[{alert_reason}] Risk Tier '{risk_tier}' escalation threshold breach",
                threshold_crossed=f"Risk Tier: {risk_tier} (Reason: {alert_reason})",
                assigned_officer_or_counsellor=routing["recipient_role"],
                status="Open",
                jurisdiction_level=routing["jurisdiction_level"],
                district=routing["district"],
                state=routing["state"],
                recipient_role=routing["recipient_role"],
                recipient_contact=routing["recipient_contact"],
                delivery_channels=[c["channel"] for c in channels],
                cooldown_until=cooldown_until,
                created_at=now,
                sla_due_at=sla_due_at,
                sla_status="IN_SLA"
            )
            db.add(alert)
            db.commit()

            return {
                "status": "dispatched",
                "alert_id": alert.id,
                "victim_id": victim_id,
                "risk_tier": risk_tier,
                "alert_reason": alert_reason,
                "jurisdiction_level": routing["jurisdiction_level"],
                "assigned_recipient": routing["recipient_role"],
                "delivery_channels": [c["channel"] for c in channels],
                "sla_due_at": sla_due_at.isoformat(),
                "cooldown_until": cooldown_until.isoformat()
            }
        finally:
            if close_session:
                db.close()

    def acknowledge_alert(
        self,
        alert_id: int,
        officer_name: str,
        notes: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Acknowledge an alert, record officer response time, and evaluate SLA compliance."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            alert = db.query(RiskAlert).filter_by(id=alert_id).first()
            if not alert:
                return {"status": "error", "reason": f"Alert ID {alert_id} not found"}

            now = utcnow()
            alert.acknowledged_at = now
            alert.acknowledged_by = officer_name
            alert.status = "ACKNOWLEDGED"
            if notes:
                alert.resolution_notes = notes

            # Evaluate SLA compliance
            if alert.sla_due_at and now > alert.sla_due_at:
                alert.sla_status = "BREACHED"
            else:
                alert.sla_status = "IN_SLA"

            db.commit()

            return {
                "status": "acknowledged",
                "alert_id": alert.id,
                "officer_name": officer_name,
                "acknowledged_at": now.isoformat(),
                "sla_status": alert.sla_status,
                "sla_due_at": alert.sla_due_at.isoformat() if alert.sla_due_at else None
            }
        finally:
            if close_session:
                db.close()

    def get_active_alerts(self, jurisdiction_level: Optional[str] = None, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Retrieve active/open alerts filtered by jurisdiction level."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            query = db.query(RiskAlert).filter(RiskAlert.status.in_(["Open", "In_Review"]))
            if jurisdiction_level:
                query = query.filter(RiskAlert.jurisdiction_level == jurisdiction_level)

            records = query.order_by(RiskAlert.created_at.desc()).all()
            
            result = []
            for r in records:
                # Check SLA breach status dynamically
                is_breached = r.sla_due_at and utcnow() > r.sla_due_at and r.status != "ACKNOWLEDGED"
                result.append({
                    "id": r.id,
                    "victim_id": r.victim_id,
                    "trigger_reason": r.trigger_reason,
                    "jurisdiction_level": r.jurisdiction_level,
                    "district": r.district,
                    "state": r.state,
                    "recipient_role": r.recipient_role,
                    "status": r.status,
                    "sla_status": "BREACHED" if is_breached else r.sla_status,
                    "sla_due_at": r.sla_due_at.isoformat() if r.sla_due_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                })
            return result
        finally:
            if close_session:
                db.close()

# Global singleton instance
alerting_service = RealtimeAlertingService()
