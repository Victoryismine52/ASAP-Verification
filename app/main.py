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
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pathlib import Path

from app.routers import eligibility as eligibility_router
from app.services.eligibility_service import PROVIDER_ADAPTER_MATRIX, get_available_connections, service
from app.models.eligibility import EligibilityRequest
from sqlalchemy.orm import Session
from app.db import Base, engine, get_db
from app.models.persistence import IntegrationOutbox, VerificationRequest, VerificationResult, VerificationWorkItem
from app.services.persistence_service import complete_request_error, complete_request_success, create_request_record, nextgen_csv, outbox_status_counts, patient_key_for_row, upsert_work_item_from_csv_row
from app.services.demo_data_service import load_demo_data, delete_demo_data, demo_data_counts
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
    """Operations console UI."""
    return """
<!doctype html><html><head><meta charset='utf-8'/><title>ASAP Verification Console</title>
<style>
:root{--bg:#eef1f5;--surface:#fff;--text:#1f2937;--muted:#6b7280;--nav:#111827;--nav-hover:#1f2937;--accent:#2563eb;--accent-hover:#1d4ed8;--border:#e5e7eb;--shadow:0 4px 14px rgba(15,23,42,.08)}
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text)}
.layout{display:flex;min-height:100vh}.sidebar{width:250px;background:var(--nav);color:#e5e7eb;padding:1.2rem .9rem;position:sticky;top:0;height:100vh}
.brand h1{font-size:1.1rem;margin:0 0 .3rem}.brand p{font-size:.78rem;line-height:1.4;color:#c7d2fe;margin:0 0 .7rem}.badge{display:inline-block;background:#f59e0b;color:#111827;font-weight:700;border-radius:999px;padding:.2rem .6rem;font-size:.72rem}
.tabs{display:flex;flex-direction:column;gap:.45rem;margin-top:1rem}.tabs button{border:1px solid #374151;background:transparent;color:#e5e7eb;border-radius:10px;padding:.55rem .7rem;text-align:left;cursor:pointer}.tabs button:hover{background:var(--nav-hover)}.tabs button.active{background:#374151;border-color:#4b5563}
.main{flex:1;padding:1.25rem}.tab{display:none}.tab.active{display:block}.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);padding:1rem;margin-bottom:1rem}
.card h2{margin:.1rem 0 .7rem}.subtitle{color:var(--muted)}.banner{border-left:4px solid var(--accent);background:#eff6ff}.controls{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin:.7rem 0}
input,select,textarea{border:1px solid #cbd5e1;border-radius:10px;padding:.5rem .6rem;font-size:.92rem;background:#fff}textarea{width:100%;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.btn{border:none;border-radius:10px;padding:.52rem .75rem;font-weight:600;cursor:pointer}.btn-primary{background:var(--accent);color:#fff}.btn-primary:hover{background:var(--accent-hover)}
.btn-secondary{background:#e5e7eb;color:#111827}.btn-secondary:hover{background:#d1d5db}.btn-danger{background:#dc2626;color:#fff}.btn-danger:hover{background:#b91c1c}.btn-sm{padding:.26rem .48rem;font-size:.74rem;border-radius:7px}
a.link-btn{display:inline-block;text-decoration:none}
.table-wrap{overflow-x:auto;overflow-y:auto;border:1px solid var(--border);border-radius:12px;background:#fff}.data-table{width:100%;min-width:1400px;table-layout:auto;border-collapse:separate;border-spacing:0;background:#fff;font-size:.86rem}.data-table th,.data-table td{padding:.5rem;border-bottom:1px solid #e5e7eb;vertical-align:top;white-space:nowrap}.data-table th{background:#f8fafc;text-transform:uppercase;font-size:.72rem;letter-spacing:.03em;color:#475569;position:sticky;top:0}.data-table tbody tr:hover{background:#f8fafc}#work-table{min-width:1700px}#hist-table{min-width:1500px}#outbox-table{min-width:1200px}.wrap-cell{white-space:normal}.muted{color:var(--muted);font-size:.8em}.action-group{display:flex;flex-direction:row;gap:.35rem;flex-wrap:nowrap;white-space:nowrap}.data-table th:last-child,.data-table td:last-child{position:sticky;right:0;background:#fff;z-index:1}.data-table th:last-child{z-index:2}
.status-badge{display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.74rem;font-weight:700}.pending_validation{background:#fef3c7;color:#92400e}.needs_revalidation{background:#ffedd5;color:#9a3412}.validated{background:#dcfce7;color:#166534}.failed{background:#fee2e2;color:#991b1b}.ready_for_review{background:#e0e7ff;color:#3730a3}.exported{background:#cffafe;color:#155e75}.posted{background:#dbeafe;color:#1e3a8a}.demo{background:#ede9fe;color:#5b21b6}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:.7rem}.metric{background:#fff;border:1px solid var(--border);border-radius:12px;padding:.7rem}.metric .label{font-size:.78rem;color:var(--muted)}.metric .value{font-size:1.3rem;font-weight:700}
.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.75rem}.field label{display:block;font-size:.85rem;color:var(--muted);margin-bottom:.25rem}.hidden{display:none}
.timeline{display:flex;flex-wrap:wrap;gap:.5rem;margin:.6rem 0 1rem}
.stage-pill{background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe;padding:.3rem .55rem;border-radius:999px;font-size:.78rem;font-weight:600}
.scenario-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.7rem}
.scenario-card{border:1px solid var(--border);border-radius:12px;padding:.8rem;background:#fff}
.scenario-card.active{border-color:#6366f1;box-shadow:0 0 0 2px rgba(99,102,241,.15)}
.activity-feed{margin-top:.8rem;border:1px solid var(--border);border-radius:12px;padding:.65rem;max-height:220px;overflow-y:auto;background:#f8fafc}
.activity-line{font-size:.85rem;border-bottom:1px solid #e5e7eb;padding:.35rem 0}
.factory-note{font-size:.85rem;color:#475569;background:#f8fafc;border:1px dashed #cbd5e1;padding:.55rem;border-radius:10px}
@media (max-width:980px){.layout{flex-direction:column}.sidebar{height:auto;width:100%;position:static}.tabs{flex-direction:row;overflow:auto}.tabs button{white-space:nowrap}.main{padding:.8rem}}
</style></head><body>
<div class='layout'><aside class='sidebar'><div class='brand'><h1>ASAP Verification Console</h1><p>Standalone verification workbench for eligibility checks, work queue review, exports, and future EHR integration.</p><span class='badge'>Prototype / Mock Mode</span></div>
<div class='tabs'><button onclick="showTab('dashboard')" data-tab='dashboard'>Dashboard</button><button onclick="showTab('demotour')" data-tab='demotour'>API Factory Demo</button><button onclick="showTab('workqueue')" data-tab='workqueue'>Work Queue</button><button onclick="showTab('history')" data-tab='history'>Request History</button><button onclick="showTab('outbox')" data-tab='outbox'>Outbox</button><button onclick="showTab('exports')" data-tab='exports'>Exports</button><button onclick="showTab('providers')" data-tab='providers'>Providers</button><button onclick="showTab('manual')" data-tab='manual'>Manual Test</button><button onclick="showTab('demodata')" data-tab='demodata'>Demo Data</button></div></aside>
<main class='main'>
<div id='dashboard' class='tab active'><div class='card'><h2>Dashboard</h2><p class='subtitle'>ASAP Verification Operations Console</p><div class='card banner'>This console is designed as a standalone verification layer. Records can enter through CSV upload, manual entry, NextGen report/scraper imports, or future EHR APIs. Verification can run through mock mode today and later through Availity or other adapter sources. Results are stored, reviewable, exportable, and staged through the outbox.</div><div id='dashboard-metrics' class='metrics'></div><details><summary>Raw dashboard JSON</summary><pre id='dash'></pre></details><div class='controls'><button class='btn btn-primary' onclick='validatePending()'>Validate Pending</button><a class='link-btn btn btn-secondary' href='/work-items/export.csv'>Export Work Queue CSV</a></div></div></div>
<div id='demotour' class='tab'><div class='card'><h2>API Factory Demo</h2><p class='subtitle'>Watch records move through an API service pipeline: load records, make JSON, send to an endpoint, receive a response, save the result, and stage the output.</p><div class='timeline'><span class='stage-pill'>Load patients</span><span class='stage-pill'>Make JSON</span><span class='stage-pill'>Send to API</span><span class='stage-pill'>Get answer</span><span class='stage-pill'>Save result</span><span class='stage-pill'>Stage output</span></div><p class='factory-note'>Live Availity data requires vendor access. Mock mode uses the same workflow with demo data.</p><div class='controls'><label for='factory-provider'>Verification Source</label><select id='factory-provider'></select><button class='btn btn-secondary' onclick='setLiveDemoProvider()'>Set Source</button><button class='btn btn-danger' onclick='resetLiveDemo()'>Reset Demo Data</button><button class='btn btn-primary' onclick='loadLiveDemoPatients()'>Load Unknown Demo Patients</button><button class='btn btn-secondary' onclick='refreshLiveDemo()'>Refresh</button><button class='btn btn-secondary' onclick="alert('Use the row-level Preview JSON button.')">Preview Request JSON</button><button class='btn btn-primary' onclick="alert('Use the row-level Send button or Send All Pending.')">Send Selected</button><button class='btn btn-primary' onclick='validateLiveDemoAllPending()'>Send All Pending</button><a class='link-btn btn btn-secondary' href='/work-items/export.csv'>Export Results CSV</a></div><pre id='live-demo-preview'></pre><h3>Latest Response Payload</h3><pre id='live-demo-response'></pre><h3>What changed?</h3><pre id='live-demo-what-changed'></pre><h3>Linked Records</h3><pre id='live-demo-linked-records'></pre><div id='live-demo-metrics' class='metrics'></div><div class='table-wrap'><table id='live-demo-table' class='data-table'></table></div><h3>Activity Log</h3><div id='demo-activity' class='activity-feed'></div><div class='controls'><button class='btn btn-secondary btn-sm' onclick="showTab('workqueue')">Open Work Queue</button><button class='btn btn-secondary btn-sm' onclick="showTab('history')">Open Request History</button><button class='btn btn-secondary btn-sm' onclick="showTab('outbox')">Open Outbox</button><button class='btn btn-secondary btn-sm' onclick="showTab('manual')">Open Manual Test</button><button class='btn btn-secondary btn-sm' onclick="showTab('providers')">Open Providers</button></div></div></div>
<div id='workqueue' class='tab'><div class='card'><h2>Work Queue</h2><div class='controls'><input id='work-status' placeholder='status filter'/><button class='btn btn-secondary' onclick='loadWork()'>Refresh</button><button class='btn btn-primary' onclick='validatePending()'>Validate Pending</button><input id='csv-file' type='file' accept='.csv'/><button class='btn btn-primary' onclick='importCsv()'>Import CSV to Work Queue</button></div><pre id='import-result'></pre><div class='table-wrap'><table id='work-table' class='data-table'></table></div></div></div>
<div id='history' class='tab'><div class='card'><h2>Request History</h2><button class='btn btn-secondary' onclick='loadHistory()'>Refresh</button><div class='table-wrap'><table id='hist-table' class='data-table'></table></div></div></div>
<div id='outbox' class='tab'><div class='card'><h2>Outbox</h2><div class='controls'><button class='btn btn-secondary' onclick='loadOutbox()'>Refresh</button><a class='link-btn btn btn-secondary' href='/outbox/export.csv'>Export CSV</a></div><div class='table-wrap'><table id='outbox-table' class='data-table'></table></div></div></div>
<div id='exports' class='tab'><div class='card'><h2>Exports</h2><ul><li><a href='/exports/nextgen/eligibility-results.csv'>Download NextGen Eligibility CSV</a></li><li><a href='/history/export.csv'>Download History CSV</a></li><li><a href='/work-items/export.csv'>Download Work Queue CSV</a></li><li><a href='/outbox/export.csv'>Download Outbox CSV</a></li></ul></div></div>
<div id='providers' class='tab'><div class='card'><h2>Providers</h2><h3>Provider Adapter Matrix</h3><p><strong>Active Verification Source</strong></p><div class='controls'><label for='provider'>Provider:</label><select id='provider'></select><button class='btn btn-primary' id='switch-btn'>Switch</button><button class='btn btn-secondary' onclick='loadProviders()'>Refresh Provider Status</button></div><p><strong>Provider Status</strong></p><pre id='provider-status'></pre><p><strong>Connection Details</strong></p><pre id='details'></pre><div id='adapter-matrix'></div></div></div>
<div id='manual' class='tab'><div class='card'><h2>Manual Test</h2><p class='subtitle'>Use this tab to manually create or edit an eligibility request, choose a verification source, and run the selected service. Form view is for operational testing; raw JSON is for developer/API testing.</p><div class='controls'><label for='manual-provider'>Verification Source</label><select id='manual-provider'></select><label for='manual-action'>Service Action</label><select id='manual-action'><option value='eligibility_check'>eligibility_check</option></select><button class='btn btn-secondary' type='button' onclick="setManualMode('form')">Form View</button><button class='btn btn-secondary' type='button' onclick="setManualMode('json')">Raw JSON</button></div><div id='manual-form-card' class='card'><div class='form-grid'><div class='field'><label for='first_name'>first_name</label><input id='first_name' /></div><div class='field'><label for='last_name'>last_name</label><input id='last_name' /></div><div class='field'><label for='dob'>dob</label><input id='dob' /></div><div class='field'><label for='member_id'>member_id</label><input id='member_id' /></div><div class='field'><label for='payer_name'>payer_name</label><input id='payer_name' /></div><div class='field'><label for='payer_id'>payer_id</label><input id='payer_id' /></div><div class='field'><label for='npi'>npi</label><input id='npi' /></div><div class='field'><label for='tax_id'>tax_id</label><input id='tax_id' /></div><div class='field'><label for='service_type'>service_type</label><input id='service_type' /></div></div></div><div id='manual-json-card' class='card hidden'><textarea id='payload' rows='12'></textarea><div class='controls'><button class='btn btn-secondary' type='button' onclick='formatManualJson()'>Format JSON</button><button class='btn btn-secondary' type='button' onclick='syncJsonToForm()'>Sync JSON to Form</button><button class='btn btn-secondary' type='button' onclick='syncFormToJson()'>Sync Form to JSON</button></div></div><div class='controls'><button class='btn btn-primary' id='test-btn'>Run Test Call</button></div><pre id='test-result'></pre></div></div>
<div id='demodata' class='tab'><div class='card'><h2>Demo Data</h2><div class='card banner'><strong>Demo data notice:</strong> All demo records are synthetic, flagged with is_demo=true, and excluded from exports by default.</div><div class='controls'><button class='btn btn-primary' onclick='loadDemoData()'>Load Demo Data</button><button class='btn btn-danger' onclick='deleteDemoData()'>Delete Demo Data</button></div><pre id='demo-counts'></pre></div></div>
</main></div>
<script>
function badge(s){return `<span class="status-badge ${s||''}">${s||''}</span>`;}
function shortId(value){if(!value)return '';const v=String(value);return v.length>14?`${v.slice(0,14)}…`:v;}
window.showTab = function(id) {var target = document.getElementById(id);if (!target) {console.error('Missing tab', id);return;}document.querySelectorAll('.tab').forEach(function(tab) {tab.classList.remove('active');});document.querySelectorAll('.tabs button').forEach(function(btn) {btn.classList.toggle('active', btn.dataset.tab === id);});target.classList.add('active');if (id === 'providers' && typeof loadProviders === 'function') {loadProviders().catch(function(err) {console.error('loadProviders failed', err);});}};
async function safeCall(label, fn) {try {return await fn();} catch (err) {console.error(label, err);return null;}}
async function dashboard(){const w=await fetch('/work-items').then(r=>r.json());const h=await fetch('/history').then(r=>r.json());const o=await fetch('/outbox').then(r=>r.json());const c={total_work_items:w.items.length,pending_validation:w.items.filter(i=>i.validation_status==='pending_validation').length,needs_revalidation:w.items.filter(i=>i.validation_status==='needs_revalidation').length,validated:w.items.filter(i=>i.validation_status==='validated').length,failed:w.items.filter(i=>i.validation_status==='failed').length,outbox_status_counts:o.status_counts,recent_request_count:h.items.length};document.getElementById('dash').textContent=JSON.stringify(c,null,2);document.getElementById('dashboard-metrics').innerHTML=`<div class='metric'><div class='label'>Total Work Items</div><div class='value'>${c.total_work_items}</div></div><div class='metric'><div class='label'>Pending Validation</div><div class='value'>${c.pending_validation}</div></div><div class='metric'><div class='label'>Needs Revalidation</div><div class='value'>${c.needs_revalidation}</div></div><div class='metric'><div class='label'>Validated</div><div class='value'>${c.validated}</div></div><div class='metric'><div class='label'>Failed</div><div class='value'>${c.failed}</div></div><div class='metric'><div class='label'>Recent Requests</div><div class='value'>${c.recent_request_count}</div></div>`}
async function loadWork(){const s=document.getElementById('work-status').value;const u=s?`/work-items?status=${encodeURIComponent(s)}`:'/work-items';const w=await fetch(u).then(r=>r.json());let html='<thead><tr><th>ID</th><th>Patient</th><th>DOB</th><th>Member ID</th><th>Payer</th><th>Service</th><th>Status</th><th>Needs Check</th><th>Last Checked</th><th>Updated</th><th>Actions</th></tr></thead><tbody>';for(const i of w.items){html+=`<tr><td>${i.id}</td><td>${i.first_name||''} ${i.last_name||''}</td><td>${i.dob||''}</td><td>${i.member_id||''}</td><td class='wrap-cell'>${i.payer_name||''}<br><span class='muted'>${i.payer_id||''}</span></td><td>${i.service_type||''}</td><td>${badge(i.validation_status)}</td><td>${i.needs_validation}</td><td>${i.last_validated_at||''}</td><td>${i.updated_at||''}</td><td><div class='action-group'><button class='btn btn-secondary btn-sm' onclick='viewItem(${i.id})'>View</button><button class='btn btn-secondary btn-sm' onclick='editItem(${i.id})'>Edit</button><button class='btn btn-primary btn-sm' onclick='validateItem(${i.id})'>Validate</button><button class='btn btn-secondary btn-sm view-last-btn' data-request-id='${i.last_request_id||""}'>View Last Result</button></div></td></tr>`}document.getElementById('work-table').innerHTML=html+'</tbody>';document.querySelectorAll('.view-last-btn').forEach((btn)=>{btn.addEventListener('click',()=>viewLast(btn.dataset.requestId||''));});dashboard();}
async function importCsv(){const f=document.getElementById('csv-file').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);const r=await fetch('/work-items/import.csv',{method:'POST',body:fd});document.getElementById('import-result').textContent=JSON.stringify(await r.json(),null,2);loadWork();}
async function validateItem(id){await fetch(`/work-items/${id}/validate`,{method:'POST'});loadWork();}
async function validatePending(){await fetch('/work-items/validate-pending',{method:'POST'});loadWork();}
async function viewItem(id){alert(JSON.stringify(await fetch(`/work-items/${id}`).then(r=>r.json()),null,2));}
async function editItem(id){const cur=await fetch(`/work-items/${id}`).then(r=>r.json());cur.notes=prompt('notes',cur.notes||'')||cur.notes;await fetch(`/work-items/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(cur)});loadWork();}
async function viewLast(rid){if(!rid)return;alert(JSON.stringify(await fetch(`/history/${rid}`).then(r=>r.json()),null,2));}
async function loadHistory(){const h=await fetch('/history').then(r=>r.json());let html='<thead><tr><th>Request</th><th>Patient</th><th>Payer</th><th>Service</th><th>Status</th><th>Source</th><th>Created</th><th>Duration</th><th>Error</th><th>Actions</th></tr></thead><tbody>';for(const i of h.items){html+=`<tr><td title="${i.request_id||''}">${shortId(i.request_id)}</td><td>${i.patient}</td><td class='wrap-cell'>${i.payer}</td><td>${i.service_type}</td><td>${badge(i.status)}</td><td>${i.provider_source}</td><td>${i.created_at}</td><td>${i.duration_ms||''}</td><td class='wrap-cell'>${i.error_message||''}</td><td><div class='action-group'><button class='btn btn-secondary btn-sm history-view-btn' data-request-id='${i.request_id}'>View Details</button><button class='btn btn-primary btn-sm history-rerun-btn' data-request-id='${i.request_id}'>Rerun</button><button class='btn btn-secondary btn-sm history-edit-btn' data-request-id='${i.request_id}'>Edit Before Rerun</button></div></td></tr>`}document.getElementById('hist-table').innerHTML=html+'</tbody>';document.querySelectorAll('.history-view-btn').forEach((btn)=>{btn.addEventListener('click',()=>viewLast(btn.dataset.requestId||''));});document.querySelectorAll('.history-rerun-btn').forEach((btn)=>{btn.addEventListener('click',()=>rerun(btn.dataset.requestId||''));});document.querySelectorAll('.history-edit-btn').forEach((btn)=>{btn.addEventListener('click',()=>editBeforeRerun(btn.dataset.requestId||''));});}
async function rerun(id){await fetch(`/history/${id}/rerun`,{method:'POST'});loadHistory();}
async function editBeforeRerun(id){const d=await fetch(`/history/${id}`).then(r=>r.json());document.getElementById('payload').value=JSON.stringify(d.request_payload,null,2);showTab('manual');}
async function loadOutbox(){const o=await fetch('/outbox').then(r=>r.json());let html='<thead><tr><th>ID</th><th>Request</th><th>Target</th><th>Record Type</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead><tbody>';for(const i of o.items){html+=`<tr><td>${i.id}</td><td title="${i.request_id||''}">${shortId(i.request_id)}</td><td>${i.target_system}</td><td>${i.target_record_type}</td><td>${badge(i.status)}</td><td>${i.created_at}</td><td><div class='action-group'><button class='btn btn-secondary btn-sm' onclick='updateOutbox(${i.id})'>Update Status</button><button class='btn btn-secondary btn-sm' onclick='viewOutbox(${i.id})'>View Payload</button></div></td></tr>`}document.getElementById('outbox-table').innerHTML=html+'</tbody>';}
async function updateOutbox(id){const status=prompt('status: ready_for_review/exported/posted/failed','exported');if(!status)return;await fetch(`/outbox/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});loadOutbox();dashboard();}
async function viewOutbox(id){alert(JSON.stringify(await fetch(`/outbox/${id}`).then(r=>r.json()),null,2));}
async function loadDemoCounts(){document.getElementById('demo-counts').textContent=JSON.stringify(await fetch('/demo/counts').then(r=>r.json()),null,2)}
async function loadDemoData(){await fetch('/demo/load',{method:'POST'});await loadDemoCounts();await loadWork();}
async function deleteDemoData(){await fetch('/demo/delete',{method:'DELETE'});await loadDemoCounts();await loadWork();}
let liveDemoItems=[];let liveDemoHistory=[];let liveDemoOutbox=[];let demoActivityLog=[];
function addLiveDemoActivity(message){demoActivityLog.push({ts:new Date().toISOString(),message});const el=document.getElementById('demo-activity');if(el){el.innerHTML=demoActivityLog.map(x=>`<div class='activity-line'><strong>${x.ts}</strong> — ${x.message}</div>`).join('')||"<div class='activity-line muted'>No activity yet.</div>";}}
function renderLiveDemoTable(){const t=document.getElementById('live-demo-table');if(!t)return;let html="<thead><tr><th>ID</th><th>Patient</th><th>DOB</th><th>Member ID</th><th>Payer</th><th>Service</th><th>Status</th><th>Last Checked</th><th>Actions</th></tr></thead><tbody>";for(const i of liveDemoItems){html+=`<tr><td>${i.id}</td><td>${i.first_name||''} ${i.last_name||''}</td><td>${i.dob||''}</td><td>${i.member_id||''}</td><td>${i.payer_name||''}</td><td>${i.service_type||''}</td><td>${badge(i.validation_status)}</td><td>${i.last_validated_at||''}</td><td><div class='action-group'><button class='btn btn-secondary btn-sm' onclick='previewLiveDemoRequestById(${i.id})'>Preview JSON</button><button class='btn btn-primary btn-sm' onclick='validateLiveDemoOne(${i.id})'>Send</button></div></td></tr>`;}t.innerHTML=html+'</tbody>';}
function renderLiveDemoMetrics(){const m=document.getElementById('live-demo-metrics');if(!m)return;const pending=liveDemoItems.filter(i=>i.validation_status==='pending_validation').length;const needs=liveDemoItems.filter(i=>i.validation_status==='needs_revalidation').length;const validated=liveDemoItems.filter(i=>i.validation_status==='validated').length;const failed=liveDemoItems.filter(i=>i.validation_status==='failed').length;const ready=liveDemoOutbox.filter(i=>i.status==='ready_for_review').length;const exported=liveDemoOutbox.filter(i=>i.status==='exported').length;m.innerHTML=`<div class='metric'><div class='label'>Work Items</div><div class='value'>${liveDemoItems.length}</div></div><div class='metric'><div class='label'>Pending</div><div class='value'>${pending}</div></div><div class='metric'><div class='label'>Needs Revalidation</div><div class='value'>${needs}</div></div><div class='metric'><div class='label'>Validated</div><div class='value'>${validated}</div></div><div class='metric'><div class='label'>Failed</div><div class='value'>${failed}</div></div><div class='metric'><div class='label'>History Rows</div><div class='value'>${liveDemoHistory.length}</div></div><div class='metric'><div class='label'>Outbox Ready</div><div class='value'>${ready}</div></div><div class='metric'><div class='label'>Outbox Exported</div><div class='value'>${exported}</div></div>`;}
async function loadLiveDemoProviders(){const meta=await fetch('/ui/connections').then(r=>r.json());const sel=document.getElementById('factory-provider');if(!sel)return;sel.innerHTML='';for(const p of meta.providers){const o=document.createElement('option');o.value=p;o.textContent=p;if(p===meta.current_provider)o.selected=true;sel.appendChild(o);}}
async function setLiveDemoProvider(){const provider=document.getElementById('factory-provider').value;await fetch('/ui/select-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider})});addLiveDemoActivity(`POST /ui/select-connection → provider set to ${provider}`);}
async function refreshLiveDemo(){const [w,h,o]=await Promise.all([fetch('/work-items').then(r=>r.json()),fetch('/history').then(r=>r.json()),fetch('/outbox').then(r=>r.json())]);liveDemoItems=w.items||[];liveDemoHistory=h.items||[];liveDemoOutbox=o.items||[];renderLiveDemoTable();renderLiveDemoMetrics();}
async function resetLiveDemo(){const r=await fetch('/demo/delete',{method:'DELETE'}).then(x=>x.json());addLiveDemoActivity(`DELETE /demo/delete → deleted demo rows (${JSON.stringify(r)})`);await refreshLiveDemo();await loadWork();await loadHistory();await loadOutbox();await loadDemoCounts();await dashboard();}
async function loadLiveDemoPatients(){const r=await fetch('/demo/load',{method:'POST'}).then(x=>x.json());addLiveDemoActivity(`POST /demo/load → loaded demo patients (${JSON.stringify(r)})`);await refreshLiveDemo();await loadWork();await loadHistory();await loadOutbox();await loadDemoCounts();await dashboard();}
async function previewLiveDemoRequestById(id) {const r = await fetch(`/work-items/${id}/preview-request`, { method: 'POST' }).then(x => x.json());document.getElementById('live-demo-preview').textContent = JSON.stringify(r, null, 2);addLiveDemoActivity(`POST /work-items/${id}/preview-request → built JSON payload`);}
async function showLatestFactoryResult(validationResponse){const responseEl=document.getElementById('live-demo-response');const changesEl=document.getElementById('live-demo-what-changed');const linkedEl=document.getElementById('live-demo-linked-records');if(responseEl)responseEl.textContent=JSON.stringify(validationResponse,null,2);let historyDetail=null;let firstResult=(validationResponse?.results||[]).find(x=>x.request_id);if(firstResult?.request_id){try{historyDetail=await fetch(`/history/${firstResult.request_id}`).then(r=>r.json());if(responseEl)responseEl.textContent=`${JSON.stringify(validationResponse,null,2)}\n\nHistory Detail:\n${JSON.stringify(historyDetail,null,2)}`;}catch(err){if(responseEl)responseEl.textContent=`${JSON.stringify(validationResponse,null,2)}\n\nHistory fetch error: ${err?.message||err}`;}}if(changesEl)changesEl.textContent=JSON.stringify((validationResponse?.results||[]).map(x=>({id:x.id,status:x.status,request_id:x.request_id||null,error:x.error||null})),null,2);if(linkedEl)linkedEl.textContent=JSON.stringify({provider:validationResponse?.provider,request_id:firstResult?.request_id||null,history_status:historyDetail?.request?.status||null,outbox_status:historyDetail?.outbox?.status||null,error_message:historyDetail?.request?.error_message||null},null,2);}
async function validateLiveDemoOne(id) {const provider = document.getElementById('factory-provider').value;const r = await fetch('/work-items/validate-selected', {method: 'POST',headers: { 'Content-Type': 'application/json' },body: JSON.stringify({ ids: [id], provider })}).then(x => x.json());addLiveDemoActivity(`POST /work-items/validate-selected provider=${provider} → validated ${r.validated_count}, failed ${r.failed_count}`);await showLatestFactoryResult(r);await refreshLiveDemo();await loadWork();await loadHistory();await loadOutbox();await loadDemoCounts();await dashboard();}
async function validateLiveDemoSelected(){alert('Use the row-level Send button or Send All Pending.');}
async function previewLiveDemoRequest(){alert('Use the row-level Preview JSON button.');}
async function validateLiveDemoAllPending(){const provider=document.getElementById('factory-provider').value;await fetch('/ui/select-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider})});addLiveDemoActivity(`POST /ui/select-connection → provider set to ${provider}`);const pendingIds=liveDemoItems.filter(i=>i.needs_validation).map(i=>i.id);const r=await fetch('/work-items/validate-selected',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:pendingIds,provider})}).then(x=>x.json());addLiveDemoActivity(`POST /work-items/validate-selected provider=${provider} → validated ${r.validated_count}, failed ${r.failed_count}`);await showLatestFactoryResult(r);await refreshLiveDemo();await loadWork();await loadHistory();await loadOutbox();await loadDemoCounts();await dashboard();}
async function loadProviders(){const meta=await fetch('/ui/connections').then(r=>r.json());const sel=document.getElementById('provider');sel.innerHTML='';for(const p of meta.providers){const o=document.createElement('option');o.value=p;o.textContent=p;if(p===meta.current_provider)o.selected=true;sel.appendChild(o);}const status=await fetch('/ui/connection-status').then(r=>r.json());document.getElementById('provider-status').textContent=JSON.stringify(status,null,2);const details=await fetch('/ui/connection-details').then(r=>r.json());document.getElementById('details').textContent=JSON.stringify(details,null,2);const matrix=await fetch('/ui/provider-matrix').then(r=>r.json());document.getElementById('adapter-matrix').textContent=JSON.stringify(matrix.providers,null,2);}
async function switchProvider(){const provider=document.getElementById('provider').value;const resp=await fetch('/ui/select-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider})});const data=await resp.json();document.getElementById('provider-status').textContent=JSON.stringify(data,null,2);await loadProviders();}
function getPayloadFromForm(){return {patient:{first_name:document.getElementById('first_name').value,last_name:document.getElementById('last_name').value,dob:document.getElementById('dob').value,member_id:document.getElementById('member_id').value},payer:{name:document.getElementById('payer_name').value,payer_id:document.getElementById('payer_id').value},provider:{npi:document.getElementById('npi').value,tax_id:document.getElementById('tax_id').value},service_type:document.getElementById('service_type').value};}
function populateFormFromPayload(payload){document.getElementById('first_name').value=payload?.patient?.first_name||'';document.getElementById('last_name').value=payload?.patient?.last_name||'';document.getElementById('dob').value=payload?.patient?.dob||'';document.getElementById('member_id').value=payload?.patient?.member_id||'';document.getElementById('payer_name').value=payload?.payer?.name||'';document.getElementById('payer_id').value=payload?.payer?.payer_id||'';document.getElementById('npi').value=payload?.provider?.npi||'';document.getElementById('tax_id').value=payload?.provider?.tax_id||'';document.getElementById('service_type').value=payload?.service_type||'';}
function syncFormToJson(){document.getElementById('payload').value=JSON.stringify(getPayloadFromForm(),null,2);}
function syncJsonToForm(){try{populateFormFromPayload(JSON.parse(document.getElementById('payload').value));}catch(e){document.getElementById('test-result').textContent=`Invalid JSON: ${e.message}`;throw e;}}
function formatManualJson(){try{document.getElementById('payload').value=JSON.stringify(JSON.parse(document.getElementById('payload').value),null,2);}catch(e){document.getElementById('test-result').textContent=`Invalid JSON: ${e.message}`;}}
let manualMode='form';
function setManualMode(mode){if(mode==='json'){syncFormToJson();document.getElementById('manual-form-card').classList.add('hidden');document.getElementById('manual-json-card').classList.remove('hidden');manualMode='json';return;}if(mode==='form'){if(manualMode==='json'){try{syncJsonToForm();}catch(e){return;}}document.getElementById('manual-json-card').classList.add('hidden');document.getElementById('manual-form-card').classList.remove('hidden');manualMode='form';}}
async function loadManualProviders(){const meta=await fetch('/ui/connections').then(r=>r.json());const sel=document.getElementById('manual-provider');sel.innerHTML='';for(const p of meta.providers){const o=document.createElement('option');o.value=p;o.textContent=p;if(p===meta.current_provider)o.selected=true;sel.appendChild(o);}}
async function runManualTest(){try{const payload=manualMode==='form'?getPayloadFromForm():JSON.parse(document.getElementById('payload').value);const provider=document.getElementById('manual-provider').value;await fetch('/ui/select-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider})});const r=await fetch('/ui/test-call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();document.getElementById('test-result').textContent=JSON.stringify(data,null,2);if(r.ok){await loadHistory();await loadOutbox();await dashboard();}}catch(e){document.getElementById('test-result').textContent=`Invalid JSON: ${e.message}`;}}
document.getElementById('test-btn').onclick=runManualTest;
document.getElementById('switch-btn').onclick=switchProvider;
const defaultManualPayload={patient:{first_name:'Jane',last_name:'Doe',dob:'1985-06-15',member_id:'MBR123456'},payer:{name:'Blue Cross Blue Shield',payer_id:'BCBS001'},provider:{npi:'1234567890',tax_id:'12-3456789'},service_type:'30'};
(async()=>{document.getElementById('payload').value=JSON.stringify(defaultManualPayload,null,2);populateFormFromPayload(defaultManualPayload);setManualMode('form');showTab('dashboard');addLiveDemoActivity('Live demo ready.');await safeCall('dashboard',()=>dashboard());await safeCall('loadWork',()=>loadWork());await safeCall('loadHistory',()=>loadHistory());await safeCall('loadOutbox',()=>loadOutbox());await safeCall('loadDemoCounts',()=>loadDemoCounts());await safeCall('loadProviders',()=>loadProviders());await safeCall('loadManualProviders',()=>loadManualProviders());await safeCall('loadLiveDemoProviders',()=>loadLiveDemoProviders());await safeCall('refreshLiveDemo',()=>refreshLiveDemo());})();
</script></body></html>"""


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


@app.post("/demo/load")
async def demo_load(db: Session = Depends(get_db)) -> dict:
    return load_demo_data(db)


@app.delete("/demo/delete")
async def demo_delete(db: Session = Depends(get_db)) -> dict:
    return delete_demo_data(db)


@app.get("/demo/counts")
async def demo_counts(db: Session = Depends(get_db)) -> dict:
    return demo_data_counts(db)


@app.get("/history")
async def history(demo: str = "all", db: Session = Depends(get_db)) -> dict:
    q = db.query(VerificationRequest)
    if demo == "only":
        q = q.filter(VerificationRequest.is_demo.is_(True))
    elif demo == "exclude":
        q = q.filter(VerificationRequest.is_demo.is_(False))
    rows = q.order_by(VerificationRequest.created_at.desc()).limit(25).all()
    return {"items": [{"request_id": r.request_id, "patient": f"{r.patient_first_name} {r.patient_last_name}", "payer": f"{r.payer_name} ({r.payer_id})", "service_type": r.service_type, "status": r.status, "provider_source": r.provider_source, "created_at": r.created_at.isoformat(), "duration_ms": r.duration_ms, "error_message": r.error_message, "is_demo": r.is_demo} for r in rows]}


@app.get("/history/{request_id}")
async def history_item(request_id: str, db: Session = Depends(get_db)) -> dict:
    req = db.query(VerificationRequest).filter(VerificationRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    res = db.query(VerificationResult).filter(VerificationResult.request_id == request_id).first()
    outbox = db.query(IntegrationOutbox).filter(IntegrationOutbox.request_id == request_id).order_by(IntegrationOutbox.created_at.desc()).first()
    payload = {"patient": {"first_name": req.patient_first_name, "last_name": req.patient_last_name, "dob": req.patient_dob.isoformat(), "member_id": req.patient_member_id}, "payer": {"name": req.payer_name, "payer_id": req.payer_id}, "provider": {"npi": req.provider_npi, "tax_id": req.provider_tax_id}, "service_type": req.service_type}
    return {
        "request": {"request_id": req.request_id, "status": req.status, "error_message": req.error_message, "provider_source": req.provider_source, "endpoint": req.endpoint, "created_at": req.created_at.isoformat()},
        "request_payload": payload,
        "result": None if not res else {
            "eligibility_status": res.eligibility_status,
            "plan_name": res.plan_name,
            "copay": res.copay,
            "coinsurance": res.coinsurance,
            "deductible_remaining": res.deductible_remaining,
            "out_of_pocket_remaining": res.out_of_pocket_remaining,
            "authorization_required": res.authorization_required,
            "source": res.source,
            "checked_at": res.checked_at.isoformat() if res.checked_at else None,
            "raw_response_json": json.loads(res.raw_response_json) if res.raw_response_json else None,
            "notes": res.notes,
        },
        "outbox": None if not outbox else {"id": outbox.id, "status": outbox.status, "target_system": outbox.target_system, "target_record_type": outbox.target_record_type, "payload_json": json.loads(outbox.payload_json) if outbox.payload_json else None},
    }


@app.post("/history/{request_id}/rerun")
async def rerun(request_id: str, db: Session = Depends(get_db)) -> dict:
    req = db.query(VerificationRequest).filter(VerificationRequest.request_id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    payload = EligibilityRequest(patient={"first_name": req.patient_first_name, "last_name": req.patient_last_name, "dob": req.patient_dob.isoformat(), "member_id": req.patient_member_id}, payer={"name": req.payer_name, "payer_id": req.payer_id}, provider={"npi": req.provider_npi, "tax_id": req.provider_tax_id}, service_type=req.service_type)
    return await ui_test_call(payload, db)


@app.get("/history/export.csv", response_class=PlainTextResponse)
async def history_export(include_demo: bool = False, db: Session = Depends(get_db)) -> str:
    return nextgen_csv(db, include_demo=include_demo)


@app.get("/exports/nextgen/eligibility-results.csv", response_class=PlainTextResponse)
async def nextgen_export(include_demo: bool = False, db: Session = Depends(get_db)) -> str:
    return nextgen_csv(db, include_demo=include_demo)


@app.get("/ui/outbox-status", include_in_schema=False)
async def ui_outbox_status(db: Session = Depends(get_db)) -> dict:
    return outbox_status_counts(db)


@app.post("/work-items/import.csv")
async def import_work_items_csv(file: UploadFile = File(...), is_demo: bool = False, db: Session = Depends(get_db)) -> dict:
    content = await file.read()
    text = content.decode("utf-8")
    rows = csv.DictReader(io.StringIO(text))
    inserted = 0
    updated = 0
    failed = 0
    errors = []
    for idx, row in enumerate(rows, start=2):
        try:
            item, action = upsert_work_item_from_csv_row(db, row, is_demo=is_demo)
            item.source_file_name = file.filename
            item.source_system = "csv_import"
            item.source_row_number = idx
            db.commit()
            if action == "inserted": inserted += 1
            else: updated += 1
        except Exception as exc:
            failed += 1
            errors.append({"row_number": idx, "member_id": row.get("member_id"), "error": str(exc)})
    return {"inserted": inserted, "updated": updated, "failed": failed, "errors": errors}


@app.post("/work-items")
async def create_or_upsert_work_item(payload: dict, db: Session = Depends(get_db)) -> dict:
    item, _ = upsert_work_item_from_csv_row(db, payload, is_demo=bool(payload.get("is_demo", False)), source_system="manual_entry")
    return await get_work_item(item.id, db)


@app.get("/work-items")
async def list_work_items(status: str | None = None, demo: str = "all", db: Session = Depends(get_db)) -> dict:
    q = db.query(VerificationWorkItem)
    if status:
        q = q.filter(VerificationWorkItem.validation_status == status)
    if demo == "only":
        q = q.filter(VerificationWorkItem.is_demo.is_(True))
    elif demo == "exclude":
        q = q.filter(VerificationWorkItem.is_demo.is_(False))
    items = q.order_by(VerificationWorkItem.created_at.desc()).all()
    return {"items": [{"id": i.id, "patient_key": i.patient_key, "first_name": i.first_name, "last_name": i.last_name, "dob": i.dob.isoformat(), "member_id": i.member_id, "payer_name": i.payer_name, "payer_id": i.payer_id, "service_type": i.service_type, "validation_status": i.validation_status, "needs_validation": i.needs_validation, "last_validated_at": i.last_validated_at.isoformat() if i.last_validated_at else None, "last_request_id": i.last_request_id, "updated_at": i.updated_at.isoformat(), "source_system": i.source_system, "source_file_name": i.source_file_name, "source_row_number": i.source_row_number, "notes": i.notes, "manual_override_reason": i.manual_override_reason, "last_error_message": i.last_error_message, "created_at": i.created_at.isoformat(), "is_demo": i.is_demo} for i in items]}


@app.get("/work-items/{item_id:int}")
async def get_work_item(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.query(VerificationWorkItem).filter(VerificationWorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": item.id, "patient_key": item.patient_key, "first_name": item.first_name, "last_name": item.last_name, "dob": item.dob.isoformat(), "member_id": item.member_id, "payer_name": item.payer_name, "payer_id": item.payer_id, "npi": item.npi, "tax_id": item.tax_id, "service_type": item.service_type, "validation_status": item.validation_status, "needs_validation": item.needs_validation, "last_request_id": item.last_request_id, "source_system": item.source_system, "source_file_name": item.source_file_name, "source_row_number": item.source_row_number, "notes": item.notes, "manual_override_reason": item.manual_override_reason, "last_error_message": item.last_error_message, "last_validated_at": item.last_validated_at.isoformat() if item.last_validated_at else None, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "is_demo": item.is_demo}


@app.post("/work-items/{item_id:int}/preview-request")
async def preview_work_item_request(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.query(VerificationWorkItem).filter(VerificationWorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    payload = {
        "patient": {"first_name": item.first_name, "last_name": item.last_name, "dob": item.dob.isoformat(), "member_id": item.member_id},
        "payer": {"name": item.payer_name, "payer_id": item.payer_id},
        "provider": {"npi": item.npi, "tax_id": item.tax_id},
        "service_type": item.service_type,
    }
    return {"work_item_id": item.id, "endpoint": "/eligibility/check", "provider": service.get_provider(), "payload": payload, "explanation": "This is the payload the API endpoint receives."}


@app.patch("/work-items/{item_id:int}")
async def patch_work_item(item_id: int, payload: dict, db: Session = Depends(get_db)) -> dict:
    item = db.query(VerificationWorkItem).filter(VerificationWorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    identity_before = (item.first_name, item.last_name, item.dob, item.member_id, item.payer_id)
    for f in ["first_name","last_name","member_id","payer_name","payer_id","npi","tax_id","service_type","notes","manual_override_reason","source_system","source_file_name","source_row_number"]:
        if f in payload:
            setattr(item, f, payload[f])
    if "dob" in payload:
        item.dob = datetime.fromisoformat(payload["dob"]).date()
    identity_after = (item.first_name, item.last_name, item.dob, item.member_id, item.payer_id)
    if identity_before != identity_after:
        new_key = patient_key_for_row(item.first_name, item.last_name, item.dob, item.member_id, item.payer_id)
        collision = db.query(VerificationWorkItem).filter(VerificationWorkItem.patient_key == new_key, VerificationWorkItem.id != item.id).first()
        if collision:
            raise HTTPException(status_code=409, detail="patient_key collision")
        item.patient_key = new_key
    item.needs_validation = True
    item.validation_status = "needs_revalidation"
    db.commit()
    db.refresh(item)
    return await get_work_item(item.id, db)


async def _validate_work_item(item: VerificationWorkItem, db: Session) -> dict:
    payload = EligibilityRequest(patient={"first_name": item.first_name, "last_name": item.last_name, "dob": item.dob.isoformat(), "member_id": item.member_id}, payer={"name": item.payer_name, "payer_id": item.payer_id}, provider={"npi": item.npi, "tax_id": item.tax_id}, service_type=item.service_type)
    started = datetime.now(timezone.utc)
    req_rec = create_request_record(db, payload, "/work-items/{id}/validate", service.get_provider(), is_demo=item.is_demo)
    try:
        response = await service.check(payload)
        complete_request_success(db, req_rec, response, started)
        item.needs_validation = False
        item.validation_status = "validated"
        item.last_validated_at = datetime.utcnow()
        item.last_request_id = req_rec.request_id
        db.commit()
        db.refresh(item)
        return {"id": item.id, "validation_status": item.validation_status, "last_request_id": item.last_request_id, "source_system": item.source_system, "source_file_name": item.source_file_name, "source_row_number": item.source_row_number, "notes": item.notes, "manual_override_reason": item.manual_override_reason, "last_error_message": item.last_error_message, "last_validated_at": item.last_validated_at.isoformat() if item.last_validated_at else None, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "is_demo": item.is_demo}
    except RuntimeError as exc:
        complete_request_error(db, req_rec, str(exc), started)
        item.validation_status = "failed"
        item.needs_validation = True
        item.last_error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/work-items/{item_id:int}/validate")
async def validate_work_item(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.query(VerificationWorkItem).filter(VerificationWorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return await _validate_work_item(item, db)




@app.post("/work-items/validate-selected")
async def validate_selected_work_items(payload: dict, db: Session = Depends(get_db)) -> dict:
    ids = payload.get("ids") or []
    provider = payload.get("provider")
    if provider is not None:
        provider = str(provider).lower()
        if provider not in get_available_connections():
            raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'")
        service.set_provider(provider)
    provider = service.get_provider()
    results = []
    validated_count = 0
    failed_count = 0
    for item_id in ids:
        item = db.query(VerificationWorkItem).filter(VerificationWorkItem.id == int(item_id)).first()
        if not item:
            failed_count += 1
            results.append({"id": item_id, "status": "failed", "error": "Not found"})
            continue
        try:
            result = await _validate_work_item(item, db)
            validated_count += 1
            results.append({"id": item.id, "status": "validated", "request_id": result.get("last_request_id")})
        except HTTPException as exc:
            failed_count += 1
            results.append({"id": item.id, "status": "failed", "error": str(exc.detail)})
    return {"provider": provider, "requested_count": len(ids), "validated_count": validated_count, "failed_count": failed_count, "results": results}
@app.post("/work-items/validate-pending")
async def validate_pending_work_items(db: Session = Depends(get_db)) -> dict:
    items = db.query(VerificationWorkItem).filter(VerificationWorkItem.needs_validation.is_(True)).all()
    validated = []
    for item in items:
        validated.append(await _validate_work_item(item, db))
    return {"validated_count": len(validated), "items": validated}


@app.get("/work-items/export.csv", response_class=PlainTextResponse)
async def export_work_items_csv(include_demo: bool = False, db: Session = Depends(get_db)) -> str:
    q = db.query(VerificationWorkItem)
    if not include_demo:
        q = q.filter(VerificationWorkItem.is_demo.is_(False))
    items = q.order_by(VerificationWorkItem.created_at.desc()).all()
    out = io.StringIO()
    fields = ["id","first_name","last_name","dob","member_id","payer_name","payer_id","service_type","validation_status","needs_validation","last_validated_at","last_request_id","updated_at"]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for i in items:
        w.writerow({k: (getattr(i, k).isoformat() if k in {"dob","last_validated_at","updated_at"} and getattr(i, k) else getattr(i, k)) for k in fields})
    return out.getvalue()


@app.get("/outbox")
async def outbox_list(demo: str = "all", db: Session = Depends(get_db)) -> dict:
    q = db.query(IntegrationOutbox)
    if demo == "only": q = q.filter(IntegrationOutbox.is_demo.is_(True))
    elif demo == "exclude": q = q.filter(IntegrationOutbox.is_demo.is_(False))
    rows = q.order_by(IntegrationOutbox.created_at.desc()).limit(100).all()
    return {"status_counts": outbox_status_counts(db), "items": [{"id": r.id, "request_id": r.request_id, "target_system": r.target_system, "target_record_type": r.target_record_type, "status": r.status, "created_at": r.created_at.isoformat()} for r in rows]}


@app.get("/outbox/{id}")
async def outbox_item(id: int, db: Session = Depends(get_db)) -> dict:
    row = db.query(IntegrationOutbox).filter(IntegrationOutbox.id == id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": row.id, "request_id": row.request_id, "status": row.status, "payload_json": row.payload_json}


@app.patch("/outbox/{id}")
async def outbox_patch(id: int, payload: dict, db: Session = Depends(get_db)) -> dict:
    row = db.query(IntegrationOutbox).filter(IntegrationOutbox.id == id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.status = payload.get("status", row.status)
    db.commit()
    return {"id": row.id, "status": row.status}


@app.get("/outbox/export.csv", response_class=PlainTextResponse)
async def outbox_export(include_demo: bool = False, db: Session = Depends(get_db)) -> str:
    q = db.query(IntegrationOutbox)
    if not include_demo:
        q = q.filter(IntegrationOutbox.is_demo.is_(False))
    rows = q.order_by(IntegrationOutbox.created_at.desc()).all()
    out = io.StringIO()
    fields = ["id","request_id","target_system","target_record_type","status","created_at"]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow({"id": r.id, "request_id": r.request_id, "target_system": r.target_system, "target_record_type": r.target_record_type, "status": r.status, "created_at": r.created_at.isoformat()})
    return out.getvalue()
