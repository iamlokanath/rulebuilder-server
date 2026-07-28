"""Seed MongoDB collections from the provided Excel/JSON dataset."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402

DATA_DIR = ROOT / "data"

CONTACT_FIELD_MAP = {
    "ID": "id",
    "First Name": "first_name",
    "Last Name": "last_name",
    "Company": "company",
    "Industry": "industry",
    "Job Title": "job_title",
    "Department": "department",
    "Language": "language",
    "Country": "country",
    "State": "state",
    "City": "city",
    "Source": "source",
    "Status": "status",
    "Email": "email",
    "Created Date": "created_date",
}

FIELD_DEFINITIONS = [
    {
        "key": "company",
        "label": "Company",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "industry",
        "label": "Industry",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "job_title",
        "label": "Job Title",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "department",
        "label": "Department",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "language",
        "label": "Language",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "country",
        "label": "Country",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "state",
        "label": "State",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "city",
        "label": "City",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "source",
        "label": "Source",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "status",
        "label": "Status",
        "data_type": "string",
        "value_source": "distinct",
        "operators": ["=", "!=", "LIKE", "NOT LIKE", "IN", "NOT IN"],
    },
    {
        "key": "first_name",
        "label": "First Name",
        "data_type": "string",
        "value_source": "free_text",
        "operators": ["=", "!=", "LIKE", "NOT LIKE"],
    },
    {
        "key": "last_name",
        "label": "Last Name",
        "data_type": "string",
        "value_source": "free_text",
        "operators": ["=", "!=", "LIKE", "NOT LIKE"],
    },
    {
        "key": "email",
        "label": "Email",
        "data_type": "string",
        "value_source": "free_text",
        "operators": ["=", "!=", "LIKE", "NOT LIKE"],
    },
    {
        "key": "created_date",
        "label": "Created Date",
        "data_type": "date",
        "value_source": "free_text",
        "operators": ["=", "!=", ">", "<", ">=", "<="],
    },
]


def load_contacts() -> list[dict]:
    path = DATA_DIR / "contacts.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    contacts = []
    for row in raw:
        contact = {
            CONTACT_FIELD_MAP[key]: value
            for key, value in row.items()
            if key in CONTACT_FIELD_MAP
        }
        contact["_id"] = str(contact["id"])
        contacts.append(contact)
    return contacts


async def seed() -> None:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db]

    await db.contacts.delete_many({})
    await db.type_master.delete_many({})
    await db.field_master.delete_many({})
    await db.users.delete_many({})
    await db.saved_rules.delete_many({})

    contacts = load_contacts()
    if contacts:
        await db.contacts.insert_many(contacts)

    await db.type_master.insert_one(
        {
            "_id": "contact",
            "key": "contact",
            "label": "Contact",
            "collection": "contacts",
        }
    )

    field_docs = [
        {
            "_id": f"contact_{field['key']}",
            "type_key": "contact",
            **field,
        }
        for field in FIELD_DEFINITIONS
    ]
    await db.field_master.insert_many(field_docs)

    admin = {
        "_id": str(uuid4()),
        "name": settings.seed_admin_name,
        "email": settings.seed_admin_email.lower(),
        "password_hash": hash_password(settings.seed_admin_password),
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(admin)

    await db.contacts.create_index("company")
    await db.contacts.create_index("industry")
    await db.contacts.create_index("job_title")
    await db.contacts.create_index("email")
    await db.saved_rules.create_index([("created_by", 1), ("updated_at", -1)])
    await db.users.create_index("email", unique=True)

    # Export dataset snapshot for deliverable
    export_dir = DATA_DIR / "mongo"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "contacts.json").write_text(
        json.dumps(contacts, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (export_dir / "type_master.json").write_text(
        json.dumps(
            [{"key": "contact", "label": "Contact", "collection": "contacts"}],
            indent=2,
        ),
        encoding="utf-8",
    )
    (export_dir / "field_master.json").write_text(
        json.dumps(field_docs, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Seeded {len(contacts)} contacts into '{settings.mongodb_db}'")
    print(f"Admin user: {settings.seed_admin_email}")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
