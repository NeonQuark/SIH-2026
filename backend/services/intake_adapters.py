from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.models import VictimProfile, InteractionLog
from backend.services.nlp_pipeline import nlp_pipeline
from backend.services.distress_engine import distress_engine
from backend.services.predictive_risk_service import predict_risk_for_victim
from backend.services.alerting_service import alerting_service
from backend.services.privacy_service import privacy_service

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class MultiChannelIntakeService:
    """Unified Multi-Channel Intake Service (Chatbot, IVRS, SMS, Mobile App, Web Portal)

    Normalizes incoming interactions into the common InteractionLog schema,
    preserves channel-specific metadata without schema breakage, runs NLP/voice stress pipeline,
    and cascades execution through Distress & Alerting engines.
    """

    def _process_common_intake(
        self,
        victim_id: str,
        channel: str,
        text: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Core intake processing logic shared across all 5 channels."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            # 1. Verify Channel Consent
            consents = privacy_service.get_channel_consents(victim_id, db=db)
            channel_c = next((c for c in consents if c["channel"] == channel.lower()), None)
            if channel_c and not channel_c["consent_granted"]:
                return {
                    "status": "suppressed",
                    "reason": f"Victim {victim_id} has opted out of '{channel}' channel interactions",
                    "victim_id": victim_id,
                    "channel": channel
                }

            # Ensure victim exists
            victim = db.query(VictimProfile).filter_by(victim_id=victim_id).first()
            if not victim:
                victim = VictimProfile(victim_id=victim_id)
                db.add(victim)
                db.commit()

            # 2. NLP & Voice Stress Pipeline Analysis
            if audio_bytes and len(audio_bytes) > 0:
                nlp_res = nlp_pipeline.analyze_audio(audio_bytes=audio_bytes, transcript_text=text)
            else:
                nlp_res = nlp_pipeline.analyze_text(text=text or "", language=language)

            # 3. Schema Normalization & Metadata Preservation
            raw_emotions = {
                "emotion_labels": nlp_res.get("emotion_labels", {}),
                "confidence": nlp_res.get("confidence", 1.0),
                "_channel_metadata": metadata or {}
            }
            if nlp_res.get("voice_stress_score") is not None:
                raw_emotions["voice_stress_score"] = nlp_res.get("voice_stress_score")
                raw_emotions["acoustic_features"] = nlp_res.get("acoustic_features", {})

            interaction = InteractionLog(
                victim_id=victim_id,
                channel=channel.lower(),
                timestamp=utcnow(),
                transcript_text=nlp_res.get("text", text or ""),
                raw_sentiment_score=nlp_res.get("sentiment_score", 0.0),
                raw_emotion_scores=raw_emotions
            )
            db.add(interaction)
            db.commit()

            # 4. Dynamic Distress Score Calculation
            distress_res = distress_engine.calculate_distress_score(
                victim_id=victim_id,
                nlp_output=nlp_res,
                db=db
            )

            # 5. Predictive Risk Forecast & Auto-Alert Escalation
            risk_res = predict_risk_for_victim(victim_id=victim_id, db=db)
            alert_res = None

            if risk_res.get("risk_tier") in ["high", "critical"]:
                alert_res = alerting_service.dispatch_alert(
                    victim_id=victim_id,
                    risk_prediction=risk_res,
                    db=db
                )

            return {
                "status": "processed",
                "interaction_id": interaction.id,
                "victim_id": victim_id,
                "channel": channel,
                "nlp_analysis": nlp_res,
                "distress_score": distress_res.get("composite_score"),
                "risk_tier": risk_res.get("risk_tier"),
                "alert_dispatch": alert_res,
                "channel_metadata_preserved": metadata or {}
            }
        finally:
            if close_session:
                db.close()

    # --- Channel Specific Intake Adapters ---

    def process_chatbot_intake(
        self,
        victim_id: str,
        message: str,
        bot_session_id: Optional[str] = None,
        user_intent: Optional[str] = None,
        session_duration_sec: Optional[int] = None,
        language: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Chatbot Channel Intake Adapter."""
        metadata = {
            "bot_session_id": bot_session_id or "session_default",
            "user_intent": user_intent or "general_distress",
            "session_duration_sec": session_duration_sec or 0
        }
        return self._process_common_intake(
            victim_id=victim_id,
            channel="chatbot",
            text=message,
            language=language,
            metadata=metadata,
            db=db
        )

    def process_ivrs_intake(
        self,
        victim_id: str,
        audio_bytes: Optional[bytes] = None,
        transcribed_text: Optional[str] = None,
        call_sid: Optional[str] = None,
        call_duration_sec: Optional[int] = None,
        caller_state: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """IVRS (Voice Call) Channel Intake Adapter."""
        metadata = {
            "call_sid": call_sid or "CA_default",
            "call_duration_sec": call_duration_sec or 0,
            "caller_state": caller_state or "Unknown"
        }
        return self._process_common_intake(
            victim_id=victim_id,
            channel="ivrs",
            text=transcribed_text,
            audio_bytes=audio_bytes,
            metadata=metadata,
            db=db
        )

    def process_sms_intake(
        self,
        victim_id: str,
        sms_text: str,
        sms_sid: Optional[str] = None,
        delivery_status: Optional[str] = "delivered",
        sender_shortcode: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """SMS Channel Intake Adapter."""
        metadata = {
            "sms_sid": sms_sid or "SM_default",
            "sms_delivery_status": delivery_status or "delivered",
            "sender_shortcode": sender_shortcode or "14416"
        }
        return self._process_common_intake(
            victim_id=victim_id,
            channel="sms",
            text=sms_text,
            metadata=metadata,
            db=db
        )

    def process_mobile_app_intake(
        self,
        victim_id: str,
        message: str,
        app_version: Optional[str] = None,
        device_os: Optional[str] = None,
        network_type: Optional[str] = None,
        coarse_location: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Mobile App Channel Intake Adapter."""
        metadata = {
            "app_version": app_version or "v1.0.0",
            "device_os": device_os or "Android",
            "network_type": network_type or "cellular",
            "coarse_location": coarse_location or "Unknown"
        }
        return self._process_common_intake(
            victim_id=victim_id,
            channel="mobile_app",
            text=message,
            metadata=metadata,
            db=db
        )

    def process_web_portal_intake(
        self,
        victim_id: str,
        message: str,
        web_session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        browser_language: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Web Portal Channel Intake Adapter."""
        metadata = {
            "web_session_id": web_session_id or "web_default",
            "user_agent": user_agent or "Mozilla/5.0",
            "browser_language": browser_language or "en-US"
        }
        return self._process_common_intake(
            victim_id=victim_id,
            channel="web_portal",
            text=message,
            metadata=metadata,
            db=db
        )

# Global singleton intake service instance
intake_service = MultiChannelIntakeService()
