import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.dashboard_service import dashboard_service, DashboardAnalyticsService
from backend.db.session import SessionLocal
from backend.db.models import VictimProfile, DistressScore, RiskAlert, InterventionRecommendation

client = TestClient(app)

def test_rbac_scoping_district_vs_national():
    db = SessionLocal()
    try:
        dist_name = f"TestDistrict_{uuid.uuid4().hex[:6]}"
        vid1 = f"v_hathras_{uuid.uuid4().hex[:6]}"
        vid2 = f"v_patna_{uuid.uuid4().hex[:6]}"

        v1 = VictimProfile(victim_id=vid1, name="Encrypted Name 1", district=dist_name, state="Uttar Pradesh")
        v2 = VictimProfile(victim_id=vid2, name="Encrypted Name 2", district="Patna", state="Bihar")
        db.add_all([v1, v2])
        db.commit()

        # Add distress scores
        ds1 = DistressScore(victim_id=vid1, score=75.0)
        ds2 = DistressScore(victim_id=vid2, score=45.0)
        db.add_all([ds1, ds2])
        db.commit()

        # District Scoped Query -> Unique district only
        metrics_dist = dashboard_service.get_dashboard_metrics(
            role="district_officer",
            district=dist_name,
            db=db
        )
        assert metrics_dist["jurisdiction_scope"]["district"] == dist_name
        assert metrics_dist["jurisdiction_scope"]["scoped_victim_count"] == 1

        # National Scoped Query -> All victims
        metrics_nat = dashboard_service.get_dashboard_metrics(
            role="national_officer",
            db=db
        )
        assert metrics_nat["jurisdiction_scope"]["scoped_victim_count"] >= 2
    finally:
        db.close()

def test_sla_metrics_and_intervention_stats():
    db = SessionLocal()
    try:
        vid = f"v_stats_{uuid.uuid4().hex[:6]}"
        v = VictimProfile(victim_id=vid, district="Hathras", state="Uttar Pradesh")
        db.add(v)
        db.commit()

        # Add Alerts (1 IN_SLA, 1 BREACHED)
        a1 = RiskAlert(victim_id=vid, trigger_reason="Critical risk", threshold_crossed="Critical 75", status="ACKNOWLEDGED", sla_status="IN_SLA")
        a2 = RiskAlert(victim_id=vid, trigger_reason="High risk", threshold_crossed="High 65", status="Open", sla_status="BREACHED")
        db.add_all([a1, a2])

        # Add Interventions (1 acted_upon, 1 ignored)
        i1 = InterventionRecommendation(victim_id=vid, intervention_type="medical", status="acted_upon")
        i2 = InterventionRecommendation(victim_id=vid, intervention_type="relocation", status="ignored")
        db.add_all([i1, i2])
        db.commit()

        metrics = dashboard_service.get_dashboard_metrics(role="national_officer", db=db)
        sla = metrics["sla_metrics"]
        assert sla["total_alerts"] >= 2
        assert sla["in_sla_count"] >= 1
        assert sla["breached_count"] >= 1

        interv = metrics["intervention_stats"]
        assert interv["total_recommended"] >= 2
        assert interv["acted_upon_count"] >= 1
        assert interv["ignored_count"] >= 1
        assert interv["acceptance_rate_pct"] > 0.0
    finally:
        db.close()

def test_zero_pii_in_payloads():
    db = SessionLocal()
    try:
        vid = f"v_pii_check_{uuid.uuid4().hex[:6]}"
        v = VictimProfile(victim_id=vid, name="Secret Real Name", phone="9999999999", district="Hathras", state="Uttar Pradesh")
        db.add(v)
        db.commit()

        ds = DistressScore(victim_id=vid, score=80.0)
        db.add(ds)
        db.commit()

        cases = dashboard_service.get_high_risk_cases(role="national_officer", limit=500, db=db)
        case_item = next((c for c in cases if c["victim_id"] == vid), None)
        assert case_item is not None

        # Verify zero PII keys in payload
        assert "name" not in case_item
        assert "phone" not in case_item
        assert "address" not in case_item
        assert case_item["victim_id"] == vid

        timeline = dashboard_service.get_case_timeline(victim_id=vid, role="national_officer", db=db)
        assert "name" not in timeline
        assert "phone" not in timeline
        assert timeline["victim_id"] == vid
    finally:
        db.close()

def test_api_dashboard_endpoints():
    vid = f"v_api_dash_{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        v = VictimProfile(victim_id=vid, district="Hathras", state="Uttar Pradesh")
        db.add(v)
        ds = DistressScore(victim_id=vid, score=85.0)
        db.add(ds)
        db.commit()
    finally:
        db.close()

    # GET /api/dashboard/metrics
    res_m = client.get("/api/dashboard/metrics?role=district_officer&district=Hathras")
    assert res_m.status_code == 200
    data_m = res_m.json()
    assert "distress_trends" in data_m
    assert "sla_metrics" in data_m
    assert "intervention_stats" in data_m

    # GET /api/dashboard/cases
    res_c = client.get("/api/dashboard/cases?role=national_officer")
    assert res_c.status_code == 200
    assert isinstance(res_c.json(), list)

    # GET /api/dashboard/case-timeline/{victim_id}
    res_t = client.get(f"/api/dashboard/case-timeline/{vid}?role=national_officer")
    assert res_t.status_code == 200
    data_t = res_t.json()
    assert data_t["victim_id"] == vid
    assert "timeline" in data_t
