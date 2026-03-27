"""Quick integration test for fraud prevention endpoints."""
import requests
import json

BASE = "http://127.0.0.1:8000/api"

print("=== FARMER DECLARATION ===")
r = requests.post(f"{BASE}/farmer-declaration", json={
    "farmer_id": "F001",
    "farmer_name": "Ramu Kisan",
    "farmer_mobile": "9876543210",
    "declared_amount": 200000,
    "purpose": "Crop cultivation",
    "otp": "123456"
})
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text}")
    exit(1)
dec = r.json()
print(f"Declaration ID: {dec.get('declaration_id')}")
print(f"Amount: {dec.get('declared_amount')}")
dec_id = dec.get("declaration_id")

print("\n=== CREATE LOAN ===")
r = requests.post(f"{BASE}/loans/create", json={
    "farmer_id": "F001",
    "farmer_name": "Ramu Kisan",
    "farmer_mobile": "9876543210",
    "amount": 250000,
    "tenure_months": 12,
    "interest_rate": 7.5,
    "purpose": "Crop cultivation and equipment",
    "created_by": "EMP001",
    "declaration_id": dec_id,
    "amount_difference_reason": "Additional funds for equipment"
})
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text}")
    exit(1)
loan = r.json()
loan_id = loan.get("loan_id")
print(f"Loan ID: {loan_id}")
print(f"Farmer Declared: {loan.get('farmer_declared_amount')}")
print(f"Loan Amount: {loan.get('amount')}")

print("\n=== DISBURSEMENT CONSENT ===")
r = requests.post(f"{BASE}/loans/{loan_id}/disbursement-consent", json={
    "account_number": "1234567890123456",
    "account_holder_name": "Ramu Kisan",
    "ifsc_code": "SBIN0001234"
})
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text}")
    exit(1)
disb = r.json()
print(f"Penny Drop Verified: {disb.get('penny_drop_verified')}")
print(f"Name Matched: {disb.get('penny_drop_name_matched')}")

print("\n=== FARMER CONSENT ===")
r = requests.post(f"{BASE}/loans/{loan_id}/farmer-consent", json={
    "otp": "123456",
    "device_info": {"platform": "test"},
    "live_photo_base64": "dGVzdF9waG90b19kYXRh",
    "gps_latitude": 19.076,
    "gps_longitude": 72.877,
    "device_fingerprint": "{\"test\": true}"
})
print(f"Status: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text}")
    exit(1)
consent = r.json()
print(f"Photo Hash: {consent.get('live_photo_hash')}")
print(f"GPS: {consent.get('gps_latitude')}, {consent.get('gps_longitude')}")

print("\n=== ALL TESTS PASSED ===")
