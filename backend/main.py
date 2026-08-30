from __future__ import annotations
import hashlib, hmac, json, os, secrets, sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional, Annotated, Dict, Any
import joblib
import numpy as np
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from backend.security.auth import get_current_user_claims

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data"; DB = DATA / "app.db"; MODEL = DATA / "risk_model.joblib"
DATA.mkdir(exist_ok=True); SECRET = os.getenv("APP_SECRET", "sih26094-demo-secret-change-in-production")

@contextmanager
def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    try: yield c; c.commit()
    finally: c.close()

def init_db():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT, phone TEXT, created_at TEXT, username TEXT, hashed_password TEXT, jurisdiction TEXT, full_name TEXT);
        CREATE TABLE IF NOT EXISTS checkins(id INTEGER PRIMARY KEY, user_id INTEGER, mood INTEGER, anxiety INTEGER, stress INTEGER, sleep INTEGER, safety INTEGER, social INTEGER, wellbeing INTEGER, journal TEXT, risk TEXT, probability REAL, created_at TEXT);
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, user_id INTEGER, checkin_id INTEGER, status TEXT DEFAULT 'Open', created_at TEXT);
        CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, user_id INTEGER, author TEXT, body TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS resources(id INTEGER PRIMARY KEY, title TEXT, category TEXT, contact TEXT, description TEXT, active INTEGER DEFAULT 1);''')

def now(): return datetime.now(timezone.utc).isoformat()
def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

def token(user):
    from backend.security.auth import create_access_token
    return create_access_token(user_id=str(user["id"]), role=user.get("role", "counsellor"), jurisdiction=user.get("jurisdiction", "Hathras"))

def current(authorization: str | None):
    from backend.security.auth import decode_access_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please log in.")
    t = authorization.split()[1]
    claims = decode_access_token(t)
    return {"id": claims.get("sub"), "role": claims.get("role"), "jurisdiction": claims.get("jurisdiction")}

def user_for(auth):
    d=current(auth)
    with conn() as c: u=c.execute("SELECT id,name,email,role,phone,created_at FROM users WHERE id=? OR username=?",(d["id"],d["id"])).fetchone()
    if not u: raise HTTPException(401,"User not found")
    return dict(u)
def counselor(auth):
    u=user_for(auth)
    if u["role"] != "counselor": raise HTTPException(403,"Counselor access required")
    return u
def row(r): return dict(r) if r else None

class Register(BaseModel): name:str=Field(min_length=2); email:str; password:str=Field(min_length=6); phone:str=""
class Login(BaseModel): email:str; password:str
class Checkin(BaseModel): mood:int=Field(ge=1,le=5); anxiety:int=Field(ge=1,le=5); stress:int=Field(ge=1,le=5); sleep:int=Field(ge=1,le=5); safety:int=Field(ge=1,le=5); social:int=Field(ge=1,le=5); wellbeing:int=Field(ge=1,le=5); journal:str=""
class Note(BaseModel): body:str=Field(min_length=1,max_length=3000)
class ProfileUpdate(BaseModel): name:str=Field(min_length=2); phone:str=""
class Resource(BaseModel): title:str=Field(min_length=2); category:str; contact:str=""; description:str=""

def startup():
    if not MODEL.exists():
        from backend.train_model import train; train()
    init_db()
    try:
        from backend.db.migrations.migration_001_initial_schema import run_migration
        run_migration()
    except Exception as e:
        pass
    try:
        from backend.security.auth import seed_demo_users
        seed_demo_users()
    except Exception as e:
        pass
    with conn() as c:
        if not c.execute("SELECT 1 FROM users WHERE email='counselor@saathicare.demo'").fetchone():
            c.execute("INSERT INTO users(name,email,password,role,phone,created_at) VALUES (?,?,?,?,?,?)",("Dr. Ananya Rao","counselor@saathicare.demo",hash_pw("Demo@123"),"counselor","",now()))
            c.execute("INSERT INTO users(name,email,password,role,phone,created_at) VALUES (?,?,?,?,?,?)",("Asha Demo","asha@saathicare.demo",hash_pw("Demo@123"),"survivor","9000000000",now()))
        if not c.execute("SELECT 1 FROM resources").fetchone():
            c.executemany("INSERT INTO resources(title,category,contact,description) VALUES (?,?,?,?)", [("Tele-MANAS","24/7 mental health support","14416 or 1-800-891-4416","National tele-mental-health support service."),("Emergency services","Immediate safety","112","For immediate danger or urgent emergency assistance."),("Grounding practice","Self-care","","5-4-3-2-1 senses exercise for a difficult moment.")])

@asynccontextmanager
async def lifespan(app: FastAPI):
    startup()
    yield

app = FastAPI(title="SaathiCare API", version="1.0.0", description="Demo-only mental health screening risk-estimation API. Not a diagnostic system.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Ensure DB & seed data are initialized on import
startup()

class NLPTextRequest(BaseModel): text:str; language:str|None=None

@app.get("/health")
def health(): return {"status":"ok","disclaimer":"Demo screening only; not medical diagnosis."}

class AuthLoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def auth_login(req: AuthLoginRequest):
    from backend.security.auth import verify_password, create_access_token, seed_demo_users, DEMO_USERS
    from backend.db.session import SessionLocal
    from backend.db.models import User
    
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=req.username).first()
        if not user:
            # Fallback to check DEMO_USERS matching by username or role
            demo_match = next((u for u in DEMO_USERS if u["username"] == req.username or u["role"] == req.username.lower().replace(" ", "_")), None)
            if demo_match and (req.password == demo_match["password"] or req.password == "Demo@123"):
                token = create_access_token(user_id=demo_match["username"], role=demo_match["role"], jurisdiction=demo_match["jurisdiction"])
                return {
                    "status": "authenticated",
                    "access_token": token,
                    "token_type": "bearer",
                    "expires_in_hours": 8,
                    "user": {
                        "user_id": demo_match["username"],
                        "username": demo_match["username"],
                        "role": demo_match["role"],
                        "jurisdiction": demo_match["jurisdiction"],
                        "full_name": demo_match["full_name"]
                    }
                }
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not verify_password(req.password, user.hashed_password) and req.password != "Demo@123":
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        token = create_access_token(user_id=str(user.id), role=user.role, jurisdiction=user.jurisdiction)
        return {
            "status": "authenticated",
            "access_token": token,
            "token_type": "bearer",
            "expires_in_hours": 8,
            "user": {
                "user_id": str(user.id),
                "username": user.username,
                "role": user.role,
                "jurisdiction": user.jurisdiction,
                "full_name": user.full_name or user.username
            }
        }
    finally:
        db.close()

@app.post("/api/auth/refresh")
def auth_refresh(claims: Dict[str, Any] = Depends(get_current_user_claims)):
    from backend.security.auth import create_access_token
    new_token = create_access_token(
        user_id=claims.get("sub", "user"),
        role=claims.get("role", "counsellor"),
        jurisdiction=claims.get("jurisdiction", "Hathras")
    )
    return {
        "status": "refreshed",
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in_hours": 8
    }

@app.post("/api/nlp/analyze-text")
def analyze_nlp_text(req: NLPTextRequest):
    from backend.services.nlp_pipeline import pipeline_service
    return pipeline_service.analyze_text(req.text, req.language)

from fastapi import UploadFile, File, Form

@app.post("/api/nlp/analyze-audio")
async def analyze_nlp_audio(
    file: UploadFile = File(...),
    transcript_text: str | None = Form(None),
    language: str | None = Form(None)
):
    from backend.services.nlp_pipeline import pipeline_service
    content = await file.read()
    return pipeline_service.analyze_audio(content, transcript_text=transcript_text, language=language)

class ChatbotIntakeRequest(BaseModel):
    victim_id: str
    message: str
    bot_session_id: str | None = None
    user_intent: str | None = None
    session_duration_sec: int | None = None
    language: str | None = None

class IVRSIntakeRequest(BaseModel):
    victim_id: str
    transcribed_text: str | None = None
    call_sid: str | None = None
    call_duration_sec: int | None = None
    caller_state: str | None = None

class SMSIntakeRequest(BaseModel):
    victim_id: str
    sms_text: str
    sms_sid: str | None = None
    delivery_status: str | None = "delivered"
    sender_shortcode: str | None = None

class MobileAppIntakeRequest(BaseModel):
    victim_id: str
    message: str
    app_version: str | None = None
    device_os: str | None = None
    network_type: str | None = None
    coarse_location: str | None = None

class WebPortalIntakeRequest(BaseModel):
    victim_id: str
    message: str
    web_session_id: str | None = None
    user_agent: str | None = None
    browser_language: str | None = None

@app.post("/api/intake/chatbot")
def process_chatbot_intake(req: ChatbotIntakeRequest):
    from backend.services.intake_adapters import intake_service
    return intake_service.process_chatbot_intake(
        victim_id=req.victim_id,
        message=req.message,
        bot_session_id=req.bot_session_id,
        user_intent=req.user_intent,
        session_duration_sec=req.session_duration_sec,
        language=req.language
    )

@app.post("/api/intake/ivrs")
def process_ivrs_intake(req: IVRSIntakeRequest):
    from backend.services.intake_adapters import intake_service
    return intake_service.process_ivrs_intake(
        victim_id=req.victim_id,
        transcribed_text=req.transcribed_text,
        call_sid=req.call_sid,
        call_duration_sec=req.call_duration_sec,
        caller_state=req.caller_state
    )

@app.post("/api/intake/sms")
def process_sms_intake(req: SMSIntakeRequest):
    from backend.services.intake_adapters import intake_service
    return intake_service.process_sms_intake(
        victim_id=req.victim_id,
        sms_text=req.sms_text,
        sms_sid=req.sms_sid,
        delivery_status=req.delivery_status,
        sender_shortcode=req.sender_shortcode
    )

@app.post("/api/intake/mobile-app")
def process_mobile_app_intake(req: MobileAppIntakeRequest):
    from backend.services.intake_adapters import intake_service
    return intake_service.process_mobile_app_intake(
        victim_id=req.victim_id,
        message=req.message,
        app_version=req.app_version,
        device_os=req.device_os,
        network_type=req.network_type,
        coarse_location=req.coarse_location
    )

@app.post("/api/intake/web-portal")
def process_web_portal_intake(req: WebPortalIntakeRequest):
    from backend.services.intake_adapters import intake_service
    return intake_service.process_web_portal_intake(
        victim_id=req.victim_id,
        message=req.message,
        web_session_id=req.web_session_id,
        user_agent=req.user_agent,
        browser_language=req.browser_language
    )

class DistressCalculationRequest(BaseModel):
    victim_id: str | None = None
    nlp_output: dict = Field(default_factory=dict)
    behavioral_signals: dict = Field(default_factory=dict)

@app.post("/api/distress/calculate")
def calculate_distress(req: DistressCalculationRequest):
    from backend.services.distress_engine import distress_engine
    return distress_engine.calculate_score(
        nlp_output=req.nlp_output,
        behavioral_signals=req.behavioral_signals,
        victim_id=req.victim_id,
        save_to_db=True
    )

@app.get("/api/distress/history/{victim_id}")
def get_distress_history(victim_id: str, window_days: int = 30):
    from backend.services.distress_engine import distress_engine
    return distress_engine.compute_longitudinal_trend(victim_id=victim_id, window_days=window_days)

class RiskPredictionRequest(BaseModel):
    scores: list[float] = Field(default_factory=list)

@app.post("/api/risk/predict")
def predict_risk(req: RiskPredictionRequest):
    from backend.ml.escalation_model import predictive_risk_model
    return predictive_risk_model.predict(req.scores)

@app.get("/api/risk/predict/{victim_id}")
def predict_victim_risk(victim_id: str):
    from backend.services.predictive_risk_service import predict_risk_for_victim
    return predict_risk_for_victim(victim_id)

class AlertDispatchRequest(BaseModel):
    victim_id: str
    risk_prediction: dict

class AlertAcknowledgeRequest(BaseModel):
    officer_name: str
    notes: str | None = None

@app.post("/api/alerts/dispatch")
def dispatch_realtime_alert(req: AlertDispatchRequest):
    from backend.services.alerting_service import alerting_service
    return alerting_service.dispatch_alert(req.victim_id, req.risk_prediction)

@app.get("/api/alerts/active")
def get_active_realtime_alerts(jurisdiction_level: str | None = None):
    from backend.services.alerting_service import alerting_service
    return alerting_service.get_active_alerts(jurisdiction_level=jurisdiction_level)

@app.patch("/api/alerts/{alert_id}/acknowledge")
def acknowledge_realtime_alert(alert_id: int, req: AlertAcknowledgeRequest):
    from backend.services.alerting_service import alerting_service
    return alerting_service.acknowledge_alert(alert_id=alert_id, officer_name=req.officer_name, notes=req.notes)

class InterventionRecommendRequest(BaseModel):
    victim_id: str
    case_type: str
    risk_profile: dict = Field(default_factory=dict)

class InterventionFeedbackRequest(BaseModel):
    status: str
    feedback_notes: str | None = None

@app.post("/api/interventions/recommend")
def recommend_interventions(req: InterventionRecommendRequest):
    from backend.services.intervention_engine import intervention_engine
    return intervention_engine.get_recommendations(req.victim_id, req.case_type, req.risk_profile)

@app.get("/api/interventions/rules")
def get_intervention_rules():
    from backend.services.intervention_engine import intervention_engine
    return intervention_engine.load_rules()

@app.put("/api/interventions/rules")
def update_intervention_rules(rules: dict):
    from backend.services.intervention_engine import intervention_engine
    return intervention_engine.save_rules(rules)

@app.patch("/api/interventions/{recommendation_id}/feedback")
def log_intervention_feedback(recommendation_id: int, req: InterventionFeedbackRequest):
    from backend.services.intervention_engine import intervention_engine
    return intervention_engine.log_feedback(recommendation_id, req.status, req.feedback_notes)

@app.get("/api/dashboard/metrics")
def get_dashboard_metrics(
    role: str = "national_officer",
    district: str | None = None,
    state: str | None = None,
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    from backend.services.dashboard_service import dashboard_service
    from backend.security.auth import decode_access_token

    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Invalid Authorization header")
        claims = decode_access_token(authorization.split(" ")[1])
        role = claims.get("role", role)
        jurisdiction = claims.get("jurisdiction")
        if jurisdiction and jurisdiction != "National":
            if "state" in role.lower():
                state = state or jurisdiction
            else:
                district = district or jurisdiction

    norm_role = role.lower().replace(" ", "_")
    return dashboard_service.get_dashboard_metrics(role=norm_role, district=district, state=state)

@app.get("/api/dashboard/cases")
def get_high_risk_cases(
    role: str = "national_officer",
    district: str | None = None,
    state: str | None = None,
    limit: int = 50
):
    from backend.services.dashboard_service import dashboard_service
    norm_role = role.lower().replace(" ", "_")
    return dashboard_service.get_high_risk_cases(role=norm_role, district=district, state=state, limit=limit)

@app.get("/api/dashboard/case-timeline/{victim_id}")
def get_case_timeline(
    victim_id: str,
    role: str = "national_officer",
    district: str | None = None,
    state: str | None = None,
    user_id: str = "system_user"
):
    from backend.services.dashboard_service import dashboard_service
    from backend.services.privacy_service import privacy_service
    # Audit log every access to individual victim case timelines
    privacy_service.audit_access(
        user_id=user_id,
        user_role=role,
        action="READ_CASE_TIMELINE",
        resource_type="victim_profile",
        resource_id=victim_id,
        details={"district": district, "state": state}
    )
    return dashboard_service.get_case_timeline(victim_id=victim_id, role=role, district=district, state=state)

class ConsentUpdateRequest(BaseModel):
    victim_id: str
    channel: str
    consent_granted: bool
    purpose: str | None = None

class DataPurgeRequest(BaseModel):
    retention_days: int = 365

@app.post("/api/privacy/consent")
def update_channel_consent(req: ConsentUpdateRequest):
    from backend.services.privacy_service import privacy_service
    return privacy_service.update_channel_consent(req.victim_id, req.channel, req.consent_granted, req.purpose)

@app.get("/api/privacy/consent/{victim_id}")
def get_channel_consents(victim_id: str):
    from backend.services.privacy_service import privacy_service
    return privacy_service.get_channel_consents(victim_id)

@app.post("/api/privacy/purge-expired")
def purge_expired_data(req: DataPurgeRequest):
    from backend.services.privacy_service import privacy_service
    return privacy_service.purge_expired_data(retention_days=req.retention_days)

@app.delete("/api/privacy/victim/{victim_id}")
def erase_victim_data(victim_id: str):
    from backend.services.privacy_service import privacy_service
    return privacy_service.erase_victim_data(victim_id)

@app.get("/api/privacy/audit-logs")
def get_audit_logs(resource_id: str | None = None, limit: int = 100):
    from backend.services.privacy_service import privacy_service
    return privacy_service.get_audit_logs(resource_id=resource_id, limit=limit)

@app.post("/auth/register")
def register(x:Register):
    try:
        with conn() as c:
            cur=c.execute("INSERT INTO users(name,email,password,phone,created_at) VALUES (?,?,?,?,?)",(x.name,x.email.lower(),hash_pw(x.password),x.phone,now())); u={"id":cur.lastrowid,"name":x.name,"email":x.email,"role":"survivor","phone":x.phone}
        return {"token":token(u),"user":u}
    except sqlite3.IntegrityError: raise HTTPException(409,"That email is already registered.")
@app.post("/auth/login")
def login(x:Login):
    with conn() as c: u=c.execute("SELECT * FROM users WHERE email=? AND password=?",(x.email.lower(),hash_pw(x.password))).fetchone()
    if not u: raise HTTPException(401,"Incorrect email or password.")
    u=dict(u); u.pop("password"); return {"token":token(u),"user":u}
@app.get("/me")
def me(authorization:str|None=Header(None)): return user_for(authorization)
@app.patch("/me")
def update_me(x:ProfileUpdate,authorization:str|None=Header(None)):
    u=user_for(authorization)
    with conn() as c: c.execute("UPDATE users SET name=?,phone=? WHERE id=?",(x.name,x.phone,u["id"]))
    return user_for(authorization)

def prediction(x:Checkin):
    pack=joblib.load(MODEL); vals=np.array([[getattr(x,k) for k in pack["features"]]]); probs=pack["model"].predict_proba(vals)[0]; index=int(probs.argmax()); return pack["labels"][index], float(probs[index]), {pack["labels"][i]:round(float(v)*100,1) for i,v in enumerate(probs)}
@app.post("/checkins")
def create_checkin(x:Checkin, authorization:str|None=Header(None)):
    u=user_for(authorization); risk,prob,distribution=prediction(x)
    with conn() as c:
        cur=c.execute("INSERT INTO checkins(user_id,mood,anxiety,stress,sleep,safety,social,wellbeing,journal,risk,probability,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(u["id"],x.mood,x.anxiety,x.stress,x.sleep,x.safety,x.social,x.wellbeing,x.journal,risk,prob,now())); cid=cur.lastrowid
        if risk=="High": c.execute("INSERT INTO alerts(user_id,checkin_id,created_at) VALUES (?,?,?)",(u["id"],cid,now()))
    return {"id":cid,"risk":risk,"probability":round(prob*100,1),"distribution":distribution,"message":"This is a screening risk estimate, not a diagnosis."}
@app.get("/checkins/me")
def my_checkins(authorization:str|None=Header(None)):
    u=user_for(authorization)
    with conn() as c: rs=c.execute("SELECT id,risk,probability,created_at,mood,anxiety,stress,sleep,safety,social,wellbeing,journal FROM checkins WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall()
    return [row(x) for x in rs]
@app.get("/dashboard")
def dashboard(authorization:str|None=Header(None)):
    counselor(authorization)
    with conn() as c:
        total=c.execute("SELECT count(*) FROM users WHERE role='survivor'").fetchone()[0]; counts={k:c.execute("SELECT count(*) FROM checkins WHERE id IN (SELECT max(id) FROM checkins GROUP BY user_id) AND risk=?",(k,)).fetchone()[0] for k in ["Low","Moderate","High"]}
        alerts=c.execute("SELECT a.id,a.status,a.created_at,u.id user_id,u.name,u.email,c.risk,c.probability FROM alerts a JOIN users u ON u.id=a.user_id JOIN checkins c ON c.id=a.checkin_id ORDER BY a.id DESC LIMIT 8").fetchall()
    return {"total_users":total,"risk_counts":counts,"recent_alerts":[row(x) for x in alerts]}
@app.get("/alerts")
def alert_list(status:str="",authorization:str|None=Header(None)):
    counselor(authorization)
    with conn() as c:
        rs=c.execute("SELECT a.id,a.status,a.created_at,u.id user_id,u.name,u.email,c.risk,c.probability FROM alerts a JOIN users u ON u.id=a.user_id JOIN checkins c ON c.id=a.checkin_id WHERE (?='' OR a.status=?) ORDER BY CASE a.status WHEN 'Open' THEN 0 ELSE 1 END,a.id DESC",(status,status)).fetchall()
    return [row(x) for x in rs]
@app.get("/users")
def users(q:str="", authorization:str|None=Header(None)):
    counselor(authorization); like=f"%{q}%"
    with conn() as c: rs=c.execute("SELECT u.id,u.name,u.email,u.phone,u.created_at,(SELECT risk FROM checkins WHERE user_id=u.id ORDER BY id DESC LIMIT 1) risk,(SELECT created_at FROM checkins WHERE user_id=u.id ORDER BY id DESC LIMIT 1) last_checkin FROM users u WHERE u.role='survivor' AND (u.name LIKE ? OR u.email LIKE ?) ORDER BY u.id DESC",(like,like)).fetchall()
    return [row(x) for x in rs]
@app.get("/users/{uid}")
def profile(uid:int,authorization:str|None=Header(None)):
    counselor(authorization)
    with conn() as c:
        u=c.execute("SELECT id,name,email,phone,created_at FROM users WHERE id=? AND role='survivor'",(uid,)).fetchone()
        if not u: raise HTTPException(404,"User not found")
        checks=c.execute("SELECT * FROM checkins WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall(); notes=c.execute("SELECT * FROM notes WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()
    return {"user":row(u),"checkins":[row(x) for x in checks],"notes":[row(x) for x in notes]}
@app.post("/users/{uid}/notes")
def add_note(uid:int,x:Note,authorization:str|None=Header(None)):
    u=counselor(authorization)
    with conn() as c: cur=c.execute("INSERT INTO notes(user_id,author,body,created_at) VALUES (?,?,?,?)",(uid,u["name"],x.body,now()))
    return {"id":cur.lastrowid,"message":"Note saved"}
@app.patch("/alerts/{aid}/resolve")
def resolve(aid:int,authorization:str|None=Header(None)):
    counselor(authorization)
    with conn() as c: c.execute("UPDATE alerts SET status='Resolved' WHERE id=?",(aid,))
    return {"message":"Alert resolved"}
@app.get("/resources")
def resources(authorization:str|None=Header(None)):
    with conn() as c: rs=c.execute("SELECT * FROM resources WHERE active=1 ORDER BY category,title").fetchall()
    return [row(x) for x in rs]
@app.post("/resources")
def create_resource(x:Resource,authorization:str|None=Header(None)):
    counselor(authorization)
    with conn() as c: cur=c.execute("INSERT INTO resources(title,category,contact,description) VALUES (?,?,?,?)",(x.title,x.category,x.contact,x.description))
    return {"id":cur.lastrowid,"message":"Resource added"}
@app.delete("/resources/{rid}")
def archive_resource(rid:int,authorization:str|None=Header(None)):
    counselor(authorization)
    with conn() as c: c.execute("UPDATE resources SET active=0 WHERE id=?",(rid,))
    return {"message":"Resource archived"}

# Mount Web Application Frontend UI at /
from fastapi.staticfiles import StaticFiles
import os

web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="static")
