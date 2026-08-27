import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

endpoints = [
    "/health",
    "/state",
    "/ambulance",
    "/traffic",
    "/signals",
    "/decisions"
]

print("\n============================================================")
print("DIGITAL TWIN API VALIDATION")
print("============================================================")

all_passed = True

for ep in endpoints:
    url = f"{BASE_URL}{ep}"
    print(f"\nGET {ep}")
    try:
        response = requests.get(url)
        print(f"Status: {response.status_code}")
        try:
            data = response.json()
            print(json.dumps(data, indent=2))
        except:
            print(response.text)
            all_passed = False
    except Exception as e:
        print(f"Error connecting to {ep}: {e}")
        all_passed = False

print("\n============================================================")
print(f"API VALIDATION: {'PASS' if all_passed else 'FAIL'}")
print("============================================================")
