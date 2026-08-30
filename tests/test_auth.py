import time
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from backend.main import app
from backend.security.auth import create_access_token, decode_access_token, hash_password, verify_password

client = TestClient(app)

def test_password_hashing_and_verification():
    raw_pass = "District@123"
    hashed = hash_password(raw_pass)

    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

def test_valid_login_issues_working_jwt():
    res = client.post("/api/auth/login", json={
        "username": "district_officer",
        "password": "District@123"
    })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "authenticated"
    assert "access_token" in data
    assert data["user"]["role"] == "district_officer"
    assert data["user"]["jurisdiction"] == "Hathras"

    # Verify decoded claims
    claims = decode_access_token(data["access_token"])
    assert claims["role"] == "district_officer"
    assert claims["jurisdiction"] == "Hathras"

def test_expired_or_invalid_tokens_rejected():
    # 1. Invalid signature
    res_bad = client.get("/api/dashboard/metrics", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert res_bad.status_code == 401

    # 2. Expired token
    expired_token = create_access_token(user_id="test_user", role="counsellor", jurisdiction="Hathras", expires_delta=timedelta(seconds=-10))
    res_exp = client.get("/api/dashboard/metrics", headers={"Authorization": f"Bearer {expired_token}"})
    assert res_exp.status_code == 401

def test_token_refresh_endpoint():
    # Login to get valid token
    login_res = client.post("/api/auth/login", json={
        "username": "counselor_ananya",
        "password": "Demo@123"
    })
    tok = login_res.json()["access_token"]

    # Call refresh endpoint
    ref_res = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {tok}"})
    assert ref_res.status_code == 200
    ref_data = ref_res.json()
    assert ref_data["status"] == "refreshed"
    assert "access_token" in ref_data

    # Verify refreshed claims
    claims = decode_access_token(ref_data["access_token"])
    assert claims["role"] == "counsellor"
    assert claims["jurisdiction"] == "Hathras"

def test_role_jurisdiction_rbac_data_restriction_with_real_jwt():
    # Generate real signed JWT for District Officer Hathras
    district_jwt = create_access_token(user_id="dist_officer_1", role="district_officer", jurisdiction="Hathras")

    res_dist = client.get(
        "/api/dashboard/metrics?role=district_officer&district=Hathras",
        headers={"Authorization": f"Bearer {district_jwt}"}
    )
    assert res_dist.status_code == 200
    data_dist = res_dist.json()
    assert data_dist["jurisdiction_scope"]["role"] == "district_officer"
    assert data_dist["jurisdiction_scope"]["district"] == "Hathras"
