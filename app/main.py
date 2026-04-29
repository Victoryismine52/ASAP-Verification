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
from fastapi.responses import HTMLResponse

from app.routers import eligibility as eligibility_router
from app.services.eligibility_service import get_available_connections, service
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
      body { font-family: Arial, sans-serif; max-width: 700px; margin: 3rem auto; line-height: 1.4; }
      .card { border: 1px solid #ddd; padding: 1rem 1.25rem; border-radius: 8px; }
      .status-ok { color: #157347; }
      .status-bad { color: #842029; }
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
