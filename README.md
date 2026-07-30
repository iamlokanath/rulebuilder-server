# RuleBuilder Server

Backend API for **RuleBuilder** — a Dynamic Nested Rule Builder.

Users create nested filter rules (Type / Field / Operator / Value / AND-OR-END), preview readable + JSON queries, save templates, and filter a MongoDB contact dataset.

**Pair UI repo:** `rulebuilder-ui` (React + Vite + TypeScript)

---

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.12+) |
| Database | MongoDB (Motor async driver) |
| Auth | JWT (email/password) + Google OAuth ID token |
| Docs | Swagger `/docs`, ReDoc `/redoc` |
| Tests | pytest + e2e automation script |
| Deploy | Docker + Docker Compose |

---

## Features

- JWT register / login
- Google Sign-In (`POST /auth/google`)
- Dynamic metadata APIs (types, fields, distinct values, operators)
- Nested rule validation (`group_start` / `group_end`)
- Live rule preview (readable query + JSON)
- Save / list / search / paginate / update / delete rules
- Rule templates
- Contact list + search + pagination
- Filter contacts using rule payload (`$and` / `$or` / `LIKE` / `IN`, etc.)
- Seed script for ~200 sample contacts + field/type masters
- Unit tests for rule engine
- End-to-end API automation script
- Dockerized API + MongoDB

---

## Project structure

```text
rulebuilder-server/
├── app/
│   ├── api/                 # Route modules
│   │   ├── auth.py
│   │   ├── metadata.py
│   │   ├── rules.py
│   │   └── contacts.py
│   ├── core/                # Config, DB, JWT, deps
│   ├── schemas/             # Pydantic models
│   ├── services/
│   │   └── rule_engine.py   # Validation + query builders
│   └── main.py
├── data/                    # Sample dataset (JSON + Excel)
├── scripts/
│   ├── seed_db.py
│   ├── e2e_automation.py
│   └── seed_e2e_tester_rules.py
├── tests/
│   └── test_rule_engine.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Quick start (local)

### 1. Prerequisites

- Python 3.12+
- MongoDB Community Server installed ([download](https://www.mongodb.com/try/download/community))

### 2. Start MongoDB locally (Windows)

Keep this terminal open while you use the API. Data is stored in `.mongo-data/` (gitignored).

**PowerShell — from the backend folder:**

```powershell
cd "E:\Personal Projects\eatech\backend"

$dataDir = "$PWD\.mongo-data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

& "C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe" `
  --dbpath $dataDir `
  --bind_ip 127.0.0.1 `
  --port 27017
```

You should see MongoDB listening on `127.0.0.1:27017`. Leave that window running.

**Stop MongoDB:** press `Ctrl+C` in that terminal, or:

```powershell
Stop-Process -Name mongod -Force -ErrorAction SilentlyContinue
```

**Notes**

- If your install path differs, change `7.0` to your version folder under `C:\Program Files\MongoDB\Server\`.
- If Git complains about `.mongo-data` files being locked, stop MongoDB first, then discard those changes. Never commit `.mongo-data`.
- Alternative: use Docker (`docker compose up`) so Compose starts Mongo for you.

### 3. Install

```bash
cd rulebuilder-server
python -m venv .venv

# Windows PowerShell
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
# macOS/Linux: cp .env.example .env
```

### 4. Configure `.env`

At minimum set:

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=dynamic_rule_builder
JWT_SECRET_KEY=change-this-to-a-long-random-secret-key
SEED_ADMIN_EMAIL=admin@eatech.com
SEED_ADMIN_PASSWORD=Admin@12345
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
GOOGLE_CLIENT_ID=           # optional, for Google login
```

### 5. Seed database

```bash
python scripts/seed_db.py
```

This loads:

- ~200 contacts
- `type_master` / `field_master`
- seeded admin user from `.env`

### 6. Run API

```bash
uvicorn app.main:app --reload --port 8000
```

- Health: http://localhost:8000/health  
- Swagger: http://localhost:8000/docs  

**Demo login:** use `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` from `.env`

---

## Docker

```bash
docker compose up --build
docker compose exec api python scripts/seed_db.py
```

Services:

- `rulebuilder-mongo` → MongoDB on host port `27017`
- `rulebuilder-server` → API on host port `8000`

Inside Compose, the API uses `MONGODB_URI=mongodb://mongodb:27017`.

---

## API overview

Base prefix: `/api/v1`

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Create user |
| POST | `/auth/login` | No | Get JWT |
| POST | `/auth/google` | No | Login/register with Google ID token |
| GET | `/auth/health` | No | Auth module health |

### Metadata (dynamic dropdowns)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/types` | No | Entity types |
| GET | `/fields/{type_key}` | No | Fields for a type |
| GET | `/values/{field_key}?type_key=&search=` | No | Distinct Mongo values |
| GET | `/operators` | No | Supported operators |

### Rules

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/rules/preview` | No | Validate + live query preview |
| POST | `/rules/save` | JWT | Save rule set / template |
| GET | `/rules` | JWT | List (search, pagination, templates_only) |
| GET | `/rules/{id}` | JWT | Get one |
| PUT | `/rules/{id}` | JWT | Update |
| DELETE | `/rules/{id}` | JWT | Delete |

### Contacts

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/contacts` | JWT | List + search + pagination |
| POST | `/contacts/filter` | JWT | Filter by rule payload |

Protected routes require:

```http
Authorization: Bearer <access_token>
```

---

## Rule model (important)

Each rule item includes:

- `type`, `field`, `operator`, `value`
- `next_operator`: `AND` | `OR` | `END`
- `group_start` / `group_end`: nesting depth markers

Example nested preview:

```text
{company = "INFOTREE" AND industry = "Software"}
```

The rule engine:

1. Validates required fields and balanced groups
2. Builds readable query text
3. Builds structured JSON
4. Contact filter compiles rules into MongoDB operators (`$eq`, `$regex`, `$in`, `$and`, `$or`, …)

---

## Google OAuth setup

1. Create a Google Cloud **OAuth Web Client**
2. Authorized JavaScript origins:
   - `http://localhost:5173`
   - `http://127.0.0.1:5173`
3. Set the same Client ID in:
   - Server `.env` → `GOOGLE_CLIENT_ID`
   - UI `.env` → `VITE_GOOGLE_CLIENT_ID`
4. Restart API and UI

---

## Tests

### Unit tests

```bash
pytest
# or
pytest tests/test_rule_engine.py -q
```

### E2E API automation

With the API running on `:8000`:

```bash
python scripts/e2e_automation.py
python scripts/e2e_automation.py --report scripts/e2e_report.json
```

Covers auth, metadata, nested preview, save/list/update/delete, contact filter, JWT guards, and requirement checks.

---

## MongoDB collections

| Collection | Purpose |
|---|---|
| `users` | Registered / Google users |
| `contacts` | Sample contact dataset |
| `type_master` | Entity types |
| `field_master` | Field metadata + operators |
| `saved_rules` | User-saved rules and templates |

Seed data lives under `data/` (`contacts.json`, Excel sample, mongo snapshots).

---

## Environment variables

Copy from `.env.example`:

| Variable | Description |
|---|---|
| `APP_NAME` | API title |
| `APP_VERSION` | Version string |
| `APP_ENV` | Environment name |
| `DEBUG` | Debug flag |
| `API_PREFIX` | Default `/api/v1` |
| `CORS_ORIGINS` | Comma-separated UI origins |
| `MONGODB_URI` | Mongo connection string |
| `MONGODB_DB` | Database name |
| `JWT_SECRET_KEY` | JWT signing secret |
| `JWT_ALGORITHM` | Default `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime |
| `SEED_ADMIN_EMAIL` | Seeded login email |
| `SEED_ADMIN_PASSWORD` | Seeded login password |
| `SEED_ADMIN_NAME` | Seeded display name |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |

**Never commit `.env`.** Keep secrets only in local env / deployment secrets.

---

## Related UI

Frontend repository: **rulebuilder-ui**

Default UI URL: http://localhost:5173  
Default API URL used by UI: `http://localhost:8000/api/v1`

---

## Author

**Lokanath Panda**  
Portfolio: https://lokanathpanda7.netlify.app/  
GitHub: https://github.com/iamlokanath  
LinkedIn: https://www.linkedin.com/in/lokanath-panda-642193238/
