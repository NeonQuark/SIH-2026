import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure model exists before importing app
from backend.train_model import train
train()

from backend.main import app, conn

client = TestClient(app)

def test_train_model_execution():
    """Verify that model training outputs a valid joblib artifact."""
    model_path = Path(__file__).resolve().parents[1] / "data" / "risk_model.joblib"
    assert model_path.exists(), "risk_model.joblib should exist after training"

def test_health_endpoint():
    """Verify system health endpoint."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "disclaimer" in data

import uuid

def test_auth_flow():
    """Test user registration, login, and authorization."""
    unique_email = f"testuser_{uuid.uuid4().hex[:8]}@saathicare.demo"
    # Register survivor
    reg_payload = {
        "name": "Test User",
        "email": unique_email,
        "password": "Password123",
        "phone": "9876543210"
    }
    res = client.post("/auth/register", json=reg_payload)
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["user"]["email"] == unique_email
    survivor_token = data["token"]

    # Duplicate registration should fail
    res_dup = client.post("/auth/register", json=reg_payload)
    assert res_dup.status_code == 409

    # Login survivor
    login_payload = {
        "email": unique_email,
        "password": "Password123"
    }
    res_login = client.post("/auth/login", json=login_payload)
    assert res_login.status_code == 200
    assert "token" in res_login.json()

    # Get /me profile
    res_me = client.get("/me", headers={"Authorization": f"Bearer {survivor_token}"})
    assert res_me.status_code == 200
    assert res_me.json()["name"] == "Test User"

    # Update /me profile
    res_patch = client.patch(
        "/me",
        json={"name": "Updated Name", "phone": "1112223333"},
        headers={"Authorization": f"Bearer {survivor_token}"}
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["name"] == "Updated Name"

def test_checkin_and_risk_prediction():
    """Test check-in submission and screening risk estimation."""
    # Login seed survivor
    login_res = client.post("/auth/login", json={"email": "asha@saathicare.demo", "password": "Demo@123"})
    assert login_res.status_code == 200
    token = login_res.json()["token"]

    # Submit Low-risk check-in
    low_checkin = {
        "mood": 1, "anxiety": 1, "stress": 1, "sleep": 1,
        "safety": 1, "social": 1, "wellbeing": 1, "journal": "Feeling good today."
    }
    res_low = client.post("/checkins", json=low_checkin, headers={"Authorization": f"Bearer {token}"})
    assert res_low.status_code == 200
    data_low = res_low.json()
    assert "risk" in data_low
    assert "probability" in data_low

    # Submit High-risk check-in
    high_checkin = {
        "mood": 5, "anxiety": 5, "stress": 5, "sleep": 5,
        "safety": 5, "social": 5, "wellbeing": 5, "journal": "High distress day."
    }
    res_high = client.post("/checkins", json=high_checkin, headers={"Authorization": f"Bearer {token}"})
    assert res_high.status_code == 200
    data_high = res_high.json()
    assert data_high["risk"] == "High"

    # Retrieve check-ins
    res_my = client.get("/checkins/me", headers={"Authorization": f"Bearer {token}"})
    assert res_my.status_code == 200
    assert len(res_my.json()) >= 2

def test_counselor_workflow():
    """Test counselor login, dashboard, alert review, notes, and resources."""
    # Login counselor
    login_res = client.post("/auth/login", json={"email": "counselor@saathicare.demo", "password": "Demo@123"})
    assert login_res.status_code == 200
    c_token = login_res.json()["token"]
    c_headers = {"Authorization": f"Bearer {c_token}"}

    # Get Dashboard
    res_dash = client.get("/dashboard", headers=c_headers)
    assert res_dash.status_code == 200
    assert "total_users" in res_dash.json()

    # Get Alerts
    res_alerts = client.get("/alerts", headers=c_headers)
    assert res_alerts.status_code == 200
    alerts = res_alerts.json()
    assert len(alerts) > 0

    # Resolve alert if any open
    open_alert = next((a for a in alerts if a["status"] == "Open"), None)
    if open_alert:
        res_res = client.patch(f"/alerts/{open_alert['id']}/resolve", headers=c_headers)
        assert res_res.status_code == 200
        assert res_res.json()["message"] == "Alert resolved"

    # Get Users list
    res_users = client.get("/users", headers=c_headers)
    assert res_users.status_code == 200
    users_list = res_users.json()
    assert len(users_list) > 0
    survivor_id = users_list[0]["id"]

    # Get Survivor Profile & Add Note
    res_prof = client.get(f"/users/{survivor_id}", headers=c_headers)
    assert res_prof.status_code == 200

    res_note = client.post(f"/users/{survivor_id}/notes", json={"body": "Followed up with survivor."}, headers=c_headers)
    assert res_note.status_code == 200

def test_resources_management():
    """Test public resource listing and counselor resource management."""
    # Public get resources
    res_list = client.get("/resources")
    assert res_list.status_code == 200
    initial_count = len(res_list.json())

    # Counselor add resource
    login_res = client.post("/auth/login", json={"email": "counselor@saathicare.demo", "password": "Demo@123"})
    c_headers = {"Authorization": f"Bearer {login_res.json()['token']}"}

    new_res = {
        "title": "KIRAN Helpline",
        "category": "Mental Health Helpline",
        "contact": "1800-599-0019",
        "description": "24/7 Toll-free mental health rehabilitation helpline."
    }
    res_create = client.post("/resources", json=new_res, headers=c_headers)
    assert res_create.status_code == 200
    rid = res_create.json()["id"]

    # Counselor archive resource
    res_del = client.delete(f"/resources/{rid}", headers=c_headers)
    assert res_del.status_code == 200
