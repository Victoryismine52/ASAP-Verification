"""
FastAPI application entry point for the eligibility-service.

Start with:
    uvicorn app.main:app --reload
or via Docker Compose:
    docker compose up
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pathlib import Path

from app.routers import eligibility as eligibility_router
from app.services.eligibility_service import PROVIDER_ADAPTER_MATRIX, get_available_connections, service
from app.models.eligibility import EligibilityRequest
from app.utils.logging import configure_logging

# Configure structured logging before anything else
configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Handle application startup and shutdown events."""
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
      <h3>Provider Adapter Matrix</h3>
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
async def ui_test_call(payload: EligibilityRequest) -> dict:
    response = await service.check(payload)
    return response.model_dump(mode="json")


@app.get("/example_patients.csv", response_class=PlainTextResponse, include_in_schema=False)
async def example_patients_csv() -> str:
    csv_path = Path("example_patients.csv")
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="example_patients.csv not found")
    return csv_path.read_text(encoding="utf-8")


@app.get("/ui/provider-matrix", include_in_schema=False)
async def ui_provider_matrix() -> dict:
    return {"providers": PROVIDER_ADAPTER_MATRIX}
