"""Seed sample nested rules for the E2E Tester account."""

from __future__ import annotations

import uuid

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
EMAIL = "e2e_764150c8@eatech.com"
PASSWORD = "TestPass@12345"


def rid() -> str:
    return str(uuid.uuid4())


PAYLOADS = [
    {
        "name": "Software at INFOTREE (nested)",
        "description": "Nested: company INFOTREE AND industry Software",
        "is_template": True,
        "rules": [
            {
                "id": rid(),
                "type": "contact",
                "field": "company",
                "operator": "=",
                "value": "INFOTREE",
                "next_operator": "AND",
                "group_start": 1,
                "group_end": 0,
            },
            {
                "id": rid(),
                "type": "contact",
                "field": "industry",
                "operator": "=",
                "value": "Software",
                "next_operator": "END",
                "group_start": 0,
                "group_end": 1,
            },
        ],
    },
    {
        "name": "Active OR Website source",
        "description": "OR group: Active status OR Website source",
        "is_template": True,
        "rules": [
            {
                "id": rid(),
                "type": "contact",
                "field": "status",
                "operator": "=",
                "value": "Active",
                "next_operator": "OR",
                "group_start": 1,
                "group_end": 0,
            },
            {
                "id": rid(),
                "type": "contact",
                "field": "source",
                "operator": "=",
                "value": "Website",
                "next_operator": "END",
                "group_start": 0,
                "group_end": 1,
            },
        ],
    },
    {
        "name": "India English speakers",
        "description": "Country India AND language English",
        "is_template": False,
        "rules": [
            {
                "id": rid(),
                "type": "contact",
                "field": "country",
                "operator": "=",
                "value": "India",
                "next_operator": "AND",
                "group_start": 0,
                "group_end": 0,
            },
            {
                "id": rid(),
                "type": "contact",
                "field": "language",
                "operator": "=",
                "value": "English",
                "next_operator": "END",
                "group_start": 0,
                "group_end": 0,
            },
        ],
    },
    {
        "name": "Deep nest: ((Company AND City) OR Status)",
        "description": "Double nesting demo for E2E Tester",
        "is_template": True,
        "rules": [
            {
                "id": rid(),
                "type": "contact",
                "field": "company",
                "operator": "LIKE",
                "value": "Info",
                "next_operator": "AND",
                "group_start": 2,
                "group_end": 0,
            },
            {
                "id": rid(),
                "type": "contact",
                "field": "city",
                "operator": "=",
                "value": "Bangalore",
                "next_operator": "OR",
                "group_start": 0,
                "group_end": 1,
            },
            {
                "id": rid(),
                "type": "contact",
                "field": "status",
                "operator": "=",
                "value": "Active",
                "next_operator": "END",
                "group_start": 0,
                "group_end": 1,
            },
        ],
    },
    {
        "name": "SDE job titles",
        "description": "Job title contains SDE",
        "is_template": False,
        "rules": [
            {
                "id": rid(),
                "type": "contact",
                "field": "job_title",
                "operator": "LIKE",
                "value": "SDE",
                "next_operator": "END",
                "group_start": 0,
                "group_end": 0,
            },
        ],
    },
]


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        print("login", login.status_code)
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        for payload in PAYLOADS:
            # regenerate ids for uniqueness each run
            for rule in payload["rules"]:
                rule["id"] = rid()
            response = client.post("/rules/save", headers=headers, json=payload)
            if response.status_code == 201:
                print("saved:", payload["name"], "->", response.json()["id"])
            else:
                print("FAIL:", payload["name"], response.status_code, response.text[:300])

        listed = client.get("/rules", headers=headers, params={"page": 1, "page_size": 20})
        body = listed.json()
        print("\nTotal for E2E Tester:", body.get("total"))
        for item in body.get("items", []):
            print(
                f"- {item['name']} | template={item['is_template']} | {item['query_text']}"
            )


if __name__ == "__main__":
    main()
