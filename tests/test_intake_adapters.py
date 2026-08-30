import uuid
import struct
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.intake_adapters import intake_service, MultiChannelIntakeService
from backend.services.privacy_service import privacy_service
from backend.db.session import SessionLocal
from backend.db.models import InteractionLog, DistressScore, RiskAlert, VictimProfile

client = TestClient(app)

def create_synthetic_wav_bytes() -> bytes:
    sample_rate = 8000
    n_samples = 8000
    pcm = bytearray()
    for i in range(n_samples):
        sample = int(12000 * ((i % 100) / 100.0))
        pcm.extend(struct.pack('<h', sample))
    
    header = bytearray(b'RIFF')
    header.extend((36 + len(pcm)).to_bytes(4, 'little'))
    header.extend(b'WAVEfmt ')
    header.extend((16).to_bytes(4, 'little'))
    header.extend((1).to_bytes(2, 'little'))
    header.extend((1).to_bytes(2, 'little'))
    header.extend(sample_rate.to_bytes(4, 'little'))
    header.extend((sample_rate * 2).to_bytes(4, 'little'))
    header.extend((2).to_bytes(2, 'little'))
    header.extend((16).to_bytes(2, 'little'))
    header.extend(b'data')
    header.extend(len(pcm).to_bytes(4, 'little'))
    return bytes(header + pcm)

def test_chatbot_intake_processing():
    vid = f"v_bot_{uuid.uuid4().hex[:6]}"
    res = intake_service.process_chatbot_intake(
        victim_id=vid,
        message="Help, I am feeling extremely scared and threatened.",
        bot_session_id="BOT-9912",
        user_intent="emergency_distress",
        session_duration_sec=120
    )

    assert res["status"] == "processed"
    assert res["channel"] == "chatbot"
    assert res["nlp_analysis"]["sentiment_label"] in ["negative", "distress"]
    assert res["channel_metadata_preserved"]["bot_session_id"] == "BOT-9912"

    # Verify DB persistence
    db = SessionLocal()
    try:
        log = db.query(InteractionLog).filter_by(victim_id=vid).first()
        assert log is not None
        assert log.channel == "chatbot"
        assert log.raw_emotion_scores["_channel_metadata"]["user_intent"] == "emergency_distress"
    finally:
        db.close()

def test_ivrs_voice_intake_processing():
    vid = f"v_ivrs_{uuid.uuid4().hex[:6]}"
    wav_bytes = create_synthetic_wav_bytes()

    res = intake_service.process_ivrs_intake(
        victim_id=vid,
        audio_bytes=wav_bytes,
        transcribed_text="mujhe bachao, urgent madad chahiye",
        call_sid="CA12345678",
        call_duration_sec=180,
        caller_state="Uttar Pradesh"
    )

    assert res["status"] == "processed"
    assert res["channel"] == "ivrs"
    assert "voice_stress_score" in res["nlp_analysis"]
    assert res["channel_metadata_preserved"]["call_duration_sec"] == 180

def test_sms_intake_processing():
    vid = f"v_sms_{uuid.uuid4().hex[:6]}"
    res = intake_service.process_sms_intake(
        victim_id=vid,
        sms_text="SOS police protection needed Hathras",
        sms_sid="SM998877",
        delivery_status="delivered"
    )

    assert res["status"] == "processed"
    assert res["channel"] == "sms"
    assert res["channel_metadata_preserved"]["sms_delivery_status"] == "delivered"

def test_mobile_app_and_web_portal_intake():
    vid_app = f"v_app_{uuid.uuid4().hex[:6]}"
    res_app = intake_service.process_mobile_app_intake(
        victim_id=vid_app,
        message="Emergency SOS alert triggered from app button",
        app_version="v2.4.1",
        device_os="Android 14",
        network_type="cellular"
    )
    assert res_app["status"] == "processed"
    assert res_app["channel_metadata_preserved"]["device_os"] == "Android 14"

    vid_web = f"v_web_{uuid.uuid4().hex[:6]}"
    res_web = intake_service.process_web_portal_intake(
        victim_id=vid_web,
        message="Filing urgent harassment report online",
        web_session_id="WEB-5511",
        user_agent="Chrome/128.0"
    )
    assert res_web["status"] == "processed"
    assert res_web["channel_metadata_preserved"]["web_session_id"] == "WEB-5511"

def test_opt_out_consent_suppression():
    vid = f"v_optout_{uuid.uuid4().hex[:6]}"
    # Opt-out of SMS
    privacy_service.update_channel_consent(victim_id=vid, channel="sms", consent_granted=False)

    res = intake_service.process_sms_intake(victim_id=vid, sms_text="Test message")
    assert res["status"] == "suppressed"
    assert "opted out" in res["reason"]

def test_api_intake_endpoints():
    vid = f"v_api_intake_{uuid.uuid4().hex[:6]}"

    # 1. Chatbot endpoint
    res_bot = client.post("/api/intake/chatbot", json={"victim_id": vid, "message": "Need counseling support"})
    assert res_bot.status_code == 200
    assert res_bot.json()["status"] == "processed"

    # 2. IVRS endpoint
    res_ivrs = client.post("/api/intake/ivrs", json={"victim_id": vid, "transcribed_text": "Emergency call", "call_duration_sec": 60})
    assert res_ivrs.status_code == 200

    # 3. SMS endpoint
    res_sms = client.post("/api/intake/sms", json={"victim_id": vid, "sms_text": "Help Hathras"})
    assert res_sms.status_code == 200

    # 4. Mobile App endpoint
    res_app = client.post("/api/intake/mobile-app", json={"victim_id": vid, "message": "Mobile checkin"})
    assert res_app.status_code == 200

    # 5. Web Portal endpoint
    res_web = client.post("/api/intake/web-portal", json={"victim_id": vid, "message": "Portal message"})
    assert res_web.status_code == 200
