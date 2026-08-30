import uuid
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.privacy_service import privacy_service, PrivacyAuditService
from backend.db.session import SessionLocal
from backend.db.models import VictimProfile, InteractionLog, DistressScore, AuditLog, ChannelConsent

client = TestClient(app)

def test_pii_masking_utility():
    assert privacy_service.mask_name("Dr. Ananya Rao") == "D*** A*** R***"
    assert privacy_service.mask_phone("+919876543210") == "+91*****3210"
    assert privacy_service.mask_email("ananya.rao@saathicare.demo") == "a***@saathicare.demo"

def test_audit_logging_and_retrieval():
    res_id = f"resource_{uuid.uuid4().hex[:6]}"

    # Log access
    res = privacy_service.audit_access(
        user_id="officer_singh",
        user_role="district_officer",
        action="READ_CASE_TIMELINE",
        resource_type="victim_profile",
        resource_id=res_id,
        details={"reason": "Emergency assessment"}
    )
    assert res["status"] == "logged"

    # Query audit logs
    logs = privacy_service.get_audit_logs(resource_id=res_id)
    assert len(logs) == 1
    log = logs[0]
    assert log["user_id"] == "officer_singh"
    assert log["action"] == "READ_CASE_TIMELINE"
    assert log["resource_id"] == res_id

def test_channel_consent_opt_in_and_opt_out():
    vid = f"victim_consent_{uuid.uuid4().hex[:6]}"

    # 1. Opt-in SMS
    res1 = privacy_service.update_channel_consent(victim_id=vid, channel="sms", consent_granted=True)
    assert res1["status"] == "updated"
    assert res1["consent_granted"] is True

    consents1 = privacy_service.get_channel_consents(victim_id=vid)
    sms_c = next(c for c in consents1 if c["channel"] == "sms")
    assert sms_c["consent_granted"] is True
    assert sms_c["opt_out_timestamp"] is None

    # 2. Opt-out SMS
    res2 = privacy_service.update_channel_consent(victim_id=vid, channel="sms", consent_granted=False)
    assert res2["consent_granted"] is False

    consents2 = privacy_service.get_channel_consents(victim_id=vid)
    sms_c2 = next(c for c in consents2 if c["channel"] == "sms")
    assert sms_c2["consent_granted"] is False
    assert sms_c2["opt_out_timestamp"] is not None

def test_data_retention_purge_and_erasure_hooks():
    db = SessionLocal()
    try:
        vid = f"victim_purge_{uuid.uuid4().hex[:6]}"
        v = VictimProfile(victim_id=vid, name="Purge Test Victim")
        db.add(v)

        # Old log (400 days ago)
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=400)
        old_log = InteractionLog(victim_id=vid, channel="sms", timestamp=old_time, transcript_text="Old message")
        db.add(old_log)
        db.commit()

        # Purge data older than 365 days
        purge_res = privacy_service.purge_expired_data(retention_days=365, db=db)
        assert purge_res["status"] == "purged"
        assert purge_res["purged_interaction_logs"] >= 1

        # Test victim erasure hook
        erase_res = privacy_service.erase_victim_data(victim_id=vid, db=db)
        assert erase_res["status"] == "erased"

        # Verify victim is completely removed
        v_check = db.query(VictimProfile).filter_by(victim_id=vid).first()
        assert v_check is None
    finally:
        db.close()

def test_api_privacy_endpoints():
    vid = f"v_api_priv_{uuid.uuid4().hex[:6]}"

    # POST /api/privacy/consent
    res_c = client.post("/api/privacy/consent", json={"victim_id": vid, "channel": "whatsapp", "consent_granted": True})
    # WhatsApp is invalid -> should return error
    assert res_c.json()["status"] == "error"

    res_sms = client.post("/api/privacy/consent", json={"victim_id": vid, "channel": "sms", "consent_granted": True})
    assert res_sms.status_code == 200
    assert res_sms.json()["status"] == "updated"

    # GET /api/privacy/consent/{victim_id}
    res_get_c = client.get(f"/api/privacy/consent/{vid}")
    assert res_get_c.status_code == 200
    assert len(res_get_c.json()) > 0

    # GET /api/privacy/audit-logs
    res_audit = client.get("/api/privacy/audit-logs")
    assert res_audit.status_code == 200
    assert isinstance(res_audit.json(), list)

    # POST /api/privacy/purge-expired
    res_purge = client.post("/api/privacy/purge-expired", json={"retention_days": 365})
    assert res_purge.status_code == 200
    assert res_purge.json()["status"] == "purged"
