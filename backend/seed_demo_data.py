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
    # --- CRITICAL CASES ---
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
            (1, 89.5, "Emergency: Threat with weapon outside residence")
        ],
        "latest_channel": "chatbot",
        "transcript": "Emergency, I am being followed near my house by the accused relatives. They showed a knife and threatened to kill me if I don't withdraw the case.",
        "sentiment": -1.0,
        "emotions": {"fear": 0.88, "anxiety": 0.35, "anger": 0.12, "sadness": 0.25, "neutral": 0.02},
        "alert": {
            "status": "Open",
            "trigger": "Critical Threshold 89.5 Breach (Hard-trigger override: Knife threat & stalking)",
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
    {
        "victim_id": "v_jaipur_critical_02",
        "case_id": "SCST-RJ-2026-0419",
        "name": "Ramesh Meghwal",
        "phone": "+91 9812345678",
        "address": "Phulera Basti, Jaipur Rural, Rajasthan",
        "contact": "+91 9812345678",
        "district": "Jaipur",
        "state": "Rajasthan",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (25, 31.0, "Intake call"),
            (14, 58.5, "Land encroachment attempt by local perpetrators"),
            (2, 83.0, "Physical assault & property damage")
        ],
        "latest_channel": "ivrs",
        "transcript": "Audio call recorded: Accused party broke window glasses with iron rods. High acoustic voice stress detected (78%).",
        "sentiment": -0.92,
        "emotions": {"fear": 0.82, "anxiety": 0.40, "anger": 0.30, "sadness": 0.10, "neutral": 0.05},
        "alert": {
            "status": "ACKNOWLEDGED",
            "trigger": "Critical Threshold 83.0 Breach (Physical Violence & Property Damage)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Jaipur",
            "sla_status": "ACKNOWLEDGED",
            "acknowledged_by": "District_Officer_Jaipur"
        },
        "interventions": [
            ("police_protection", "Approved", "Police patrol unit deployed to Phulera Basti"),
            ("relocation", "Accepted", "Temporary safe house placement arranged in Jaipur city")
        ]
    },
    {
        "victim_id": "v_patna_critical_03",
        "case_id": "SCST-BR-2026-0102",
        "name": "Pooja Paswan",
        "phone": "+91 9765432109",
        "address": "Phulwari Sharif, Patna, Bihar",
        "contact": "+91 9765432109",
        "district": "Patna",
        "state": "Bihar",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (12, 76.0, "Sexual harassment & boycott threat"),
            (3, 87.0, "Social boycott imposed on victim family")
        ],
        "latest_channel": "mobile_app",
        "transcript": "Local panchayat leaders have called for economic boycott against my family for filing SC/ST FIR.",
        "sentiment": -0.88,
        "emotions": {"fear": 0.79, "anxiety": 0.60, "sadness": 0.45, "neutral": 0.01},
        "alert": {
            "status": "Escalated",
            "trigger": "State Escalation: Critical Score 87.0 + Social Boycott Threat",
            "jurisdiction_level": "state",
            "assigned": "State_SC_ST_Commission_Bihar",
            "sla_status": "IN_SLA",
            "sla_due_hours": 1.0
        },
        "interventions": [
            ("rehabilitation", "Approved", "State Commission directive issued to District Magistrate Patna for immediate intervention"),
            ("legal_aid", "Approved", "Free legal counsel assigned under Bihar State Legal Services Authority")
        ]
    },

    # --- HIGH RISK CASES ---
    {
        "victim_id": "v_agra_high_04",
        "case_id": "SCST-UP-2026-0921",
        "name": "Kavita Jatav",
        "phone": "+91 9654321098",
        "address": "Khandauli, Agra, Uttar Pradesh",
        "contact": "+91 9654321098",
        "district": "Agra",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (18, 42.0, "Baseline check-in"),
            (5, 68.5, "Witness intimidation by accused associates")
        ],
        "latest_channel": "sms",
        "transcript": "They are pressuring me to compromise outside court. Saying they will make life difficult.",
        "sentiment": -0.75,
        "emotions": {"fear": 0.68, "anxiety": 0.52, "anger": 0.15, "sadness": 0.20, "neutral": 0.05},
        "alert": {
            "status": "Open",
            "trigger": "High Risk Threshold 68.5 Breach (Witness Intimidation)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Agra",
            "sla_status": "IN_SLA",
            "sla_due_hours": 2.0
        },
        "interventions": [
            ("witness_protection", "Pending", "Witness protection assessment pending DSP report"),
            ("counselling", "Accepted", "Tele-counselling session booked with certified trauma counselor")
        ]
    },
    {
        "victim_id": "v_udaipur_high_05",
        "case_id": "SCST-RJ-2026-0305",
        "name": "Kalu Lal Mina",
        "phone": "+91 9543210987",
        "address": "Salumber, Udaipur, Rajasthan",
        "contact": "+91 9543210987",
        "district": "Udaipur",
        "state": "Rajasthan",
        "caste_category": "ST",
        "gender": "Male",
        "scores": [
            (21, 38.0, "Land dispute FIR filed"),
            (7, 65.0, "Forced eviction attempt from tribal land parcel")
        ],
        "latest_channel": "web_portal",
        "transcript": "Land grabbers showed forged documents and threatened forced demolition of agricultural hut.",
        "sentiment": -0.70,
        "emotions": {"fear": 0.62, "anxiety": 0.58, "anger": 0.35, "sadness": 0.10, "neutral": 0.08},
        "alert": {
            "status": "ACKNOWLEDGED",
            "trigger": "High Risk Threshold 65.0 Breach (Tribal Land Dispossession)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Udaipur",
            "sla_status": "ACKNOWLEDGED",
            "acknowledged_by": "District_Officer_Udaipur"
        },
        "interventions": [
            ("legal_aid", "Approved", "Revenue court stay order application filed"),
            ("financial_aid", "Pending", "Relief grant application under Revenue Board pending verification")
        ]
    },
    {
        "victim_id": "v_gaya_high_06",
        "case_id": "SCST-BR-2026-0211",
        "name": "Manju Manjhi",
        "phone": "+91 9432109876",
        "address": "Bodhgaya, Gaya, Bihar",
        "contact": "+91 9432109876",
        "district": "Gaya",
        "state": "Bihar",
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
            "status": "Open",
            "trigger": "High Risk Threshold 64.0 Breach (Workplace Retaliation)",
            "jurisdiction_level": "district",
            "assigned": "District_Officer_Gaya",
            "sla_status": "IN_SLA",
            "sla_due_hours": 1.5
        },
        "interventions": [
            ("financial_aid", "Approved", "Emergency subsistence grant approved ₹25,000"),
            ("counselling", "Completed", "Initial psychosocial evaluation completed")
        ]
    },

    # --- MEDIUM RISK CASES ---
    {
        "victim_id": "v_lucknow_med_07",
        "case_id": "SCST-UP-2026-0544",
        "name": "Anil Rawat",
        "phone": "+91 9321098765",
        "address": "Mohanlalganj, Lucknow, UP",
        "contact": "+91 9321098765",
        "district": "Lucknow",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (22, 35.0, "Routine check-in"),
            (11, 48.0, "Minor argument with village mukhiya")
        ],
        "latest_channel": "chatbot",
        "transcript": "Sub-inspector called for statement recording. Feeling anxious about going to police station alone.",
        "sentiment": -0.45,
        "emotions": {"fear": 0.42, "anxiety": 0.50, "anger": 0.05, "sadness": 0.10, "neutral": 0.25},
        "interventions": [
            ("counselling", "Accepted", "Para-legal volunteer assigned to accompany for statement recording")
        ]
    },
    {
        "victim_id": "v_kota_med_08",
        "case_id": "SCST-RJ-2026-0188",
        "name": "Meena Bheel",
        "phone": "+91 9210987654",
        "address": "Sangod, Kota, Rajasthan",
        "contact": "+91 9210987654",
        "district": "Kota",
        "state": "Rajasthan",
        "caste_category": "ST",
        "gender": "Female",
        "scores": [
            (16, 40.0, "Distress check-in"),
            (6, 52.0, "School entry discrimination complaint")
        ],
        "latest_channel": "sms",
        "transcript": "School authorities delayed admission of child despite government order under SC/ST quota.",
        "sentiment": -0.50,
        "emotions": {"fear": 0.35, "anxiety": 0.55, "anger": 0.30, "sadness": 0.20, "neutral": 0.15},
        "interventions": [
            ("legal_aid", "Approved", "District Education Officer notice drafted")
        ]
    },
    {
        "victim_id": "v_muzaffarpur_med_09",
        "case_id": "SCST-BR-2026-0390",
        "name": "Rajesh Ram",
        "phone": "+91 9109876543",
        "address": "Kanti, Muzaffarpur, Bihar",
        "contact": "+91 9109876543",
        "district": "Muzaffarpur",
        "state": "Bihar",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (19, 32.0, "Initial complaint log"),
            (8, 46.5, "Public water well access dispute")
        ],
        "latest_channel": "mobile_app",
        "transcript": "Denial of access to community tube well by upper caste residents in Kanti block.",
        "sentiment": -0.52,
        "emotions": {"fear": 0.38, "anxiety": 0.48, "anger": 0.40, "sadness": 0.15, "neutral": 0.10},
        "interventions": [
            ("legal_aid", "Accepted", "BDO enquiry initiated regarding community water access")
        ]
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
        "scores": [
            (14, 38.5, "Baseline assessment"),
            (4, 54.0, "Verbal threat in local shop")
        ],
        "latest_channel": "chatbot",
        "transcript": "Shopkeeper refused service and used derogatory caste epithet.",
        "sentiment": -0.58,
        "emotions": {"fear": 0.45, "anxiety": 0.52, "anger": 0.38, "sadness": 0.22, "neutral": 0.08},
        "interventions": [
            ("counselling", "Completed", "Psychosocial counselling provided by Hathras District Counselor")
        ]
    },

    # --- LOW RISK / STABLE CASES ---
    {
        "victim_id": "v_varanasi_low_11",
        "case_id": "SCST-UP-2026-0112",
        "name": "Vijay Gautam",
        "phone": "+91 8987654321",
        "address": "Pindra, Varanasi, UP",
        "contact": "+91 8987654321",
        "district": "Varanasi",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (30, 22.0, "Routine check-in"),
            (15, 18.0, "Compensation disbursed"),
            (2, 14.0, "Case proceeding smoothly in special court")
        ],
        "latest_channel": "web_portal",
        "transcript": "Received second statutory relief tranche of ₹2,00,000. Hearing scheduled for next month.",
        "sentiment": 0.25,
        "emotions": {"fear": 0.10, "anxiety": 0.15, "anger": 0.05, "sadness": 0.05, "neutral": 0.65},
        "interventions": [
            ("financial_aid", "Completed", "Full statutory compensation of ₹4,00,000 successfully disbursed")
        ]
    },
    {
        "victim_id": "v_hathras_low_12",
        "case_id": "SCST-UP-2026-0331",
        "name": "Lata Devi",
        "phone": "+91 8876543210",
        "address": "Mursan, Hathras, UP",
        "contact": "+91 8876543210",
        "district": "Hathras",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (26, 28.0, "Case review"),
            (12, 20.0, "Charge sheet filed"),
            (1, 16.5, "Police protection active")
        ],
        "latest_channel": "chatbot",
        "transcript": "Thank you for the update on court hearing schedule. Police constable visited today for routine check.",
        "sentiment": 0.40,
        "emotions": {"fear": 0.08, "anxiety": 0.12, "anger": 0.02, "sadness": 0.05, "neutral": 0.73},
        "interventions": [
            ("police_protection", "Completed", "Routine police security patrols established")
        ]
    },
    {
        "victim_id": "v_jaipur_low_13",
        "case_id": "SCST-RJ-2026-0774",
        "name": "Babu Lal Bairwa",
        "phone": "+91 8765432109",
        "address": "Sanganer, Jaipur, Rajasthan",
        "contact": "+91 8765432109",
        "district": "Jaipur",
        "state": "Rajasthan",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (24, 25.0, "Initial registration"),
            (8, 19.0, "Counselling complete")
        ],
        "latest_channel": "sms",
        "transcript": "Attended counselling session today. Feeling much better and supported.",
        "sentiment": 0.55,
        "emotions": {"fear": 0.05, "anxiety": 0.10, "anger": 0.01, "sadness": 0.04, "neutral": 0.80},
        "interventions": [
            ("counselling", "Completed", "Completed 4 wellness counselling sessions")
        ]
    },
    {
        "victim_id": "v_patna_low_14",
        "case_id": "SCST-BR-2026-0612",
        "name": "Aarti Kumari",
        "phone": "+91 8654321098",
        "address": "Danapur, Patna, Bihar",
        "contact": "+91 8654321098",
        "district": "Patna",
        "state": "Bihar",
        "caste_category": "SC",
        "gender": "Female",
        "scores": [
            (27, 21.0, "Periodic check-in"),
            (5, 17.5, "Court testimony recorded under Sec 164 CrPC")
        ],
        "latest_channel": "mobile_app",
        "transcript": "Statement recorded before Judicial Magistrate. Legal aid lawyer was present throughout.",
        "sentiment": 0.35,
        "emotions": {"fear": 0.12, "anxiety": 0.18, "anger": 0.05, "sadness": 0.05, "neutral": 0.60},
        "interventions": [
            ("legal_aid", "Completed", "Sec 164 statement completed successfully")
        ]
    },
    {
        "victim_id": "v_agra_low_15",
        "case_id": "SCST-UP-2026-0499",
        "name": "Dharmendra Singh Koli",
        "phone": "+91 8543210987",
        "address": "Fatehabad, Agra, UP",
        "contact": "+91 8543210987",
        "district": "Agra",
        "state": "Uttar Pradesh",
        "caste_category": "SC",
        "gender": "Male",
        "scores": [
            (20, 26.0, "Baseline check"),
            (3, 15.0, "Resolution & settlement under court supervision")
        ],
        "latest_channel": "web_portal",
        "transcript": "Accused submitted unconditional written apology in special court. Case moving towards final disposal.",
        "sentiment": 0.60,
        "emotions": {"fear": 0.04, "anxiety": 0.08, "anger": 0.02, "sadness": 0.02, "neutral": 0.84},
        "interventions": [
            ("legal_aid", "Completed", "Court compromise terms registered")
        ]
    }
]

def seed_demo_data(db: Session = None):
    """Populate database with 15-20 realistic SC/ST Act victim cases across districts & states."""
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        # First ensure demo accounts exist
        seed_demo_users(db)

        # Check if core demo cases are present
        demo_sample = db.query(VictimProfile).filter_by(victim_id="v_hathras_critical_01").first()
        if demo_sample:
            logger.info("Core demo victim profiles already present. Skipping seed.")
            return {"status": "skipped", "message": "Core demo records preserved"}

        now = utcnow()
        created_victims = 0

        for vdata in DEMO_USERS_LIST if 'DEMO_USERS_LIST' in locals() else DEMO_VICTIMS:
            vid = vdata["victim_id"]
            
            # 1. Create Victim Profile
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

            # 2. Add Consent
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

            # 3. Add Longitudinal Distress Scores
            ds_records = []
            for days_ago, score_val, note in vdata["scores"]:
                ts = now - timedelta(days=days_ago)
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
                    confidence=0.92
                )
                db.add(ds)
                db.flush()
                ds_records.append(ds)

            # 4. Add Latest Interaction Log
            db.add(InteractionLog(
                victim_id=vid,
                channel=vdata["latest_channel"],
                timestamp=now - timedelta(hours=2),
                transcript_text=vdata["transcript"],
                raw_sentiment_score=vdata["sentiment"],
                raw_emotion_scores=vdata["emotions"]
            ))

            # 5. Add Risk Alert (if applicable)
            if "alert" in vdata and vdata["alert"]:
                adata = vdata["alert"]
                last_ds_id = ds_records[-1].id if ds_records else None
                created_ts = now - timedelta(hours=12)
                sla_due = created_ts + timedelta(hours=adata.get("sla_due_hours", 1.0))
                
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

            # 6. Add Interventions
            for itype, istatus, idetails in vdata.get("interventions", []):
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

            # 7. Add Audit Logs
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
        logger.info(f"Successfully seeded {created_victims} victim profiles with complete longitudinal history.")
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
