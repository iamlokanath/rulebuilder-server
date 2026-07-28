"""
Dynamic Rule Builder — full E2E automation suite.

Covers every API endpoint, auth flows, nested rule features, contact filtering,
pagination/search/templates, and assignment requirement checks (i18n, theme,
Docker, unit tests, Swagger, JWT).

Usage (from backend/ with venv active, API running on :8000):

    python scripts/e2e_automation.py
    python scripts/e2e_automation.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

DEFAULT_BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
API = "/api/v1"
ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@eatech.com")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "Admin@12345")
FRONTEND_URL = os.getenv("E2E_FRONTEND_URL", "http://127.0.0.1:5173")


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""
    duration_ms: float = 0.0


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def add(self, result: Result) -> None:
        self.results.append(result)
        mark = "PASS" if result.ok else "FAIL"
        detail = result.detail.replace("\u2192", "->") if result.detail else ""
        line = f"  [{mark}] {result.name}" + (f" - {detail}" if detail else "")
        print(line.encode("ascii", "replace").decode("ascii"))

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        self.add(Result(name=name, ok=bool(condition), detail=detail if not condition or detail else ""))
        return bool(condition)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)


def run_case(suite: Suite, name: str, fn: Callable[[], str | None]) -> None:
    started = time.perf_counter()
    try:
        detail = fn() or ""
        suite.add(
            Result(
                name=name,
                ok=True,
                detail=detail,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        )
    except Exception as exc:  # noqa: BLE001
        suite.add(
            Result(
                name=name,
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        )


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sample_rules(
    *,
    company: str = "INFOTREE",
    nested: bool = True,
    as_template_ready: bool = False,
) -> list[dict[str, Any]]:
    if nested:
        return [
            {
                "id": str(uuid.uuid4()),
                "type": "contact",
                "field": "company",
                "operator": "=",
                "value": company,
                "next_operator": "AND",
                "group_start": 1,
                "group_end": 0,
            },
            {
                "id": str(uuid.uuid4()),
                "type": "contact",
                "field": "industry",
                "operator": "=",
                "value": "Software",
                "next_operator": "END",
                "group_start": 0,
                "group_end": 1,
            },
        ]
    return [
        {
            "id": str(uuid.uuid4()),
            "type": "contact",
            "field": "company",
            "operator": "=",
            "value": company,
            "next_operator": "END",
            "group_start": 0,
            "group_end": 0,
        }
    ]


# ---------------------------------------------------------------------------
# Endpoint + feature tests
# ---------------------------------------------------------------------------


def test_health(client: httpx.Client, suite: Suite) -> None:
    print("\n== Health ==")

    def root() -> str:
        r = client.get("/")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "message" in body and "docs" in body
        return body.get("version", "")

    def health() -> str:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        return "ok"

    def openapi() -> str:
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        assert len(paths) >= 10
        return f"{len(paths)} paths"

    def swagger_docs() -> str:
        r = client.get("/docs")
        assert r.status_code == 200
        assert "swagger" in r.text.lower() or "openapi" in r.text.lower()
        return "docs available"

    def auth_health() -> str:
        r = client.get(f"{API}/auth/health")
        assert r.status_code == 200
        assert "healthy" in r.json()["message"].lower()
        return r.json()["message"]

    for name, fn in [
        ("GET /", root),
        ("GET /health", health),
        ("GET /openapi.json (Swagger schema)", openapi),
        ("GET /docs (Swagger UI)", swagger_docs),
        ("GET /api/v1/auth/health", auth_health),
    ]:
        run_case(suite, name, fn)


def test_auth(client: httpx.Client, suite: Suite) -> str:
    print("\n== Authentication ==")
    unique = uuid.uuid4().hex[:8]
    email = f"e2e_{unique}@eatech.com"
    password = "TestPass@12345"
    token_holder: dict[str, str] = {}

    def register() -> str:
        r = client.post(
            f"{API}/auth/register",
            json={"name": "E2E Tester", "email": email, "password": password},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == email
        return body["id"]

    def register_duplicate() -> str:
        r = client.post(
            f"{API}/auth/register",
            json={"name": "E2E Tester", "email": email, "password": password},
        )
        assert r.status_code == 409, r.text
        return "conflict expected"

    def login_bad() -> str:
        r = client.post(
            f"{API}/auth/login",
            json={"email": email, "password": "WrongPass999"},
        )
        assert r.status_code == 401, r.text
        return "unauthorized expected"

    def login_ok() -> str:
        r = client.post(
            f"{API}/auth/login",
            json={"email": email, "password": password},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("access_token")
        assert body.get("token_type") == "bearer"
        token_holder["user"] = body["access_token"]
        return "jwt issued"

    def admin_login() -> str:
        r = client.post(
            f"{API}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert r.status_code == 200, r.text
        token_holder["admin"] = r.json()["access_token"]
        return "admin jwt"

    def protected_without_token() -> str:
        r = client.get(f"{API}/rules")
        assert r.status_code in {401, 403}, r.text
        return f"status={r.status_code}"

    def google_unconfigured_or_invalid() -> str:
        r = client.post(f"{API}/auth/google", json={"id_token": "x" * 40})
        # 503 if GOOGLE_CLIENT_ID empty, 401 if configured but token invalid
        assert r.status_code in {401, 503}, r.text
        return f"status={r.status_code}"

    for name, fn in [
        ("POST /auth/register", register),
        ("POST /auth/register duplicate -> 409", register_duplicate),
        ("POST /auth/login invalid -> 401", login_bad),
        ("POST /auth/login success -> JWT", login_ok),
        ("POST /auth/login seeded admin", admin_login),
        ("Protected /rules without JWT -> 401/403", protected_without_token),
        ("POST /auth/google without valid token", google_unconfigured_or_invalid),
    ]:
        run_case(suite, name, fn)

    assert "admin" in token_holder, "admin login failed — cannot continue"
    return token_holder["admin"]


def test_metadata(client: httpx.Client, suite: Suite) -> dict[str, Any]:
    print("\n== Metadata (dynamic dropdowns) ==")
    meta: dict[str, Any] = {}

    def types() -> str:
        r = client.get(f"{API}/types")
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1
        assert any(t["key"] == "contact" for t in items)
        meta["types"] = items
        return f"{len(items)} types"

    def fields() -> str:
        r = client.get(f"{API}/fields/contact")
        assert r.status_code == 200, r.text
        items = r.json()
        assert len(items) >= 10
        keys = {f["key"] for f in items}
        for required in ("company", "industry", "job_title", "source", "status"):
            assert required in keys, f"missing field {required}"
            field = next(f for f in items if f["key"] == required)
            assert field["operators"], f"no operators for {required}"
            assert field["value_source"] in {"distinct", "free_text"}
        meta["fields"] = items
        return f"{len(items)} fields"

    def fields_404() -> str:
        r = client.get(f"{API}/fields/does-not-exist")
        assert r.status_code == 404
        return "not found"

    def values_company() -> str:
        r = client.get(f"{API}/values/company", params={"type_key": "contact"})
        assert r.status_code == 200, r.text
        values = r.json()
        assert isinstance(values, list) and len(values) >= 1
        meta["company_values"] = values
        return f"{len(values)} values"

    def values_search() -> str:
        r = client.get(
            f"{API}/values/company",
            params={"type_key": "contact", "search": "INFO", "limit": 20},
        )
        assert r.status_code == 200, r.text
        values = r.json()
        assert all("info" in v.lower() for v in values)
        return f"{len(values)} filtered"

    def values_404() -> str:
        r = client.get(f"{API}/values/nope", params={"type_key": "contact"})
        assert r.status_code == 404
        return "not found"

    def operators() -> str:
        r = client.get(f"{API}/operators")
        assert r.status_code == 200, r.text
        items = r.json()
        keys = {o["key"] for o in items}
        for op in ("=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN", ">", "<"):
            assert op in keys, f"missing operator {op}"
        meta["operators"] = items
        return f"{len(items)} operators"

    for name, fn in [
        ("GET /types", types),
        ("GET /fields/contact", fields),
        ("GET /fields/{bad} -> 404", fields_404),
        ("GET /values/company (Mongo distinct)", values_company),
        ("GET /values/company?search=", values_search),
        ("GET /values/{bad} -> 404", values_404),
        ("GET /operators", operators),
    ]:
        run_case(suite, name, fn)

    return meta


def test_rules_flow(client: httpx.Client, suite: Suite, token: str) -> str:
    print("\n== Rules (preview / save / list / update / delete) ==")
    headers = auth_headers(token)
    rule_id_holder: dict[str, str] = {}
    template_id_holder: dict[str, str] = {}
    marker = uuid.uuid4().hex[:8]

    def preview_valid() -> str:
        r = client.post(f"{API}/rules/preview", json={"rules": sample_rules()})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_valid"] is True
        assert body["query_text"]
        assert "group" in body["query_json"] or isinstance(body["query_json"], dict)
        assert "company" in body["query_text"].lower() or "INFOTREE" in body["query_text"]
        return body["query_text"][:80]

    def preview_invalid_empty() -> str:
        r = client.post(f"{API}/rules/preview", json={"rules": []})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_valid"] is False
        assert body["errors"]
        return str(body["errors"][0])

    def preview_unbalanced() -> str:
        rules = sample_rules(nested=False)
        rules[0]["group_start"] = 2
        rules[0]["group_end"] = 0
        r = client.post(f"{API}/rules/preview", json={"rules": rules})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_valid"] is False
        return ",".join(body["errors"])[:100]

    def preview_or_logic() -> str:
        rules = [
            {
                "id": "1",
                "type": "contact",
                "field": "status",
                "operator": "=",
                "value": "Active",
                "next_operator": "OR",
                "group_start": 0,
                "group_end": 0,
            },
            {
                "id": "2",
                "type": "contact",
                "field": "status",
                "operator": "=",
                "value": "Inactive",
                "next_operator": "END",
                "group_start": 0,
                "group_end": 0,
            },
        ]
        r = client.post(f"{API}/rules/preview", json={"rules": rules})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_valid"] is True
        assert "OR" in body["query_text"].upper()
        return body["query_text"][:80]

    def save_rule() -> str:
        r = client.post(
            f"{API}/rules/save",
            headers=headers,
            json={
                "name": f"E2E Rule {marker}",
                "description": "Automation saved rule",
                "rules": sample_rules(),
                "is_template": False,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        rule_id_holder["id"] = body["id"]
        assert body["name"] == f"E2E Rule {marker}"
        assert body["is_template"] is False
        return body["id"]

    def save_template() -> str:
        r = client.post(
            f"{API}/rules/save",
            headers=headers,
            json={
                "name": f"E2E Template {marker}",
                "description": "Automation template",
                "rules": sample_rules(),
                "is_template": True,
            },
        )
        assert r.status_code == 201, r.text
        template_id_holder["id"] = r.json()["id"]
        assert r.json()["is_template"] is True
        return template_id_holder["id"]

    def save_invalid() -> str:
        rules = sample_rules(nested=False)
        rules[0]["group_start"] = 3
        r = client.post(
            f"{API}/rules/save",
            headers=headers,
            json={"name": "Bad", "rules": rules, "is_template": False},
        )
        assert r.status_code == 422, r.text
        return "validation blocked"

    def list_rules() -> str:
        r = client.get(f"{API}/rules", headers=headers, params={"page": 1, "page_size": 10})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "total" in body and "total_pages" in body
        assert body["page"] == 1
        assert any(item["id"] == rule_id_holder["id"] for item in body["items"])
        return f"total={body['total']}"

    def search_rules() -> str:
        r = client.get(
            f"{API}/rules",
            headers=headers,
            params={"search": marker, "page": 1, "page_size": 10},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 1
        assert all(marker in (item["name"] + (item.get("description") or "")) for item in body["items"])
        return f"matched={body['total']}"

    def templates_only() -> str:
        r = client.get(
            f"{API}/rules",
            headers=headers,
            params={"templates_only": True, "page": 1, "page_size": 50},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert all(item["is_template"] for item in body["items"])
        assert any(item["id"] == template_id_holder["id"] for item in body["items"])
        return f"templates={body['total']}"

    def get_rule() -> str:
        rid = rule_id_holder["id"]
        r = client.get(f"{API}/rules/{rid}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["id"] == rid
        return rid

    def get_missing() -> str:
        r = client.get(f"{API}/rules/{uuid.uuid4()}", headers=headers)
        assert r.status_code == 404
        return "not found"

    def update_rule() -> str:
        rid = rule_id_holder["id"]
        r = client.put(
            f"{API}/rules/{rid}",
            headers=headers,
            json={
                "name": f"E2E Rule Updated {marker}",
                "description": "Updated by automation",
                "is_template": True,
                "rules": sample_rules(company="INFOTREE", nested=True),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"].endswith(marker)
        assert body["is_template"] is True
        return "updated"

    def delete_rule() -> str:
        rid = rule_id_holder["id"]
        r = client.delete(f"{API}/rules/{rid}", headers=headers)
        assert r.status_code == 200, r.text
        assert "deleted" in r.json()["message"].lower()
        # confirm gone
        r2 = client.get(f"{API}/rules/{rid}", headers=headers)
        assert r2.status_code == 404
        return "deleted"

    def delete_template() -> str:
        rid = template_id_holder["id"]
        r = client.delete(f"{API}/rules/{rid}", headers=headers)
        assert r.status_code == 200, r.text
        return "template deleted"

    for name, fn in [
        ("POST /rules/preview valid nested", preview_valid),
        ("POST /rules/preview empty -> invalid", preview_invalid_empty),
        ("POST /rules/preview unbalanced groups", preview_unbalanced),
        ("POST /rules/preview AND/OR logic", preview_or_logic),
        ("POST /rules/save", save_rule),
        ("POST /rules/save template", save_template),
        ("POST /rules/save invalid -> 422", save_invalid),
        ("GET /rules pagination", list_rules),
        ("GET /rules?search= (rule search)", search_rules),
        ("GET /rules?templates_only=true", templates_only),
        ("GET /rules/{id}", get_rule),
        ("GET /rules/{missing} -> 404", get_missing),
        ("PUT /rules/{id} (rule editing)", update_rule),
        ("DELETE /rules/{id}", delete_rule),
        ("DELETE /rules/{template}", delete_template),
    ]:
        run_case(suite, name, fn)

    return marker


def test_contacts(client: httpx.Client, suite: Suite, token: str, meta: dict[str, Any]) -> None:
    print("\n== Contacts (list / search / filter) ==")
    headers = auth_headers(token)
    company_values = meta.get("company_values") or []
    company = company_values[0] if company_values else "INFOTREE"

    def list_contacts() -> str:
        r = client.get(
            f"{API}/contacts",
            headers=headers,
            params={"page": 1, "page_size": 10},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 1
        assert len(body["items"]) <= 10
        assert body["page"] == 1
        # expect ~200 sample contacts
        assert body["total"] >= 50, f"expected seeded dataset, got total={body['total']}"
        return f"total={body['total']}"

    def pagination() -> str:
        r1 = client.get(f"{API}/contacts", headers=headers, params={"page": 1, "page_size": 5})
        r2 = client.get(f"{API}/contacts", headers=headers, params={"page": 2, "page_size": 5})
        assert r1.status_code == 200 and r2.status_code == 200
        ids1 = [c["id"] for c in r1.json()["items"]]
        ids2 = [c["id"] for c in r2.json()["items"]]
        assert ids1 and ids2
        assert set(ids1).isdisjoint(set(ids2))
        return f"page1={ids1} page2={ids2}"

    def search() -> str:
        r = client.get(
            f"{API}/contacts",
            headers=headers,
            params={"search": company[:4], "page": 1, "page_size": 20},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 0
        return f"search_total={body['total']}"

    def filter_equals() -> str:
        rules = sample_rules(company=company, nested=False)
        r = client.post(
            f"{API}/contacts/filter",
            headers=headers,
            params={"page": 1, "page_size": 20},
            json={"rules": rules},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 1
        assert all(item.get("company") == company for item in body["items"])
        return f"matched={body['total']} company={company}"

    def filter_nested() -> str:
        rules = sample_rules(company=company, nested=True)
        # industry may not match Software for every company — still must return 200 + valid shape
        r = client.post(
            f"{API}/contacts/filter",
            headers=headers,
            params={"page": 1, "page_size": 20},
            json={"rules": rules},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "total" in body
        return f"nested_matched={body['total']}"

    def filter_like() -> str:
        rules = [
            {
                "id": "like-1",
                "type": "contact",
                "field": "company",
                "operator": "LIKE",
                "value": company[:3],
                "next_operator": "END",
                "group_start": 0,
                "group_end": 0,
            }
        ]
        r = client.post(
            f"{API}/contacts/filter",
            headers=headers,
            params={"page": 1, "page_size": 10},
            json={"rules": rules},
        )
        assert r.status_code == 200, r.text
        return f"like_matched={r.json()['total']}"

    def filter_invalid() -> str:
        rules = sample_rules(nested=False)
        rules[0]["group_start"] = 5
        r = client.post(
            f"{API}/contacts/filter",
            headers=headers,
            json={"rules": rules},
        )
        assert r.status_code == 422, r.text
        return "validation blocked"

    def unauthorized() -> str:
        r = client.get(f"{API}/contacts")
        assert r.status_code in {401, 403}
        return f"status={r.status_code}"

    for name, fn in [
        ("GET /contacts list + seed size", list_contacts),
        ("GET /contacts pagination", pagination),
        ("GET /contacts?search=", search),
        ("POST /contacts/filter equals", filter_equals),
        ("POST /contacts/filter nested groups", filter_nested),
        ("POST /contacts/filter LIKE", filter_like),
        ("POST /contacts/filter invalid -> 422", filter_invalid),
        ("GET /contacts without JWT -> 401/403", unauthorized),
    ]:
        run_case(suite, name, fn)


def test_end_to_end_builder_flow(client: httpx.Client, suite: Suite, token: str) -> None:
    print("\n== End-to-end builder flow ==")
    headers = auth_headers(token)

    def full_flow() -> str:
        # 1 metadata cascade
        types = client.get(f"{API}/types").json()
        assert types
        type_key = types[0]["key"]
        fields = client.get(f"{API}/fields/{type_key}").json()
        field = next(f for f in fields if f["value_source"] == "distinct")
        values = client.get(
            f"{API}/values/{field['key']}",
            params={"type_key": type_key},
        ).json()
        assert values
        operators = client.get(f"{API}/operators").json()
        assert any(op["key"] in field["operators"] for op in operators)

        # 2 build rule using first distinct value
        rules = [
            {
                "id": str(uuid.uuid4()),
                "type": type_key,
                "field": field["key"],
                "operator": "=",
                "value": values[0],
                "next_operator": "END",
                "group_start": 0,
                "group_end": 0,
            }
        ]

        # 3 live preview
        preview = client.post(f"{API}/rules/preview", json={"rules": rules})
        assert preview.status_code == 200
        assert preview.json()["is_valid"] is True

        # 4 save
        name = f"E2E Flow {uuid.uuid4().hex[:6]}"
        saved = client.post(
            f"{API}/rules/save",
            headers=headers,
            json={"name": name, "rules": rules, "is_template": True, "description": "e2e"},
        )
        assert saved.status_code == 201, saved.text
        rid = saved.json()["id"]

        # 5 apply to contacts
        filtered = client.post(
            f"{API}/contacts/filter",
            headers=headers,
            params={"page": 1, "page_size": 5},
            json={"rules": rules},
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] >= 1

        # 6 edit + reload
        updated = client.put(
            f"{API}/rules/{rid}",
            headers=headers,
            json={"name": name + " edited"},
        )
        assert updated.status_code == 200
        listed = client.get(
            f"{API}/rules",
            headers=headers,
            params={"search": "edited", "templates_only": True},
        )
        assert listed.status_code == 200
        assert any(i["id"] == rid for i in listed.json()["items"])

        # 7 cleanup
        deleted = client.delete(f"{API}/rules/{rid}", headers=headers)
        assert deleted.status_code == 200
        return f"field={field['key']} value={values[0]} matched={filtered.json()['total']}"

    run_case(suite, "E2E: type->field->value->preview->save->filter->edit->delete", full_flow)


# ---------------------------------------------------------------------------
# Assignment requirement checks (static + frontend)
# ---------------------------------------------------------------------------


def test_requirements(suite: Suite) -> None:
    print("\n== Assignment requirements (static) ==")

    def path_exists(rel: str) -> bool:
        return (ROOT / rel).exists() or (BACKEND / rel).exists() or (FRONTEND / rel).exists()

    checks: list[tuple[str, bool, str]] = []

    # Stack / structure
    checks.append(("Backend FastAPI app present", (BACKEND / "app" / "main.py").exists(), ""))
    checks.append(("API layer separation (app/api)", (BACKEND / "app" / "api").is_dir(), ""))
    checks.append(("Frontend React src present", (FRONTEND / "src").is_dir(), ""))
    checks.append(("Reusable UI components folder", (FRONTEND / "src" / "components" / "ui").is_dir(), ""))
    checks.append(("Rule-builder components folder", (FRONTEND / "src" / "components" / "rule-builder").is_dir(), ""))

    # Multilingual JSON content
    for lang in ("en", "hi", "or"):
        p = FRONTEND / "src" / "content" / f"{lang}.json"
        checks.append((f"i18n content {lang}.json", p.exists(), str(p)))

    # Theme config file (not hardcoded only in CSS)
    theme = FRONTEND / "src" / "content" / "theme.json"
    checks.append(("Theme tokens in theme.json", theme.exists(), str(theme)))

    # Dark mode support in content
    en = json.loads((FRONTEND / "src" / "content" / "en.json").read_text(encoding="utf-8"))
    checks.append(("Dark mode string in i18n", "darkMode" in en.get("common", {}), ""))

    # Bonus: unit tests, docker, jwt deps
    checks.append(("Unit tests present", (BACKEND / "tests" / "test_rule_engine.py").exists(), ""))
    docker_files = list(BACKEND.glob("Dockerfile*")) + list(BACKEND.glob("docker-compose*")) + list(ROOT.glob("docker-compose*"))
    checks.append(("Docker support files", len(docker_files) > 0, str([str(p) for p in docker_files])))

    reqs = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    checks.append(("JWT dependency (python-jose)", "python-jose" in reqs, ""))
    checks.append(("httpx available for API tests", "httpx" in reqs, ""))

    # File line budget (~500) — sample critical files
    over_limit: list[str] = []
    for path in [
        FRONTEND / "src" / "pages" / "BuilderPage.tsx",
        BACKEND / "app" / "api" / "rules.py",
        BACKEND / "app" / "api" / "contacts.py",
        BACKEND / "app" / "services" / "rule_engine.py",
    ]:
        if path.exists():
            lines = len(path.read_text(encoding="utf-8").splitlines())
            if lines > 500:
                over_limit.append(f"{path.name}:{lines}")
    checks.append(("Key files ≤ ~500 lines", len(over_limit) == 0, ", ".join(over_limit) or "ok"))

    # i18n key parity
    hi = json.loads((FRONTEND / "src" / "content" / "hi.json").read_text(encoding="utf-8"))
    or_ = json.loads((FRONTEND / "src" / "content" / "or.json").read_text(encoding="utf-8"))

    def flatten(obj: Any, prefix: str = "") -> list[str]:
        keys: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.extend(flatten(v, f"{prefix}.{k}" if prefix else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                keys.extend(flatten(v, f"{prefix}[{i}]"))
        else:
            keys.append(prefix)
        return keys

    en_keys = set(flatten(en))
    hi_keys = set(flatten(hi))
    or_keys = set(flatten(or_))
    checks.append(("i18n key parity EN/HI", en_keys == hi_keys, f"miss={len(en_keys-hi_keys)} extra={len(hi_keys-en_keys)}"))
    checks.append(("i18n key parity EN/OR", en_keys == or_keys, f"miss={len(en_keys-or_keys)} extra={len(or_keys-en_keys)}"))

    # Required feature strings / sections
    for section in ("builder", "saved", "contacts", "home", "dashboard", "logic", "meta"):
        checks.append((f"i18n section '{section}'", section in en, ""))

    # Frontend pages for routes
    for page in ("BuilderPage.tsx", "SavedRulesPage.tsx", "ContactsPage.tsx", "LoginPage.tsx", "HomePage.tsx"):
        checks.append((f"Frontend page {page}", (FRONTEND / "src" / "pages" / page).exists(), ""))

    # Bonus feature components
    checks.append(
        ("Rule edit/reorder components", (FRONTEND / "src" / "components" / "rule-builder" / "RuleRow.tsx").exists(), ""),
    )
    checks.append(
        ("Pagination component", (FRONTEND / "src" / "components" / "ui" / "Pagination.tsx").exists(), ""),
    )
    checks.append(
        ("LanguageSwitcher component", (FRONTEND / "src" / "components" / "layout" / "LanguageSwitcher.tsx").exists(), ""),
    )

    for name, ok, detail in checks:
        suite.check(name, ok, detail)


def test_frontend_smoke(suite: Suite) -> None:
    print("\n== Frontend smoke ==")
    try:
        with httpx.Client(base_url=FRONTEND_URL, timeout=10.0) as fe:
            def home() -> str:
                r = fe.get("/")
                assert r.status_code == 200
                assert "html" in r.headers.get("content-type", "").lower()
                return "ok"

            def login_route() -> str:
                r = fe.get("/login")
                assert r.status_code == 200
                return "ok"

            for name, fn in [
                ("GET frontend /", home),
                ("GET frontend /login", login_route),
            ]:
                run_case(suite, name, fn)
    except Exception as exc:  # noqa: BLE001
        suite.add(Result(name="Frontend reachable", ok=False, detail=str(exc)))


def test_unit_tests(suite: Suite) -> None:
    print("\n== Backend unit tests ==")

    def pytest_rule_engine() -> str:
        import subprocess

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_rule_engine.py", "-q"],
            cwd=str(BACKEND),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stdout + "\n" + proc.stderr)
        return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "passed"

    run_case(suite, "pytest tests/test_rule_engine.py", pytest_rule_engine)


def print_summary(suite: Suite) -> int:
    print("\n" + "=" * 64)
    print(f"RESULTS: {suite.passed} passed, {suite.failed} failed, {len(suite.results)} total")
    print("=" * 64)
    if suite.failed:
        print("\nFailed cases:")
        for r in suite.results:
            if not r.ok:
                print(f"  - {r.name}: {r.detail}")
    return 1 if suite.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E automation for Dynamic Rule Builder")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-unit", action="store_true")
    parser.add_argument("--report", default="", help="Optional JSON report path")
    args = parser.parse_args()

    suite = Suite()
    print(f"Base URL: {args.base_url}")
    print(f"Admin: {ADMIN_EMAIL}")

    try:
        with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
            # connectivity
            try:
                client.get("/health").raise_for_status()
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: backend not reachable at {args.base_url}: {exc}")
                return 2

            test_health(client, suite)
            token = test_auth(client, suite)
            meta = test_metadata(client, suite)
            test_rules_flow(client, suite, token)
            test_contacts(client, suite, token, meta)
            test_end_to_end_builder_flow(client, suite, token)
    except Exception:
        traceback.print_exc()
        return 2

    test_requirements(suite)
    if not args.skip_frontend:
        test_frontend_smoke(suite)
    if not args.skip_unit:
        test_unit_tests(suite)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "passed": suite.passed,
            "failed": suite.failed,
            "total": len(suite.results),
            "results": [
                {"name": r.name, "ok": r.ok, "detail": r.detail, "duration_ms": r.duration_ms}
                for r in suite.results
            ],
        }
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nReport written to {report_path}")

    return print_summary(suite)


if __name__ == "__main__":
    raise SystemExit(main())
