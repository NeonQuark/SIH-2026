from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.models import (
    AuditLog, ChannelConsent, VictimProfile, InteractionLog, DistressScore, RiskAlert, InterventionRecommendation
)

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class PrivacyAuditService:
    """Privacy, Security Audit Logging, Data Retention Purge, Channel Consent, and PII Masking Service."""

    @staticmethod
    def mask_name(name: Optional[str]) -> Optional[str]:
        if not name:
            return name
        parts = name.strip().split()
        masked = [p[0] + "***" if len(p) > 1 else p for p in parts]
        return " ".join(masked)

    @staticmethod
    def mask_phone(phone: Optional[str]) -> Optional[str]:
        if not phone or len(phone) < 7:
            return "*****"
        return phone[:3] + "*****" + phone[-4:]

    @staticmethod
    def mask_email(email: Optional[str]) -> Optional[str]:
        if not email or "@" not in email:
            return "*****"
        user, domain = email.split("@", 1)
        return user[0] + "***@" + domain

    def audit_access(
        self,
        user_id: str,
        user_role: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Record an immutable audit log entry for case data access or export."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            entry = AuditLog(
                user_id=user_id,
                user_role=user_role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                timestamp=utcnow(),
                details=details
            )
            db.add(entry)
            db.commit()
            return {"status": "logged", "audit_id": entry.id, "timestamp": entry.timestamp.isoformat()}
        finally:
            if close_session:
                db.close()

    def get_audit_logs(
        self,
        resource_id: Optional[str] = None,
        limit: int = 100,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve audit access logs for compliance reporting."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            query = db.query(AuditLog)
            if resource_id:
                query = query.filter(AuditLog.resource_id == resource_id)

            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            return [
                {
                    "audit_id": l.id,
                    "user_id": l.user_id,
                    "user_role": l.user_role,
                    "action": l.action,
                    "resource_type": l.resource_type,
                    "resource_id": l.resource_id,
                    "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                    "details": l.details
                }
                for l in logs
            ]
        finally:
            if close_session:
                db.close()

    def update_channel_consent(
        self,
        victim_id: str,
        channel: str,
        consent_granted: bool,
        purpose: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Track victim opt-in/opt-out consent per communication channel."""
        valid_channels = ["chatbot", "ivrs", "sms", "web_portal", "mobile_app"]
        norm_channel = channel.lower().strip()
        if norm_channel not in valid_channels:
            return {"status": "error", "reason": f"Invalid channel. Must be one of {valid_channels}"}

        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            now = utcnow()
            existing = (
                db.query(ChannelConsent)
                .filter_by(victim_id=victim_id, channel=norm_channel)
                .first()
            )

            if existing:
                existing.consent_granted = consent_granted
                if not consent_granted:
                    existing.opt_out_timestamp = now
                else:
                    existing.consent_timestamp = now
                    existing.opt_out_timestamp = None
            else:
                existing = ChannelConsent(
                    victim_id=victim_id,
                    channel=norm_channel,
                    consent_granted=consent_granted,
                    consent_timestamp=now,
                    opt_out_timestamp=None if consent_granted else now,
                    consent_purpose=purpose or "Victim distress monitoring & emergency alert dispatch"
                )
                db.add(existing)

            db.commit()

            return {
                "status": "updated",
                "victim_id": victim_id,
                "channel": norm_channel,
                "consent_granted": consent_granted,
                "timestamp": now.isoformat()
            }
        finally:
            if close_session:
                db.close()

    def get_channel_consents(
        self,
        victim_id: str,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve active communication channel consent statuses for a victim."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            records = db.query(ChannelConsent).filter_by(victim_id=victim_id).all()
            return [
                {
                    "channel": r.channel,
                    "consent_granted": r.consent_granted,
                    "consent_timestamp": r.consent_timestamp.isoformat() if r.consent_timestamp else None,
                    "opt_out_timestamp": r.opt_out_timestamp.isoformat() if r.opt_out_timestamp else None,
                    "purpose": r.consent_purpose
                }
                for r in records
            ]
        finally:
            if close_session:
                db.close()

    def purge_expired_data(
        self,
        retention_days: int = 365,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Data Retention Policy Hook: Purges interaction logs and distress scores older than retention window."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            cutoff_date = utcnow() - timedelta(days=retention_days)

            # Purge old interaction logs
            logs_deleted = (
                db.query(InteractionLog)
                .filter(InteractionLog.timestamp < cutoff_date)
                .delete(synchronize_session=False)
            )

            # Purge old distress scores
            scores_deleted = (
                db.query(DistressScore)
                .filter(DistressScore.timestamp < cutoff_date)
                .delete(synchronize_session=False)
            )

            db.commit()

            return {
                "status": "purged",
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "purged_interaction_logs": logs_deleted,
                "purged_distress_scores": scores_deleted
            }
        finally:
            if close_session:
                db.close()

    def erase_victim_data(
        self,
        victim_id: str,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Right to be Forgotten Deletion Policy Hook: Complete erasure of a victim's data."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            v = db.query(VictimProfile).filter_by(victim_id=victim_id).first()
            if not v:
                return {"status": "error", "reason": f"Victim ID {victim_id} not found"}

            db.query(InteractionLog).filter_by(victim_id=victim_id).delete(synchronize_session=False)
            db.query(DistressScore).filter_by(victim_id=victim_id).delete(synchronize_session=False)
            db.query(RiskAlert).filter_by(victim_id=victim_id).delete(synchronize_session=False)
            db.query(InterventionRecommendation).filter_by(victim_id=victim_id).delete(synchronize_session=False)
            db.query(ChannelConsent).filter_by(victim_id=victim_id).delete(synchronize_session=False)
            db.query(VictimProfile).filter_by(victim_id=victim_id).delete(synchronize_session=False)

            db.commit()

            return {
                "status": "erased",
                "victim_id": victim_id,
                "message": f"All data for victim {victim_id} has been permanently erased in compliance with DPDP Act 2023"
            }
        finally:
            if close_session:
                db.close()

# Global singleton service instance
privacy_service = PrivacyAuditService()
