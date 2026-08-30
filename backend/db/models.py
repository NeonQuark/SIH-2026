import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, JSON, DateTime, ForeignKey, Boolean
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from backend.db.session import Base
from backend.security.crypto import PIICrypto

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    """System user table for authentication and RBAC claims."""
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="counsellor")  # district_officer, state_officer, counsellor, national_admin
    jurisdiction = Column(String(100), nullable=False, default="Hathras")
    full_name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class VictimProfile(Base):
    """Victim profile linked to SC/ST Prevention of Atrocities Act case ID.
    
    PII fields (case_id, name, phone, address, contact) are encrypted at rest
    and separated from analytics tables via the pseudonymized victim_id join key.
    """
    __tablename__ = "victims"
    __table_args__ = {'extend_existing': True}

    victim_id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Encrypted columns stored at rest
    _case_id_enc = Column("case_id_enc", Text, nullable=True)
    _name_enc = Column("name_enc", Text, nullable=True)
    _phone_enc = Column("phone_enc", Text, nullable=True)
    _address_enc = Column("address_enc", Text, nullable=True)
    _contact_enc = Column("contact_enc", Text, nullable=True)

    # Non-PII analytical metadata
    district = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)
    caste_category = Column(String(50), nullable=True)  # e.g., SC, ST
    gender = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Hybrid properties for transparent PII encryption & decryption
    @hybrid_property
    def case_id(self) -> str | None:
        return PIICrypto.decrypt(self._case_id_enc)

    @case_id.setter
    def case_id(self, val: str | None):
        self._case_id_enc = PIICrypto.encrypt(val)

    @hybrid_property
    def name(self) -> str | None:
        return PIICrypto.decrypt(self._name_enc)

    @name.setter
    def name(self, val: str | None):
        self._name_enc = PIICrypto.encrypt(val)

    @hybrid_property
    def phone(self) -> str | None:
        return PIICrypto.decrypt(self._phone_enc)

    @phone.setter
    def phone(self, val: str | None):
        self._phone_enc = PIICrypto.encrypt(val)

    @hybrid_property
    def address(self) -> str | None:
        return PIICrypto.decrypt(self._address_enc)

    @address.setter
    def address(self, val: str | None):
        self._address_enc = PIICrypto.encrypt(val)

    @hybrid_property
    def contact(self) -> str | None:
        return PIICrypto.decrypt(self._contact_enc)

    @contact.setter
    def contact(self, val: str | None):
        self._contact_enc = PIICrypto.encrypt(val)

    # Relationships to pseudonymized analytics tables
    interaction_logs = relationship("InteractionLog", back_populates="victim", cascade="all, delete-orphan")
    distress_scores = relationship("DistressScore", back_populates="victim", cascade="all, delete-orphan")
    risk_alerts = relationship("RiskAlert", back_populates="victim", cascade="all, delete-orphan")
    intervention_recommendations = relationship("InterventionRecommendation", back_populates="victim", cascade="all, delete-orphan")

class InteractionLog(Base):
    """Interaction logs from multi-channel intake."""
    __tablename__ = "interaction_logs"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    victim_id = Column(String(36), ForeignKey("victims.victim_id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # chatbot, ivrs, sms, web_portal, mobile_app
    timestamp = Column(DateTime(timezone=True), default=utcnow, index=True)
    transcript_text = Column(Text, nullable=True)
    raw_sentiment_score = Column(Float, nullable=True)  # -1.0 to +1.0
    raw_emotion_scores = Column(JSON, nullable=True)  # {"fear": 0.8, "sadness": 0.5, ...}

    victim = relationship("VictimProfile", back_populates="interaction_logs")

class DistressScore(Base):
    """Dynamic distress score engine metrics and longitudinal records."""
    __tablename__ = "distress_scores"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    victim_id = Column(String(36), ForeignKey("victims.victim_id"), nullable=False, index=True)
    score = Column(Float, nullable=False)  # 0 to 100
    timestamp = Column(DateTime(timezone=True), default=utcnow, index=True)
    contributing_factors = Column(JSON, nullable=True)  # {"mood": 4, "anxiety": 5, "safety": 5}
    model_version = Column(String(50), nullable=False, default="v1.0.0-rf160")
    confidence = Column(Float, nullable=False, default=1.0)  # 0.0 to 1.0

    victim = relationship("VictimProfile", back_populates="distress_scores")
    risk_alerts = relationship("RiskAlert", back_populates="distress_score")

class RiskAlert(Base):
    """Predictive risk alerts for officers and counsellors with jurisdictional routing & SLA tracking."""
    __tablename__ = "risk_alerts"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    victim_id = Column(String(36), ForeignKey("victims.victim_id"), nullable=False, index=True)
    distress_score_id = Column(Integer, ForeignKey("distress_scores.id"), nullable=True)
    trigger_reason = Column(Text, nullable=False)
    threshold_crossed = Column(String(50), nullable=False)  # e.g., "Critical Threshold 75.0"
    assigned_officer_or_counsellor = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="Open")  # Open, In_Review, Escalated, Resolved, ACKNOWLEDGED

    # Jurisdictional Routing & Multi-Channel Delivery
    jurisdiction_level = Column(String(20), nullable=False, default="district")  # district, state, national
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    recipient_role = Column(String(50), nullable=True)  # District_Officer, State_Commission, National_Cell
    recipient_contact = Column(String(100), nullable=True)
    delivery_channels = Column(JSON, nullable=True)  # ["dashboard", "sms", "email"]
    cooldown_until = Column(DateTime(timezone=True), nullable=True)

    # SLA Tracking
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    sla_due_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    sla_status = Column(String(20), nullable=False, default="IN_SLA")  # IN_SLA, BREACHED, ACKNOWLEDGED
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    victim = relationship("VictimProfile", back_populates="risk_alerts")
    distress_score = relationship("DistressScore", back_populates="risk_alerts")

class InterventionRecommendation(Base):
    """Actionable intervention recommendations mapped to cases."""
    __tablename__ = "intervention_recommendations"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    victim_id = Column(String(36), ForeignKey("victims.victim_id"), nullable=False, index=True)
    linked_case_id = Column(String(255), nullable=True)  # SC/ST Act Case ID reference
    intervention_type = Column(String(100), nullable=False)  # Police_Escort, Counseling, Legal_Aid, Medical, Shelter
    status = Column(String(50), nullable=False, default="Pending")  # Pending, Approved, In_Progress, Completed, Rejected
    recommendation_details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    victim = relationship("VictimProfile", back_populates="intervention_recommendations")

class AuditLog(Base):
    """Immutable audit trail logging every access to individual case data (who, when, what)."""
    __tablename__ = "audit_logs"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    user_role = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)  # READ_CASE_TIMELINE, VIEW_VICTIM_PROFILE, EXPORT_ANALYTICS, UPDATE_INTERVENTION
    resource_type = Column(String(50), nullable=False)  # victim_profile, interaction_log, distress_score, risk_alert
    resource_id = Column(String(100), nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, index=True)
    details = Column(JSON, nullable=True)

class ChannelConsent(Base):
    """Multi-channel communication consent and opt-in/opt-out tracking."""
    __tablename__ = "channel_consents"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    victim_id = Column(String(36), ForeignKey("victims.victim_id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # chatbot, ivrs, sms, web_portal, mobile_app
    consent_granted = Column(Boolean, nullable=False, default=True)
    consent_timestamp = Column(DateTime(timezone=True), default=utcnow, index=True)
    opt_out_timestamp = Column(DateTime(timezone=True), nullable=True)
    consent_purpose = Column(String(255), nullable=False, default="Victim distress monitoring & emergency alert dispatch")
