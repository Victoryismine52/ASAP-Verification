"""
FastAPI application entry point for the eligibility-service.

Start with:
    uvicorn app.main:app --reload
or via Docker Compose:
    docker compose up
"""
import logging
import csv
import io
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pathlib import Path

from app.routers import eligibility as eligibility_router
from app.services.eligibility_service import PROVIDER_ADAPTER_MATRIX, get_available_connections, service
from app.models.eligibility import EligibilityRequest
from sqlalchemy.orm import Session
from app.db import Base, engine, get_db
from app.models.persistence import IntegrationOutbox, VerificationRequest, VerificationResult, VerificationWorkItem
from app.services.persistence_service import complete_request_error, complete_request_success, create_request_record, nextgen_csv, outbox_status_counts, upsert_work_item_from_csv_row
from app.utils.logging import configure_logging

# Configure structured logging before anything else
configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Handle application startup and shutdown events."""
    Base.metadata.create_all(bind=engine)
    logger.info("Eligibility service started.")
    yield
    logger.info("Eligibility service stopped.")


app = FastAPI(
    title="Eligibility Service",
    description=(
        "Insurance eligibility and benefits verification API. "
        "Supports mock testing and real Availity integration."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(eligibility_router.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"], summary="Health check")
async def health() -> dict:
    """Returns a simple liveness probe response."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page() -> str:
    """Simple UI for connection selection and status."""
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Eligibility Service</title>
    <style>
      body { font-family: Arial, sans-serif; max-width: 1200px; margin: 2rem auto; line-height: 1.4; }
      .card { border: 1px solid #ddd; padding: 1rem 1.25rem; border-radius: 8px; }
      .status-ok { color: #157347; }
      .status-bad { color: #842029; }
      .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
      .col { border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem; min-height: 300px; overflow: auto; }
      table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
      th, td { border: 1px solid #ddd; padding: 4px; text-align: left; }
    </style>
  </head>
  <body>
    <h1>Eligibility Service</h1>
    <div class="card">
      <label for="provider"><strong>Current Connection:</strong></label>
      <select id="provider"></select>
      <button id="switch-btn">Switch</button>
      <p id="current-provider"></p>
      <p id="status"></p>
      <pre id="details"></pre>
      <h3>Test Eligibility Call</h3>
      <p>Run a test call from this page (same backend route logic as API).</p>
      <textarea id="payload" rows="14" style="width:100%;font-family:monospace;"></textarea>
      <button id="test-btn">Run Test Call</button>
      <pre id="test-result"></pre>
      <h3>Batch CSV Demo</h3>
      <p>Upload CSV or use <code>example_patients.csv</code> to run a batch demo.</p>
      <input id="csv-file" type="file" accept=".csv" />
      <button id="load-example-btn">Load Example CSV</button>
      <button id="run-batch-btn">Run Batch Calls</button>
      <div class="grid">
        <div class="col">
          <h4>Loaded Patient Rows</h4>
          <div id="batch-patients"></div>
        </div>
        <div class="col">
          <h4>API Responses (streaming)</h4>
          <div id="batch-responses"></div>
        </div>
      </div>
      <h3>Operations</h3><p><a href="/exports/nextgen/eligibility-results.csv">Download NextGen Eligibility CSV</a></p><div id="outbox-status"></div><h4>Recent 25 Checks</h4><pre id="recent-checks"></pre><h3>Provider Adapter Matrix</h3>
      <div id="adapter-matrix"></div>
      <p><a href="/docs">Open Swagger Docs</a></p>
    </div>
    <script>
      const defaultPayload = {
        patient: { first_name: "Jane", last_name: "Doe", dob: "1985-06-15", member_id: "MBR123456" },
        payer: { name: "Blue Cross Blue Shield", payer_id: "BCBS001" },
        provider: { npi: "1234567890", tax_id: "12-3456789" },
        service_type: "30"
      };
      document.getElementById('payload').value = JSON.stringify(defaultPayload, null, 2);
      let batchRows = [];

      async function refresh() {
        const meta = await fetch('/ui/connections').then(r => r.json());
        const sel = document.getElementById('provider');
        sel.innerHTML = '';
        for (const p of meta.providers) {
          const o = document.createElement('option');
          o.value = p; o.textContent = p;
          if (p === meta.current_provider) o.selected = true;
          sel.appendChild(o);
        }
        const s = await fetch('/ui/connection-status').then(r => r.json());
        document.getElementById('current-provider').textContent = `Active provider: ${s.provider}`;
        const statusEl = document.getElementById('status');
        statusEl.textContent = s.connected ? `Connected: ${s.detail}` : `Not connected: ${s.detail}`;
        statusEl.className = s.connected ? 'status-ok' : 'status-bad';
        const details = await fetch('/ui/connection-details').then(r => r.json());
        document.getElementById('details').textContent = JSON.stringify(details, null, 2);
        const hist = await fetch('/history').then(r=>r.json());
        document.getElementById('recent-checks').textContent = JSON.stringify(hist.items, null, 2);
        const outbox = await fetch('/ui/outbox-status').then(r=>r.json());
        document.getElementById('outbox-status').textContent = `Outbox status counts: ${JSON.stringify(outbox)}`;
        const matrix = await fetch('/ui/provider-matrix').then(r => r.json());
        const headers = ['provider','coverage_type','real_time_support','access_needed','best_use'];
        let html = '<table><thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>';
        for (const row of matrix.providers) {
          html += '<tr>' + headers.map(h => `<td>${row[h] || ''}</td>`).join('') + '</tr>';
        }
        html += '</tbody></table>';
        document.getElementById('adapter-matrix').innerHTML = html;
      }
      document.getElementById('switch-btn').addEventListener('click', async () => {
        const provider = document.getElementById('provider').value;
        await fetch('/ui/select-connection', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({provider})
        });
        await refresh();
      });
      document.getElementById('test-btn').addEventListener('click', async () => {
        const resultEl = document.getElementById('test-result');
        resultEl.textContent = 'Running...';
        try {
          const payload = JSON.parse(document.getElementById('payload').value);
          const resp = await fetch('/ui/test-call', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
          });
          const data = await resp.json();
          resultEl.textContent = JSON.stringify(data, null, 2);
        } catch (err) {
          resultEl.textContent = `Error: ${err}`;
        }
      });
      function parseCsv(text) {
        const lines = text.trim().split(/\\r?\\n/);
        if (lines.length < 2) return [];
        const headers = lines[0].split(',').map(x => x.trim());
        return lines.slice(1).filter(Boolean).map(line => {
          const cols = line.split(',').map(x => x.trim());
          const row = {};
          headers.forEach((h, i) => row[h] = cols[i] || '');
          return row;
        });
      }
      function renderBatchPatients(rows) {
        const container = document.getElementById('batch-patients');
        if (!rows.length) { container.textContent = 'No rows loaded.'; return; }
        const headers = Object.keys(rows[0]);
        let html = '<table><thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>';
        for (const row of rows) {
          html += '<tr>' + headers.map(h => `<td>${row[h] || ''}</td>`).join('') + '</tr>';
        }
        html += '</tbody></table>';
        container.innerHTML = html;
      }
      function toEligibilityPayload(row) {
        return {
          patient: {
            first_name: row.first_name,
            last_name: row.last_name,
            dob: row.dob,
            member_id: row.member_id
          },
          payer: {
            name: row.payer_name,
            payer_id: row.payer_id
          },
          provider: {
            npi: row.npi,
            tax_id: row.tax_id
          },
          service_type: row.service_type || '30'
        };
      }
      async function runBatchCalls() {
        const out = document.getElementById('batch-responses');
        out.innerHTML = '';
        for (let i = 0; i < batchRows.length; i++) {
          const row = batchRows[i];
          const payload = toEligibilityPayload(row);
          const line = document.createElement('pre');
          line.textContent = `#${i + 1} ${row.first_name} ${row.last_name}: running...`;
          out.appendChild(line);
          try {
            const resp = await fetch('/ui/test-call', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify(payload)
            });
            const data = await resp.json();
            line.textContent = `#${i + 1} ${row.first_name} ${row.last_name}: ${JSON.stringify(data)}`;
          } catch (err) {
            line.textContent = `#${i + 1} ${row.first_name} ${row.last_name}: error ${err}`;
          }
        }
      }
      document.getElementById('csv-file').addEventListener('change', async (e) => {
        const f = e.target.files[0];
        if (!f) return;
        const text = await f.text();
        batchRows = parseCsv(text);
        renderBatchPatients(batchRows);
      });
      document.getElementById('load-example-btn').addEventListener('click', async () => {
        const text = await fetch('/example_patients.csv').then(r => r.text());
        batchRows = parseCsv(text);
        renderBatchPatients(batchRows);
      });
      document.getElementById('run-batch-btn').addEventListener('click', async () => {
        await runBatchCalls();
      });
      refresh();
    </script>
  </body>
</html>
"""


@app.get("/ui/connections", include_in_schema=False)
async def ui_connections() -> dict:
    return {
        "providers": get_available_connections(),
        "current_provider": service.get_provider(),
    }


@app.get("/ui/connection-status", include_in_schema=False)
async def ui_connection_status() -> dict:
    return await service.connection_status()


@app.get("/ui/connection-details", include_in_schema=False)
async def ui_connection_details() -> dict:
    return service.connection_details()


@app.post("/ui/select-connection", include_in_schema=False)
async def ui_select_connection(payload: dict) -> dict:
    provider = str(payload.get("provider", "")).lower()
    if provider not in get_available_connections():
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'")
    service.set_provider(provider)
    return await service.connection_status()


@app.post("/ui/test-call", include_in_schema=False)
async def ui_test_call(payload: EligibilityRequest, db: Session = Depends(get_db)) -> dict:
    from datetime import datetime, timezone
    started = datetime.now(timezone.utc)
    req_rec = create_request_record(db, payload, "/ui/test-call", service.get_provider())
    try:
        response = await service.check(payload)
        complete_request_success(db, req_rec, response, started)
        return response.model_dump(mode="json")
    except RuntimeError as exc:
        complete_request_error(db, req_rec, str(exc), started)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/example_patients.csv", response_class=PlainTextResponse, include_in_schema=False)
async def example_patients_csv() -> str:
    csv_path = Path("example_patients.csv")
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="example_patients.csv not found")
    return csv_path.read_text(encoding="utf-8")


@app.get("/ui/provider-matrix", include_in_schema=False)
async def ui_provider_matrix() -> dict:
    return {"providers": PROVIDER_ADAPTER_MATRIX}


@app.get("/history")
async def history(db: Session = Depends(get_db)) -> dict:
    rows = db.query(VerificationRequest).order_by(VerificationRequest.created_at.desc()).limit(25).all()
    return {"items": [{"request_id": r.request_id, "status": r.status, "source": r.provider_source, "created_at": r.created_at.isoformat()} for r in rows]}


@app.get("/history/{request_id}")
async def history_item(request_id: str, db: Session = Depends(get_db)) -> dict:
    req = db.query(VerificationRequest).filter(VerificationRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    res = db.query(VerificationResult).filter(VerificationResult.request_id == request_id).first()
    return {"request": {"request_id": req.request_id, "status": req.status, "error_message": req.error_message}, "result": None if not res else {"status": res.eligibility_status, "plan_name": res.plan_name}}


@app.post("/history/{request_id}/rerun")
async def rerun(request_id: str, db: Session = Depends(get_db)) -> dict:
    req = db.query(VerificationRequest).filter(VerificationRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    payload = EligibilityRequest(patient={"first_name": req.patient_first_name, "last_name": req.patient_last_name, "dob": req.patient_dob.isoformat(), "member_id": req.patient_member_id}, payer={"name": req.payer_name, "payer_id": req.payer_id}, provider={"npi": req.provider_npi, "tax_id": req.provider_tax_id}, service_type=req.service_type)
    return await ui_test_call(payload, db)


@app.get("/history/export.csv", response_class=PlainTextResponse)
async def history_export(db: Session = Depends(get_db)) -> str:
    return nextgen_csv(db)


@app.get("/exports/nextgen/eligibility-results.csv", response_class=PlainTextResponse)
async def nextgen_export(db: Session = Depends(get_db)) -> str:
    return nextgen_csv(db)


@app.get("/ui/outbox-status", include_in_schema=False)
async def ui_outbox_status(db: Session = Depends(get_db)) -> dict:
    return outbox_status_counts(db)


@app.post("/work-items/import.csv")
async def import_work_items_csv(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    content = await file.read()
    text = content.decode("utf-8")
    rows = csv.DictReader(io.StringIO(text))
    inserted = 0
    updated = 0
    for row in rows:
        _, action = upsert_work_item_from_csv_row(db, row)
        if action == "inserted":
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated}


@app.get("/work-items")
async def list_work_items(status: str | None = None, db: Session = Depends(get_db)) -> dict:
    q = db.query(VerificationWorkItem)
    if status:
        q = q.filter(VerificationWorkItem.validation_status == status)
    items = q.order_by(VerificationWorkItem.created_at.desc()).all()
    return {"items": [{"id": i.id, "patient_key": i.patient_key, "validation_status": i.validation_status, "needs_validation": i.needs_validation} for i in items]}


@app.get("/work-items/{item_id}")
async def get_work_item(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.query(VerificationWorkItem).filter(VerificationWorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": item.id, "patient_key": item.patient_key, "first_name": item.first_name, "last_name": item.last_name, "dob": item.dob.isoformat(), "member_id": item.member_id, "payer_name": item.payer_name, "payer_id": item.payer_id, "npi": item.npi, "tax_id": item.tax_id, "service_type": item.service_type, "validation_status": item.validation_status, "needs_validation": item.needs_validation, "last_request_id": item.last_request_id}


async def _validate_work_item(item: VerificationWorkItem, db: Session) -> dict:
    payload = EligibilityRequest(patient={"first_name": item.first_name, "last_name": item.last_name, "dob": item.dob.isoformat(), "member_id": item.member_id}, payer={"name": item.payer_name, "payer_id": item.payer_id}, provider={"npi": item.npi, "tax_id": item.tax_id}, service_type=item.service_type)
    started = datetime.now(timezone.utc)
    req_rec = create_request_record(db, payload, "/work-items/{id}/validate", service.get_provider())
    try:
        response = await service.check(payload)
        complete_request_success(db, req_rec, response, started)
        item.needs_validation = False
        item.validation_status = "validated"
        item.last_validated_at = datetime.utcnow()
        item.last_request_id = req_rec.request_id
        db.commit()
        db.refresh(item)
        return {"id": item.id, "validation_status": item.validation_status, "last_request_id": item.last_request_id}
    except RuntimeError as exc:
        complete_request_error(db, req_rec, str(exc), started)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/work-items/{item_id}/validate")
async def validate_work_item(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.query(VerificationWorkItem).filter(VerificationWorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return await _validate_work_item(item, db)


@app.post("/work-items/validate-pending")
async def validate_pending_work_items(db: Session = Depends(get_db)) -> dict:
    items = db.query(VerificationWorkItem).filter(VerificationWorkItem.needs_validation.is_(True)).all()
    validated = []
    for item in items:
        validated.append(await _validate_work_item(item, db))
    return {"validated_count": len(validated), "items": validated}
