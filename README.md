# Eligibility Service

Production-ready FastAPI microservice for insurance eligibility and benefits
verification.  Supports a pluggable adapter pattern so that mock testing and
real Availity integration share the same interface.

> Default mode is **mock**. All non-mock adapters are scaffolded and require
> vendor/trading-partner credentials before live eligibility calls will work.

---

## Quick Start

### Run with Docker Compose (recommended)

```bash
# 1. Copy the example env file
cp .env.example .env

# 2. Start the service (hot-reload enabled)
docker compose up
```

The API is available at **http://localhost:8000**  
Landing page: **http://localhost:8000/**  
Swagger UI: **http://localhost:8000/docs**

---

### Run locally (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # edit as needed

uvicorn app.main:app --reload
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness probe |
| `GET`  | `/` | Landing page with provider selector + connection status |
| `GET`  | `/ui/connection-details` | Current provider diagnostic details (base URL, scope, mode) |
| `POST` | `/ui/test-call` | Run an eligibility test call from landing page payload |
| `GET`  | `/example_patients.csv` | Example 10-row CSV for landing-page batch demo |
| `POST` | `/eligibility/check` | Run an eligibility check |
| `GET`  | `/docs` | Swagger UI |
| `GET`  | `/redoc` | ReDoc UI |

### Example: POST /eligibility/check

**Request body**

```json
{
  "patient": {
    "first_name": "Jane",
    "last_name": "Doe",
    "dob": "1985-06-15",
    "member_id": "MBR123456"
  },
  "payer": {
    "name": "Blue Cross Blue Shield",
    "payer_id": "BCBS001"
  },
  "provider": {
    "npi": "1234567890",
    "tax_id": "12-3456789"
  },
  "service_type": "30"
}
```

**Response body (mock adapter)**

```json
{
  "status": "active",
  "plan_name": "Mock PPO Gold Plan",
  "copay": 25.0,
  "coinsurance": 0.20,
  "deductible_remaining": 750.0,
  "out_of_pocket_remaining": 2000.0,
  "authorization_required": false,
  "source": "mock",
  "checked_at": "2026-01-01T12:00:00Z"
}
```

---

## Configuration

All configuration is done through environment variables (or a `.env` file).

| Variable | Default | Description |
|----------|---------|-------------|
| `ELIGIBILITY_PROVIDER` | `mock` | Adapter to use: `mock`, `availity`, `stedi`, `optum_change`, `cms_hets`, or `state_medicaid` |
| `AVAILITY_CLIENT_ID` | *(empty)* | Availity OAuth2 client ID |
| `AVAILITY_CLIENT_SECRET` | *(empty)* | Availity OAuth2 client secret |
| `AVAILITY_BASE_URL` | `https://api.availity.com` | Availity API base URL |
| `AVAILITY_SCOPE` | `healthcare-hipaa-transactions-demo` | Space-delimited OAuth scope(s) for token requests |
| `STEDI_API_KEY` | *(empty)* | Stedi API key for 270/271 calls |
| `STEDI_BASE_URL` | `https://core.us.stedi.com` | Stedi base URL |
| `OPTUM_CLIENT_ID` | *(empty)* | Optum/Change OAuth client ID |
| `OPTUM_CLIENT_SECRET` | *(empty)* | Optum/Change OAuth client secret |
| `OPTUM_BASE_URL` | `https://api.changehealthcare.com` | Optum/Change base URL |
| `CMS_HETS_SUBMITTER_ID` | *(empty)* | CMS HETS submitter ID |
| `CMS_HETS_PASSWORD` | *(empty)* | CMS HETS password |
| `STATE_MEDICAID_ENDPOINT` | *(empty)* | State Medicaid endpoint |
| `STATE_MEDICAID_API_KEY` | *(empty)* | State Medicaid API credential |
| `CONNECTIONS_CONFIG_PATH` | `connections.json` | JSON config file listing providers shown in landing-page dropdown |

> **Note:** This service uses OAuth2 **client credentials** and sends credentials as `client_secret_post` form fields at `POST /v1/token`.
>
> **Connections config format:** `{"providers": ["mock", "availity"]}` (unknown providers are ignored).

---

## Project Structure

```
app/
  main.py                   # FastAPI app, health endpoint, startup hooks
  config.py                 # Pydantic-Settings configuration
  models/
    eligibility.py          # Request / response Pydantic models
  routers/
    eligibility.py          # POST /eligibility/check route
  services/
    eligibility_service.py  # Orchestration layer
  adapters/
    base.py                 # Abstract adapter interface
    mock_adapter.py         # Static test data adapter
    availity_adapter.py     # Availity stub (OAuth2 + /v1/coverages)
  utils/
    auth.py                 # Incoming request auth placeholder
    logging.py              # Structured logging configuration

tests/
  test_health.py            # /health endpoint tests
  test_eligibility.py       # /eligibility/check tests (mock adapter)

Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

---

## Running Tests

```bash
pip install -r requirements.txt
pytest -v
```

---

## Adding a New Provider

1. Create `app/adapters/my_provider_adapter.py` implementing `BaseEligibilityAdapter`.
2. Add a branch in `app/services/eligibility_service.py → _build_adapter()`.
3. Set `ELIGIBILITY_PROVIDER=my_provider` in your `.env`.


## Multi-Source Adapter Platform

The service now exposes a provider adapter matrix on the landing page and supports selecting scaffolded adapters for:

- Availity
- Stedi
- Optum/Change Healthcare
- CMS HETS
- State Medicaid

Only `mock` is live by default. Scaffolded adapters intentionally return a safe `Not configured` eligibility response when credentials are missing, rather than raising runtime errors.

## Persistence and Operational History

The service now persists operational request/response records using SQLAlchemy.

- `DATABASE_URL` env var controls the database connection.
- Default: `sqlite:///./asap_verification.db`.
- Models are designed to be PostgreSQL-compatible (portable SQLAlchemy schema).

### Stored entities

- `VerificationRequest`
- `VerificationResult`
- `IntegrationOutbox`

Every `POST /eligibility/check` and `POST /ui/test-call` is saved with request metadata, raw JSON, normalized fields, status, timing, and errors.

### History APIs

- `GET /history`
- `GET /history/{request_id}`
- `POST /history/{request_id}/rerun`
- `GET /history/export.csv`

### NextGen export workflow

Use `GET /exports/nextgen/eligibility-results.csv` to download a normalized CSV for import/review in NextGen-adjacent operational workflows.

After each successful eligibility response, an `IntegrationOutbox` row is created with:

- `target_system = nextgen`
- `target_record_type = eligibility_result`
- `status = ready_for_review`

Direct NextGen writeback is intentionally deferred until an approved integration path and governance controls are established.
