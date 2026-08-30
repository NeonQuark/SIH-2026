import uuid
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.alerting_service import alerting_service, RealtimeAlertingService
from backend.db.session import SessionLocal
from backend.db.models import VictimProfile, RiskAlert

client = TestClient(app)

def test_jurisdictional_routing_district_vs_state():
    db = SessionLocal()
    try:
        vid = f"victim_{uuid.uuid4().hex[:6]}"
        victim = VictimProfile(victim_id=vid, district="Hathras", state="Uttar Pradesh")
        db.add(victim)
        db.commit()

        service = RealtimeAlertingService()

        # High risk -> District Officer
        pred_high = {"risk_tier": "high", "trend": {"direction": "stable"}}
        route_high = service.resolve_jurisdiction(victim, pred_high)
        assert route_high["jurisdiction_level"] == "district"
        assert "District_Officer_Hathras" in route_high["recipient_role"]
        assert route_high["sla_minutes"] == 120

        # Critical + Worsening -> State Commission
        pred_crit_worsening = {"risk_tier": "critical", "trend": {"direction": "worsening"}}
        route_state = service.resolve_jurisdiction(victim, pred_crit_worsening)
        assert route_state["jurisdiction_level"] == "state"
        assert "State_SC_ST_Commission_Uttar Pradesh" in route_state["recipient_role"]
        assert route_state["sla_minutes"] == 60
    finally:
        db.close()

def test_deduplication_cooldown_window():
    vid = f"victim_dedup_{uuid.uuid4().hex[:6]}"
    pred = {"risk_tier": "critical", "projected_score_next_period": 84.0}

    # 1. First dispatch -> Should succeed
    res1 = alerting_service.dispatch_alert(victim_id=vid, risk_prediction=pred)
    assert res1["status"] == "dispatched"
    assert "alert_id" in res1
    alert_id = res1["alert_id"]

    # 2. Second dispatch within 60 min cooldown -> Should be deduplicated
    res2 = alerting_service.dispatch_alert(victim_id=vid, risk_prediction=pred)
    assert res2["status"] == "deduplicated"
    assert res2["alert_id"] == alert_id
    assert "cooldown_until" in res2

def test_multi_channel_delivery_and_acknowledgement_sla():
    vid = f"victim_sla_{uuid.uuid4().hex[:6]}"
    pred = {"risk_tier": "critical", "projected_score_next_period": 82.0}

    res_dispatch = alerting_service.dispatch_alert(victim_id=vid, risk_prediction=pred)
    assert res_dispatch["status"] == "dispatched"
    assert "dashboard" in res_dispatch["delivery_channels"]
    assert "sms" in res_dispatch["delivery_channels"]
    assert "email" in res_dispatch["delivery_channels"]

    alert_id = res_dispatch["alert_id"]

    # Acknowledge within SLA
    res_ack = alerting_service.acknowledge_alert(
        alert_id=alert_id,
        officer_name="Officer_Vikram_Singh",
        notes="Dispatched local patrol to survivor location."
    )
    assert res_ack["status"] == "acknowledged"
    assert res_ack["officer_name"] == "Officer_Vikram_Singh"
    assert res_ack["sla_status"] == "IN_SLA"

def test_api_alert_endpoints():
    vid = f"api_alert_{uuid.uuid4().hex[:6]}"
    dispatch_payload = {
        "victim_id": vid,
        "risk_prediction": {
            "risk_tier": "critical",
            "projected_score_next_period": 88.0
        }
    }

    # POST /api/alerts/dispatch
    res = client.post("/api/alerts/dispatch", json=dispatch_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "dispatched"
    alert_id = data["alert_id"]

    # GET /api/alerts/active
    res_active = client.get("/api/alerts/active?jurisdiction_level=district")
    assert res_active.status_code == 200
    active_list = res_active.json()
    assert any(a["id"] == alert_id for a in active_list)

    # PATCH /api/alerts/{id}/acknowledge
    ack_payload = {"officer_name": "Officer_Ananya", "notes": "On site."}
    res_ack = client.patch(f"/api/alerts/{alert_id}/acknowledge", json=ack_payload)
    assert res_ack.status_code == 200
    assert res_ack.json()["status"] == "acknowledged"
