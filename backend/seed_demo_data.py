import uuid
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal, engine, Base
from backend.db.models import (
    VictimProfile, InteractionLog, DistressScore, RiskAlert,
    InterventionRecommendation, AuditLog, ChannelConsent, User
)
from backend.security.auth import seed_demo_users

logger = logging.getLogger("seed_demo_data")

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

DEMO_VICTIMS = [
    # ─────────────────────────────────────────────────────────────
    # 1. KEY DEMO MOMENT: HARD-TRIGGER CRITICAL CASE (Hathras)
    # ─────────────────────────────────────────────────────────────
    {
        "victim_id": "v_hathras_critical_01",
        "case_id": "SCST-UP-2026-0814",
        "name": "Sunita Kumari",
        "phone": "+91 9876543210",
        "address": "Village Chandpa, Tehsil Sadar, Hathras, UP",
        "contact": "+91 9876543210",
        "district": "Hathras",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (28, 24.5, "Initial intake check-in after FIR registration"),
            (20, 48.0, "Reported verbal harassment outside home"),
            (10, 72.0, "Followed by unknown bike riders near market"),
            (1, 89.5, "Emergency: Hard-trigger threat with weapon outside residence")
        ],
        "latest_channel": "chatbot",
        "transcript": "someone is following me near my house and showed a knife",
        "sentiment": -1.0,
        "emotions": {"fear": 0.88, "anxiety": 0.35, "anger": 0.12, "sadness": 0.25, "neutral": 0.02},
        "hard_trigger_detected": True,
        "matched_terms": ["following me", "knife"],
        "alert": {
            "status": "Open",
            "trigger": "[hard_trigger_override] Critical Threshold 89.5 Breach (Hard-trigger: weapon threat & stalking)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Hathras",
            "sla_status": "IN_SLA",
            "sla_due_hours": 0.5
        },
        "interventions": [
            ("witness_protection", "In_Progress", "24/7 Police protection posted at victim residence in Chandpa village"),
            ("legal_aid", "Approved", "Senior District Advocate appointed under SC/ST Legal Aid Scheme"),
            ("financial_aid", "Completed", "First installment of statutory compensation ₹1,25,000 disbursed")
        ]
    },

    # ─────────────────────────────────────────────────────────────
    # 2. CRITICAL CASE (Lucknow)
    # ─────────────────────────────────────────────────────────────
    {
        "victim_id": "v_lucknow_critical_02",
        "case_id": "SCST-UP-2026-0312",
        "name": "Ramesh Rawat",
        "phone": "+91 9812345678",
        "address": "Mohanlalganj Basti, Lucknow, UP",
        "contact": "+91 9812345678",
        "district": "Lucknow",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (25, 31.0, "Intake call"),
            (14, 58.5, "Caste slurs and retaliation threats by accused party"),
            (2, 83.0, "Physical assault & window damage")
        ],
        "latest_channel": "ivrs",
        "transcript": "Audio call recorded: Accused party broke window glasses with iron rods outside my home. High acoustic voice stress (78%).",
        "sentiment": -0.92,
        "emotions": {"fear": 0.82, "anxiety": 0.40, "anger": 0.30, "sadness": 0.10, "neutral": 0.05},
        "hard_trigger_detected": True,
        "matched_terms": ["iron rods", "broke"],
        "alert": {
            "status": "ACKNOWLEDGED",
            "trigger": "Critical Threshold 83.0 Breach (Physical Violence & Property Damage)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Lucknow",
            "sla_status": "ACKNOWLEDGED",
            "acknowledged_by": "District_Officer_Lucknow"
        },
        "interventions": [
            ("police_protection", "Approved", "Police patrol unit deployed to Mohanlalganj Basti"),
            ("relocation", "Accepted", "Temporary safe house placement arranged in Lucknow city")
        ]
    },

    # ─────────────────────────────────────────────────────────────
    # 3. CRITICAL CASE (Meerut)
    # ─────────────────────────────────────────────────────────────
    {
        "victim_id": "v_meerut_critical_03",
        "case_id": "SCST-UP-2026-0901",
        "name": "Pooja Jatav",
        "phone": "+91 9765432109",
        "address": "Partapur Basti, Meerut, UP",
        "contact": "+91 9765432109",
        "district": "Meerut",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (18, 40.0, "Witness intimidation FIR recorded"),
            (8, 68.0, "Intimidation at workplace"),
            (1, 87.0, "Armed threat to witness family")
        ],
        "latest_channel": "sms",
        "transcript": "They pointed a gun at my brother and threatened to kill us if we testify tomorrow in court.",
        "sentiment": -0.95,
        "emotions": {"fear": 0.85, "anxiety": 0.50, "anger": 0.20, "sadness": 0.10, "neutral": 0.01},
        "hard_trigger_detected": True,
        "matched_terms": ["gun", "threatened to kill"],
        "alert": {
            "status": "Open",
            "trigger": "[hard_trigger_override] Critical Threshold 87.0 Breach (Gun threat to witness)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Meerut",
            "sla_status": "IN_SLA",
            "sla_due_hours": 0.5
        },
        "interventions": [
            ("witness_protection", "Approved", "Emergency witness protection escort to Special Court Meerut"),
            ("legal_aid", "Approved", "Senior Special Public Prosecutor assigned")
        ]
    },

    # ─────────────────────────────────────────────────────────────
    # 4. HIGH RISK CASES (Hathras, Lucknow, Meerut)
    # ─────────────────────────────────────────────────────────────
    {
        "victim_id": "v_hathras_high_04",
        "case_id": "SCST-UP-2026-0921",
        "name": "Kavita Valmiki",
        "phone": "+91 9654321098",
        "address": "Khandauli, Hathras, UP",
        "contact": "+91 9654321098",
        "district": "Hathras",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (18, 42.0, "Baseline check-in"),
            (5, 68.5, "Witness coercion attempt")
        ],
        "latest_channel": "sms",
        "transcript": "They are pressuring me to compromise outside court. Saying they will make life difficult.",
        "sentiment": -0.75,
        "emotions": {"fear": 0.68, "anxiety": 0.52, "anger": 0.15, "sadness": 0.20, "neutral": 0.05},
        "alert": {
            "status": "ACKNOWLEDGED",
            "trigger": "High Risk Threshold 68.5 Breach (Witness Intimidation)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Hathras",
            "sla_status": "ACKNOWLEDGED",
            "acknowledged_by": "District_Officer_Hathras"
        },
        "interventions": [
            ("witness_protection", "Pending", "Witness protection assessment pending DSP report"),
            ("counselling", "Accepted", "Tele-counselling session booked with trauma counselor")
        ]
    },
    {
        "victim_id": "v_lucknow_high_05",
        "case_id": "SCST-UP-2026-0411",
        "name": "Babu Lal Verma",
        "phone": "+91 9543210987",
        "address": "Bakshi Ka Talab, Lucknow, UP",
        "contact": "+91 9543210987",
        "district": "Lucknow",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (21, 38.0, "Land dispute FIR filed"),
            (7, 65.0, "Forced eviction attempt")
        ],
        "latest_channel": "web_portal",
        "transcript": "Land grabbers showed forged documents and threatened forced demolition of agricultural hut.",
        "sentiment": -0.70,
        "emotions": {"fear": 0.62, "anxiety": 0.58, "anger": 0.35, "sadness": 0.10, "neutral": 0.08},
        "alert": {
            "status": "Open",
            "trigger": "High Risk Threshold 65.0 Breach (Land Eviction Threat)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Lucknow",
            "sla_status": "IN_SLA",
            "sla_due_hours": 1.5
        },
        "interventions": [
            ("legal_aid", "Approved", "Revenue court stay order application filed"),
            ("financial_aid", "Pending", "Relief grant application pending verification")
        ]
    },
    {
        "victim_id": "v_meerut_high_06",
        "case_id": "SCST-UP-2026-0211",
        "name": "Manju Paswan",
        "phone": "+91 9432109876",
        "address": "Mawana, Meerut, UP",
        "contact": "+91 9432109876",
        "district": "Meerut",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (15, 45.0, "Verbal caste abuse at workplace"),
            (4, 64.0, "Constructive dismissal & harassment")
        ],
        "latest_channel": "ivrs",
        "transcript": "Fired from job after refusing to withdraw caste slurs FIR against supervisor.",
        "sentiment": -0.68,
        "emotions": {"fear": 0.58, "anxiety": 0.65, "anger": 0.25, "sadness": 0.38, "neutral": 0.05},
        "alert": {
            "status": "In_Review",
            "trigger": "High Risk Threshold 64.0 Breach (Workplace Retaliation)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Meerut",
            "sla_status": "IN_SLA",
            "sla_due_hours": 2.0
        },
        "interventions": [
            ("financial_aid", "Approved", "Emergency subsistence grant approved ₹25,000"),
            ("counselling", "Completed", "Initial psychosocial evaluation completed")
        ]
    },

    # ─────────────────────────────────────────────────────────────
    # 5. MEDIUM RISK CASES
    # ─────────────────────────────────────────────────────────────
    {
        "victim_id": "v_hathras_med_07",
        "case_id": "SCST-UP-2026-0544",
        "name": "Anil Rawat",
        "phone": "+91 9321098765",
        "address": "Sadabad, Hathras, UP",
        "contact": "+91 9321098765",
        "district": "Hathras",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [(22, 35.0, "Routine check-in"), (11, 48.0, "Minor argument with village mukhiya")],
        "latest_channel": "chatbot",
        "transcript": "Sub-inspector called for statement recording. Feeling anxious about going to police station alone.",
        "sentiment": -0.45,
        "emotions": {"fear": 0.42, "anxiety": 0.50, "anger": 0.05, "sadness": 0.10, "neutral": 0.25},
        "interventions": [("counselling", "Accepted", "Para-legal volunteer assigned to accompany for statement recording")]
    },
    {
        "victim_id": "v_lucknow_med_08",
        "case_id": "SCST-UP-2026-0188",
        "name": "Meena Bheel",
        "phone": "+91 9210987654",
        "address": "Chinhat, Lucknow, UP",
        "contact": "+91 9210987654",
        "district": "Lucknow",
        "state": "Uttar Pradesh",
        "caste_category": "ST",
        "gender": "Female",
        "scores": [(16, 40.0, "Distress check-in"), (6, 52.0, "School entry discrimination complaint")],
        "latest_channel": "sms",
        "transcript": "School authorities delayed admission of child despite government order under SC/ST quota.",
        "sentiment": -0.50,
        "emotions": {"fear": 0.35, "anxiety": 0.55, "anger": 0.30, "sadness": 0.20, "neutral": 0.15},
        "interventions": [("legal_aid", "Approved", "District Education Officer notice drafted")]
    },
    {
        "victim_id": "v_meerut_med_09",
        "case_id": "SCST-UP-2026-0390",
        "name": "Rajesh Ram",
        "phone": "+91 9109876543",
        "address": "Sardhana, Meerut, UP",
        "contact": "+91 9109876543",
        "district": "Meerut",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [(19, 32.0, "Initial complaint log"), (8, 46.5, "Public water well access dispute")],
        "latest_channel": "mobile_app",
        "transcript": "Denial of access to community tube well by upper caste residents in Sardhana block.",
        "sentiment": -0.52,
        "emotions": {"fear": 0.38, "anxiety": 0.48, "anger": 0.40, "sadness": 0.15, "neutral": 0.10},
        "interventions": [("legal_aid", "Accepted", "BDO enquiry initiated regarding community water access")]
    },
    {
        "victim_id": "v_hathras_med_10",
        "case_id": "SCST-UP-2026-1102",
        "name": "Rekha Valmiki",
        "phone": "+91 9098765432",
        "address": "Sasni Gate, Hathras, UP",
        "contact": "+91 9098765432",
        "district": "Hathras",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [(14, 38.5, "Baseline assessment"), (4, 54.0, "Verbal threat in local shop")],
        "latest_channel": "chatbot",
        "transcript": "Shopkeeper refused service and used derogatory caste epithet.",
        "sentiment": -0.58,
        "emotions": {"fear": 0.45, "anxiety": 0.52, "anger": 0.38, "sadness": 0.22, "neutral": 0.08},
        "interventions": [("counselling", "Completed", "Psychosocial counselling provided by Hathras District Counselor")]
    },

    # ─────────────────────────────────────────────────────────────
    # 6. STABLE / IMPROVING LOW RISK CASES
    # ─────────────────────────────────────────────────────────────
    {
        "victim_id": "v_hathras_low_11",
        "case_id": "SCST-UP-2026-0112",
        "name": "Vijay Gautam",
        "phone": "+91 8987654321",
        "address": "Mursan, Hathras, UP",
        "contact": "+91 8987654321",
        "district": "Hathras",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [(30, 22.0, "Routine check-in"), (15, 18.0, "Compensation disbursed"), (2, 14.0, "Case proceeding smoothly")],
        "latest_channel": "web_portal",
        "transcript": "Received second statutory relief tranche of ₹2,00,000. Hearing scheduled for next month.",
        "sentiment": 0.25,
        "emotions": {"fear": 0.10, "anxiety": 0.15, "anger": 0.05, "sadness": 0.05, "neutral": 0.65},
        "interventions": [("financial_aid", "Completed", "Full statutory compensation of ₹4,00,000 successfully disbursed")]
    },
    {
        "victim_id": "v_lucknow_low_12",
        "case_id": "SCST-UP-2026-0331",
        "name": "Lata Devi",
        "phone": "+91 8876543210",
        "address": "Gomti Nagar, Lucknow, UP",
        "contact": "+91 8876543210",
        "district": "Lucknow",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [(26, 28.0, "Case review"), (12, 20.0, "Charge sheet filed"), (1, 16.5, "Police protection active")],
        "latest_channel": "chatbot",
        "transcript": "Thank you for the update on court hearing schedule. Police constable visited today for routine check.",
        "sentiment": 0.40,
        "emotions": {"fear": 0.08, "anxiety": 0.12, "anger": 0.02, "sadness": 0.05, "neutral": 0.73},
        "interventions": [("police_protection", "Completed", "Routine police security patrols established")]
    },
    {
        "victim_id": "v_meerut_low_13",
        "case_id": "SCST-UP-2026-0774",
        "name": "Babu Lal Bairwa",
        "phone": "+91 8765432109",
        "address": "Modinagar, Meerut, UP",
        "contact": "+91 8765432109",
        "district": "Meerut",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [(24, 25.0, "Initial registration"), (8, 19.0, "Counselling complete")],
        "latest_channel": "sms",
        "transcript": "Attended counselling session today. Feeling much better and supported.",
        "sentiment": 0.55,
        "emotions": {"fear": 0.05, "anxiety": 0.10, "anger": 0.01, "sadness": 0.04, "neutral": 0.80},
        "interventions": [("counselling", "Completed", "Completed 4 wellness counselling sessions")]
    },
    {
        "victim_id": "v_hathras_low_14",
        "case_id": "SCST-UP-2026-0612",
        "name": "Aarti Kumari",
        "phone": "+91 8654321098",
        "address": "Sikandra Rao, Hathras, UP",
        "contact": "+91 8654321098",
        "district": "Hathras",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [(27, 21.0, "Periodic check-in"), (5, 17.5, "Court testimony recorded under Sec 164 CrPC")],
        "latest_channel": "mobile_app",
        "transcript": "Statement recorded before Judicial Magistrate. Legal aid lawyer was present throughout.",
        "sentiment": 0.35,
        "emotions": {"fear": 0.12, "anxiety": 0.18, "anger": 0.05, "sadness": 0.05, "neutral": 0.60},
        "interventions": [("legal_aid", "Completed", "Sec 164 statement completed successfully")]
    },
    {
        "victim_id": "v_lucknow_low_15",
        "case_id": "SCST-UP-2026-0499",
        "name": "Dharmendra Koli",
        "phone": "+91 8543210987",
        "address": "Kakori, Lucknow, UP",
        "contact": "+91 8543210987",
        "district": "Lucknow",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [(20, 26.0, "Baseline check"), (3, 15.0, "Resolution & settlement under court supervision")],
        "latest_channel": "web_portal",
        "transcript": "Accused submitted unconditional written apology in special court. Case moving towards final disposal.",
        "sentiment": 0.60,
        "emotions": {"fear": 0.04, "anxiety": 0.08, "anger": 0.02, "sadness": 0.02, "neutral": 0.84},
        "interventions": [("legal_aid", "Completed", "Court compromise terms registered")]
    }
]

def seed_demo_data(db: Session = None):
    """Populate database with 15 realistic SC/ST Act victim cases across target districts."""
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        # 1. Ensure demo accounts exist
        seed_demo_users(db)

        now = utcnow()
        created_victims = 0

        for vdata in DEMO_VICTIMS:
            vid = vdata["victim_id"]

            # Upsert Victim Profile
            victim = db.query(VictimProfile).filter_by(victim_id=vid).first()
            if not victim:
                victim = VictimProfile(
                    victim_id=vid,
                    case_id=vdata["case_id"],
                    name=vdata["name"],
                    phone=vdata["phone"],
                    address=vdata["address"],
                    contact=vdata["contact"],
                    district=vdata["district"],
                    state=vdata["state"],
                    caste_category=vdata["caste_category"],
                    gender=vdata["gender"],
                    created_at=now - timedelta(days=30)
                )
                db.add(victim)
                db.flush()
                created_victims += 1
            else:
                victim.case_id = vdata["case_id"]
                victim.district = vdata["district"]
                victim.state = vdata["state"]

            # Add Channel Consents
            for ch in ["chatbot", "ivrs", "sms", "mobile_app", "web_portal"]:
                consent = db.query(ChannelConsent).filter_by(victim_id=vid, channel=ch).first()
                if not consent:
                    db.add(ChannelConsent(
                        victim_id=vid,
                        channel=ch,
                        consent_granted=True,
                        consent_timestamp=now - timedelta(days=30),
                        consent_purpose="SC/ST Victim Protection & Emergency Dispatch"
                    ))

            # Add Longitudinal Distress Scores
            ds_records = []
            for days_ago, score_val, note in vdata["scores"]:
                ts = now - timedelta(days=days_ago)
                ds = db.query(DistressScore).filter_by(victim_id=vid, score=score_val).first()
                if not ds:
                    ds = DistressScore(
                        victim_id=vid,
                        score=score_val,
                        timestamp=ts,
                        contributing_factors={
                            "fear_emotion": min(100.0, score_val * 1.1),
                            "anxiety_emotion": min(100.0, score_val * 0.9),
                            "negative_sentiment": min(100.0, score_val * 1.0),
                            "note": note
                        },
                        model_version="v1.0.0-rf160",
                        confidence=0.95
                    )
                    db.add(ds)
                    db.flush()
                ds_records.append(ds)

            # Add Latest Interaction Log
            db.add(InteractionLog(
                victim_id=vid,
                channel=vdata["latest_channel"],
                timestamp=now - timedelta(hours=2),
                transcript_text=vdata["transcript"],
                raw_sentiment_score=vdata["sentiment"],
                raw_emotion_scores=vdata["emotions"]
            ))

            # Add Risk Alert (if applicable)
            if "alert" in vdata and vdata["alert"]:
                adata = vdata["alert"]
                last_ds_id = ds_records[-1].id if ds_records else None
                created_ts = now - timedelta(hours=12)
                sla_due = created_ts + timedelta(hours=adata.get("sla_due_hours", 1.0))

                existing_alert = db.query(RiskAlert).filter_by(victim_id=vid, trigger_reason=adata["trigger"]).first()
                if not existing_alert:
                    alert = RiskAlert(
                        victim_id=vid,
                        distress_score_id=last_ds_id,
                        trigger_reason=adata["trigger"],
                        threshold_crossed=adata["trigger"].split("(")[0].strip(),
                        assigned_officer_or_counsellor=adata["assigned"],
                        status=adata["status"],
                        jurisdiction_level=adata["jurisdiction_level"],
                        district=vdata["district"],
                        state=vdata["state"],
                        recipient_role=adata["assigned"],
                        recipient_contact=f"{adata['assigned'].lower()}@saathicare.gov.in",
                        delivery_channels=["dashboard", "sms", "email"],
                        cooldown_until=now + timedelta(minutes=60),
                        created_at=created_ts,
                        sla_due_at=sla_due,
                        acknowledged_at=now - timedelta(hours=6) if adata["status"] in ["ACKNOWLEDGED", "In_Review"] else None,
                        acknowledged_by=adata.get("acknowledged_by"),
                        sla_status=adata["sla_status"]
                    )
                    db.add(alert)

            # Add Interventions
            for itype, istatus, idetails in vdata.get("interventions", []):
                existing_rec = db.query(InterventionRecommendation).filter_by(victim_id=vid, intervention_type=itype).first()
                if not existing_rec:
                    db.add(InterventionRecommendation(
                        victim_id=vid,
                        linked_case_id=vdata["case_id"],
                        intervention_type=itype,
                        status=istatus,
                        recommendation_details={
                            "notes": idetails,
                            "district": vdata["district"],
                            "caste_category": vdata["caste_category"]
                        },
                        created_at=now - timedelta(days=5)
                    ))

            # Add Audit Logs
            db.add(AuditLog(
                user_id="counselor_ananya",
                user_role="counsellor",
                action="READ_CASE_TIMELINE",
                resource_type="victim_profile",
                resource_id=vid,
                ip_address="127.0.0.1",
                timestamp=now - timedelta(hours=1),
                details={"district": vdata["district"], "state": vdata["state"]}
            ))

        db.commit()
        logger.info(f"Successfully seeded/updated demo victim profiles.")
        return {"status": "seeded", "victims_created": created_victims}

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding demo data: {str(e)}")
        raise e
    finally:
        if close_session:
            db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_demo_data()
