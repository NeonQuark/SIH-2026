# Privacy & Security Compliance Checklist

This document details the privacy, security, data protection, and legal compliance controls implemented in the Victim Distress-Monitoring System under the **Digital Personal Data Protection (DPDP) Act 2023 (India)** and the **Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act framework**.

---

## Compliance Control Summary Matrix

| Control Category | Technical Implementation | Status | Verification Reference |
|---|---|---|---|
| **PII Encryption at Rest** | AES-256 Fernet symmetric cryptography (`backend/security/crypto.py`) on `case_id`, `name`, `phone`, `address`, `contact`. | **COMPLIANT** | [`tests/test_data_model.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/tests/test_data_model.py) |
| **PII Encryption in Transit** | TLS/HTTPS enforced for all REST API endpoints (`backend/main.py`). | **COMPLIANT** | [`backend/main.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/backend/main.py) |
| **Role-Based Access Control (RBAC)** | Strict geographic and role-scoped data isolation (`district_officer`, `state_officer`, `national_officer`, `counselor`, `admin`). | **COMPLIANT** | [`tests/test_dashboard_service.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/tests/test_dashboard_service.py) |
| **PII Masking & Pseudonymization** | Analytics tables join strictly via pseudonymized `victim_id` UUID strings. PII masked for unauthorized roles (`J*** D***`, `+91*****3210`). | **COMPLIANT** | [`backend/services/privacy_service.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/backend/services/privacy_service.py) |
| **Immutable Audit Logging** | Access logging of every case read/write action (`who`, `when`, `action`, `resource_id`, `ip`) in `audit_logs` table. | **COMPLIANT** | [`tests/test_privacy_service.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/tests/test_privacy_service.py) |
| **Data Retention Policy Hooks** | Configurable data retention purge hook (`purge_expired_data(retention_days=365)`) for historical logs & scores. | **COMPLIANT** | `POST /api/privacy/purge-expired` |
| **Right to be Forgotten (Data Erasure)** | Automated victim data erasure hook (`erase_victim_data(victim_id)`) removing all associated profile & log entries. | **COMPLIANT** | `DELETE /api/privacy/victim/{victim_id}` |
| **Multi-Channel Consent Tracking** | Per-channel opt-in/opt-out consent tracking (`chatbot`, `ivrs`, `sms`, `web_portal`, `mobile_app`) in `channel_consents` table. | **COMPLIANT** | `POST /api/privacy/consent` |

---

## 1. PII Encryption at Rest & In Transit

- **Encryption Standard:** AES-256 Fernet derived via SHA-256 key stretching from `APP_SECRET` / `ENCRYPTION_KEY`.
- **Encrypted Columns:** `case_id_enc`, `name_enc`, `phone_enc`, `address_enc`, `contact_enc` in `victims` table.
- **Decryption Controls:** Decryption occurs transparently via SQLAlchemy hybrid properties exclusively when requested by authorized sessions. Raw SQL queries on database files inspect ciphertexts (`gAAAAAB...`) preventing unauthenticated exposure.

---

## 2. Role-Based Access Control (RBAC) & PII Isolation

- **District Level Scope:** District Officers can only view data where `victim.district == assigned_district`.
- **State Level Scope:** State SC/ST Commission Officers can only view data where `victim.state == assigned_state`.
- **National Level Scope:** National Atrocities Prevention Cell holds aggregate access.
- **Analytics Separation:** Public and analytics endpoints return pseudonymized `victim_id` UUID strings without raw PII.

---

## 3. Immutable Audit Logging Architecture

Every API request accessing individual victim case timelines or profiles executes `privacy_service.audit_access()`, logging:
- `user_id`: Identifier of the user or officer making the request.
- `user_role`: Role of the caller (`district_officer`, `state_officer`, `counselor`, `admin`).
- `action`: Specific operation performed (`READ_CASE_TIMELINE`, `VIEW_VICTIM_PROFILE`, `ERASE_VICTIM_DATA`).
- `resource_id`: Pseudonymized `victim_id` or case target ID.
- `timestamp`: UTC ISO timestamp.

Audit records are stored in the immutable `audit_logs` database table and exposed to compliance officers via `GET /api/privacy/audit-logs`.

---

## 4. Data Retention & Deletion Policy Hooks

- **Purge Hook:** `purge_expired_data(retention_days=365)` automatically deletes interaction logs and distress scores exceeding the statutory retention period under SC/ST Act reporting guidelines.
- **Right to be Forgotten:** `erase_victim_data(victim_id)` allows data fiduciaries to process statutory deletion requests, removing records across all 7 database tables.

---

## 5. Multi-Channel Consent Management

Communication channels (`chatbot`, `ivrs`, `sms`, `web_portal`, `mobile_app`) enforce explicit consent:
- `consent_granted`: Boolean opt-in status.
- `consent_timestamp`: Timestamp when consent was recorded.
- `opt_out_timestamp`: Timestamp when victim requested opt-out / channel suppression.
- `consent_purpose`: Documented processing purpose under Section 6 of DPDP Act 2023.

---

## 6. Audit Trail & Verification Suite

Comprehensive privacy and security test coverage is implemented in:
- [`tests/test_data_model.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/tests/test_data_model.py) (PII Encryption & Pseudonymized Joins)
- [`tests/test_dashboard_service.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/tests/test_dashboard_service.py) (RBAC Scoping & Zero PII Guarantee)
- [`tests/test_privacy_service.py`](file:///c:/Users/itzab/OneDrive/Desktop/SIH/Software/tests/test_privacy_service.py) (Audit Logging, Consent Tracking & Retention Hooks)
