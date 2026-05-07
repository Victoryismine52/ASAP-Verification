# ASAP Verification Console

FastAPI-based insurance eligibility and benefits verification workbench for demoing a standalone verification layer. The app supports CSV/manual/demo-data intake, a reviewable work queue, request history, outbox staging for future EHR integration, and a pluggable provider-adapter pattern.

The current demo branch includes:

- mock adapter for local development and controlled workflow scenarios
- Availity adapter using OAuth client credentials and `/v1/coverages`
- Stedi adapter using API-key auth and Stedi's JSON eligibility endpoint
- scaffolded future-provider candidates for Optum/Change, CMS HETS, and state Medicaid
- API Factory Demo tab for walking records through preview → send → response → history → outbox

> Default mode is **mock**. Availity and Stedi require local credentials/API keys. No real credentials are committed to the repository.

---

## Quick Start

### Run with Docker Compose (recommended)

```bash
# 1. Copy the example env file
cp .env.example .env

# 2. Optional: paste local demo credentials into .env
# STEDI_API_KEY=...
# AVAILITY_CLIENT_ID=...
# AVAILITY_CLIENT_SECRET=...

# 3. Start the service (hot-reload enabled)
docker compose up --build
```

The API is available at **http://localhost:8000**  
Operations console: **http://localhost:8000/**  
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

Use Python 3.12 for local/Codex test environments. Some pinned dependencies, especially `pydantic-core`, may fail to build on newer unreleased Python versions.

---

## Demo Flow

The easiest path for a live demo is the **API Factory Demo** tab.

1. Copy `.env.example` to `.env` and add any local provider credentials.
2. Start the app with Docker Compose.
3. Open the operations console.
4. Go to **API Factory Demo**.
5. Select a verification source and click **Set Source**.
6. Click **Load Unknown Demo Patients**.
7. Preview a row's JSON payload.
8. Send one row or run all pending rows.
9. View the response payload in the modal.
10. Open Request History / Outbox to show persisted results and downstream staging.

Provider-specific demo rows can carry a `preferred_provider`, so a Stedi demo patient routes to Stedi even if the global source selector is set to another provider.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness probe |
| `GET`  | `/` | Operations console UI |
| `GET`  | `/ui/connections` | Available provider connections |
| `POST` | `/ui/select-connection` | Select active provider |
| `GET`  | `/ui/connection-details` | Current provider diagnostic details |
| `GET`  | `/ui/connection-status` | Current provider connection/configuration status |
| `POST` | `/ui/test-call` | Run a manual eligibility test call |
| `POST` | `/eligibility/check` | Run an eligibility check |
| `GET`  | `/work-items` | Work queue records |
| `POST` | `/work-items/import.csv` | Import CSV rows into the work queue |
| `POST` | `/work-items/validate-pending` | Validate pending work queue rows |
| `POST` | `/work-items/{id}/validate` | Validate a single work queue row |
| `GET`  | `/history` | Request history |
| `GET`  | `/history/{request_id}` | Request/result detail with raw payloads |
| `POST` | `/history/{request_id}/rerun` | Rerun a saved request |
| `GET`  | `/outbox` | Downstream integration staging queue |
| `GET`  | `/exports/factory/results.csv` | Factory demo export including payload/response data |
| `GET`  | `/exports/nextgen/eligibility-results.csv` | Normalized NextGen-adjacent eligibility CSV |
| `GET`  | `/docs` | Swagger UI |
| `GET`  | `/redoc` | ReDoc UI |

---

## Example: POST /eligibility/check

**Request body**

```json
{
  "patient": {
    "first_name": "Jane",
    "last_name": "Doe",
    "dob": "1900-01-01",
    "member_id": "123456789"
  },
  "payer": {
    "name": "AHS",
    "payer_id": "AHS"
  },
  "provider": {
    "npi": "1999999984",
    "tax_id": ""
  },
  "service_type": "30",
  "external_patient_id": "UAA111222333"
}
```

`external_patient_id` is optional. It is especially useful for Stedi because Stedi recommends passing an external patient identifier to correlate historical eligibility checks.

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
  "checked_at": "2026-01-01T12:00:00Z",
  "raw_response_json": null,
  "error_message": null
}
```

---

## Configuration

All configuration is done through environment variables or a local `.env` file. Use `.env.example` as the safe template. Do not commit real `.env` files.

| Variable | Default | Description |
|----------|---------|-------------|
| `ELIGIBILITY_PROVIDER` | `mock` | Adapter to use: `mock`, `availity`, `stedi`, `optum_change`, `cms_hets`, or `state_medicaid` |
| `DATABASE_URL` | `sqlite:///./data/asap_verification.db` | SQLAlchemy database URL |
| `AVAILITY_CLIENT_ID` | *(empty)* | Availity OAuth2 client ID |
| `AVAILITY_CLIENT_SECRET` | *(empty)* | Availity OAuth2 client secret |
| `AVAILITY_BASE_URL` | `https://api.availity.com` | Availity API base URL |
| `AVAILITY_SCOPE` | `healthcare-hipaa-transactions-demo` | OAuth scope(s) for token requests |
| `AVAILITY_SUBMITTER_ID` | *(empty)* | Optional Availity submitter identifier |
| `AVAILITY_PROVIDER_NPI` | *(empty)* | Optional configured provider NPI |
| `AVAILITY_PROVIDER_TAX_ID` | *(empty)* | Optional configured provider tax ID |
| `STEDI_API_KEY` | *(empty)* | Stedi API key for eligibility calls |
| `STEDI_BASE_URL` | `https://healthcare.us.stedi.com/2024-04-01` | Stedi Healthcare API base URL |
| `STEDI_PROVIDER_ORGANIZATION_NAME` | `ACME Health Services` in `.env.example` | Provider organization name used in Stedi request payloads |
| `OPTUM_CLIENT_ID` | *(empty)* | Optum/Change OAuth client ID |
| `OPTUM_CLIENT_SECRET` | *(empty)* | Optum/Change OAuth client secret |
| `OPTUM_BASE_URL` | `https://api.changehealthcare.com` | Optum/Change base URL |
| `CMS_HETS_SUBMITTER_ID` | *(empty)* | CMS HETS submitter ID |
| `CMS_HETS_PASSWORD` | *(empty)* | CMS HETS password |
| `STATE_MEDICAID_ENDPOINT` | *(empty)* | State Medicaid endpoint |
| `STATE_MEDICAID_API_KEY` | *(empty)* | State Medicaid API credential |
| `CONNECTIONS_CONFIG_PATH` | `connections.json` | Optional JSON config listing providers shown in dropdowns |

`.gitignore` ignores `.env` and `.env.*`, while allowing `.env.example`.

---

## Provider Adapter Status

| Provider | Current status | Notes |
|----------|----------------|-------|
| `mock` | Live locally | Deterministic test scenarios and workflow simulation |
| `availity` | Implemented | Uses OAuth token flow and `/v1/coverages`; access depends on configured credentials/scope |
| `stedi` | Implemented | Uses API key and `POST /change/medicalnetwork/eligibility/v3`; test keys require approved mock requests |
| `optum_change` | Scaffolded | Future enterprise clearinghouse candidate |
| `cms_hets` | Scaffolded | Future Medicare/HETS candidate |
| `state_medicaid` | Scaffolded | Future state-specific Medicaid candidate |

### Availity notes

Availity calls use the configured base URL, credentials, and scope. Demo or production access is determined by the credentials/scope/entitlements supplied by Availity.

### Stedi notes

Stedi calls use the configured Stedi API key directly in the `Authorization` header and send JSON eligibility requests to the Stedi Healthcare API. Test API keys can return real test-mode responses, including payer AAA errors. A provider response with AAA errors proves transport/provider response but does not necessarily mean the patient's insurance was validated.

---

## Operational Workflow Concepts

The app is intended to separate three concepts:

1. **API/transport status** — did a provider respond?
2. **Eligibility validation status** — did the response validate active patient coverage?
3. **Operational action state** — does staff need to fix, review, rerun, export, or stage?

Work item statuses include:

- `pending_validation`
- `needs_revalidation`
- `validated`
- `failed`
- `ready_for_review`

For the demo, a successful API response should not automatically imply `validated`. Provider responses with AAA errors, inactive coverage, or ambiguous results should land in a reviewable operational state while preserving the raw payload.

---

## Demo Data

Demo data is synthetic and flagged with `is_demo=true`.

The demo seed includes:

- pending records
- records needing revalidation
- preloaded history/outbox examples
- Availity-preferred rows
- Stedi-preferred Jane Doe sample rows
- an intentional Stedi member ID failure row that can be edited and rerun

Use:

- **Demo Data** tab for general load/delete
- **API Factory Demo** tab for step-by-step demo flow

---

## Persistence and Operational History

The service persists operational request/response records using SQLAlchemy.

- `DATABASE_URL` controls the database connection.
- Default: `sqlite:///./data/asap_verification.db`.
- The schema is designed to remain portable to PostgreSQL.
- Local SQLite optional-column checks handle recent demo columns such as `preferred_provider` and `external_patient_id`.

### Stored entities

- `VerificationWorkItem`
- `VerificationRequest`
- `VerificationResult`
- `IntegrationOutbox`

Every `POST /eligibility/check`, `POST /ui/test-call`, and work-item validation is saved with request metadata, raw JSON, normalized fields, status, timing, and errors where applicable.

### History APIs

- `GET /history`
- `GET /history/{request_id}`
- `POST /history/{request_id}/rerun`
- `GET /history/export.csv`

### NextGen-adjacent export workflow

Use `GET /exports/nextgen/eligibility-results.csv` to download a normalized CSV for import/review in NextGen-adjacent operational workflows.

After each successful eligibility response, an `IntegrationOutbox` row can be created with:

- `target_system = nextgen`
- `target_record_type = eligibility_result`
- `status = ready_for_review`

Direct NextGen writeback is intentionally deferred until an approved integration path and governance controls are established.

---

## Project Structure

```
app/
  main.py                         # FastAPI app and operations console UI
  config.py                       # Pydantic Settings configuration
  db.py                           # SQLAlchemy engine/session setup
  models/
    eligibility.py                # Request/response Pydantic models
    persistence.py                # SQLAlchemy persistence models
  routers/
    eligibility.py                # POST /eligibility/check route
  services/
    eligibility_service.py        # Provider orchestration layer
    persistence_service.py        # History/work queue/outbox persistence helpers
    demo_data_service.py          # Demo seed load/delete helpers
  adapters/
    base.py                       # Abstract adapter interface
    mock_adapter.py               # Local mock adapter
    availity_adapter.py           # Availity OAuth + coverages adapter
    stedi_adapter.py              # Stedi healthcare eligibility adapter
    optum_change_adapter.py       # Scaffolded future adapter
    cms_hets_adapter.py           # Scaffolded future adapter
    state_medicaid_adapter.py     # Scaffolded future adapter
  utils/
    auth.py                       # Incoming request auth placeholder
    logging.py                    # Structured logging configuration

data/
  demo_seed.json                  # Synthetic demo records/history/outbox
  stedi_mock_values.example.json  # Non-secret Stedi mock value reference

tests/
  test_*.py

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

For Codex or cached container environments, force Python 3.12 if dependency installation tries to use Python 3.14 or newer.

---

## Adding a New Provider

1. Create `app/adapters/my_provider_adapter.py` implementing `BaseEligibilityAdapter`.
2. Add the adapter builder in `app/services/eligibility_service.py`.
3. Add provider metadata to `PROVIDER_ADAPTER_MATRIX`.
4. Add safe configuration placeholders to `.env.example`.
5. Add mocked tests for request mapping, error handling, and raw response preservation.
6. Set `ELIGIBILITY_PROVIDER=my_provider` or select the provider in the UI.

---

## Codespaces / Container Persistence Notes

- SQLite writes to `./data/asap_verification.db` by default.
- `docker-compose.yml` mounts `./data:/app/data`, so DB files persist across container restarts.
- In GitHub Codespaces, this keeps verification history and work items between service restarts as long as the workspace is retained.
- For a clean demo reset in a disposable environment, delete `data/asap_verification.db` or use the Demo Data delete/reload controls.
