"""
Allure TestOps Importer - Web UI
Run: python app.py   |   Open: http://localhost:5000
"""

import csv
import io
import os

import requests as req
from dotenv import load_dotenv, set_key
from flask import Flask, jsonify, render_template_string, request, Response

from importer import (
    add_steps,
    build_labels,
    fetch_existing_names,
    format_field,
    load_config,
    parse_scenario,
)

app = Flask(__name__)
app.secret_key = "allure-importer-ui"

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yml")
ENV_PATH    = os.path.join(BASE_DIR, "env.env")

load_dotenv(ENV_PATH)

# CSV template columns — matches the sample file
CSV_TEMPLATE_HEADERS = ["ID", "Precondition", "Name", "Scenario", "expected_result",
                        "Potential Fail Case", "Status", "Notes", "New issues", "Screen recording"]
CSV_TEMPLATE_EXAMPLE = [
    "TC-001",
    "1. User is logged in 2. Feature is enabled",
    "My test case name",
    "1. Open the dashboard 2. Click Settings 3. Verify page loads",
    "*Expected result one *Expected result two",
    "", "Passed", "", "", ""
]

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Allure Importer</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}

/* ---- header ---- */
header{background:#1a1d27;border-bottom:1px solid #2d3148;padding:14px 28px;display:flex;align-items:center;gap:12px}
.logo{width:28px;height:28px;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:7px;display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;font-size:14px;flex-shrink:0}
header h1{font-size:15px;font-weight:600;color:#f1f5f9;flex:1}
.header-actions{display:flex;gap:8px;align-items:center}

/* ---- layout ---- */
.page{max-width:1100px;margin:0 auto;padding:24px 20px;display:flex;flex-direction:column;gap:20px}

/* ---- cards ---- */
.card{background:#1a1d27;border:1px solid #2d3148;border-radius:12px;overflow:hidden}
.card-head{padding:14px 18px;border-bottom:1px solid #2d3148;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.step-num{width:22px;height:22px;border-radius:50%;background:#2d3148;color:#94a3b8;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.step-num.active{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff}
.step-num.done{background:#0f2a1e;color:#4ade80}
.card-head h2{font-size:13px;font-weight:600;color:#f1f5f9}
.card-head .hint{margin-left:auto;font-size:11px;color:#475569}
.card-body{padding:18px}

/* ---- settings panel ---- */
.settings-panel{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center}
.settings-panel.open{display:flex}
.settings-box{background:#1a1d27;border:1px solid #2d3148;border-radius:14px;width:100%;max-width:520px;margin:20px}
.settings-box .sh{padding:16px 20px;border-bottom:1px solid #2d3148;display:flex;align-items:center;justify-content:space-between}
.settings-box .sh h2{font-size:14px;font-weight:600}
.settings-box .sb{padding:20px;display:flex;flex-direction:column;gap:16px}
.field-group{display:flex;flex-direction:column;gap:6px}
.field-group label{font-size:11px;color:#475569;text-transform:uppercase;letter-spacing:.05em}
.field-input{background:#0f1117;border:1px solid #2d3148;border-radius:7px;padding:9px 12px;color:#e2e8f0;font-size:13px;outline:none;width:100%}
.field-input:focus{border-color:#6366f1}
.field-input::placeholder{color:#3f4568}
.field-row{display:flex;gap:10px}
.field-row .field-group{flex:1}
.field-row .field-group.narrow{flex:0 0 110px}
.auth-status{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:7px;font-size:12px;margin-top:4px}
.auth-ok   {background:#0a2218;border:1px solid #14532d;color:#4ade80}
.auth-fail {background:#200a0a;border:1px solid #7f1d1d;color:#f87171}
.auth-idle {background:#1e2035;border:1px solid #2d3148;color:#64748b}
.settings-footer{padding:14px 20px;border-top:1px solid #2d3148;display:flex;gap:10px;justify-content:flex-end}

/* ---- drop zone ---- */
.drop-zone{border:2px dashed #2d3148;border-radius:10px;padding:32px 20px;text-align:center;cursor:pointer;transition:.2s;position:relative;background:#13151f}
.drop-zone:hover,.drop-zone.over{border-color:#6366f1;background:#1a1b30}
.drop-zone input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.drop-zone .dz-icon{font-size:28px;margin-bottom:8px}
.drop-zone p{color:#94a3b8;font-size:14px}
.drop-zone small{color:#3f4568;font-size:12px;margin-top:5px;display:block}

/* ---- folder form ---- */
.folder-form{margin-top:16px;background:#13151f;border:1px solid #2d3148;border-radius:10px;padding:16px}
.folder-form h3{font-size:12px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px}
.folder-grid{display:flex;gap:12px;flex-wrap:wrap}
.folder-grid .fg{flex:1;min-width:180px}
.folder-grid .fg.narrow{flex:0 0 110px}
.folder-status{margin-top:10px;font-size:12px;color:#475569}
.folder-status.set{color:#4ade80}

/* ---- alerts ---- */
.alert{display:flex;align-items:flex-start;gap:10px;padding:11px 14px;border-radius:7px;font-size:12px;margin-top:10px}
.alert-info {background:#1e2035;border:1px solid #2d3148;color:#94a3b8;display:none}
.alert-warn {background:#1c1a0a;border:1px solid #713f12;color:#fbbf24;display:none}
.alert-error{background:#200a0a;border:1px solid #7f1d1d;color:#f87171;display:none}
.alert.show{display:flex}
.spin{width:13px;height:13px;border:2px solid #4c1d95;border-top-color:#a78bfa;border-radius:50%;animation:spin .7s linear infinite;flex-shrink:0;margin-top:1px}
@keyframes spin{to{transform:rotate(360deg)}}

/* ---- table ---- */
.tbl-wrap{overflow-x:auto;border-radius:9px;border:1px solid #2d3148;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:12px}
thead tr{background:#141620}
th{padding:8px 12px;text-align:left;color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:500;white-space:nowrap;border-bottom:1px solid #2d3148}
tbody tr{border-bottom:1px solid #1e2035;transition:background .1s}
tbody tr:last-child{border-bottom:none}
tbody tr:hover{background:#1a1d27}
td{padding:9px 12px;vertical-align:top;color:#cbd5e1}
.td-name{font-weight:500;color:#f1f5f9;min-width:180px;max-width:260px}
.td-pre,.td-exp{white-space:pre-line;font-size:11px;color:#94a3b8;min-width:140px;max-width:200px;line-height:1.5}
.td-steps{min-width:180px;max-width:260px}
.steps-ul{list-style:none}
.steps-ul li{font-size:11px;color:#94a3b8;padding:1px 0}
.steps-ul li::before{content:"-> ";color:#3f4568}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:600}
.b-count{background:#1e2035;color:#64748b}
.b-yes{background:#0a2218;color:#4ade80}
.b-no{background:#1e2035;color:#475569}
.b-skip{background:#1c1a0a;color:#fbbf24}
.row-skip td{opacity:.4}

/* ---- buttons ---- */
.btn{padding:8px 18px;border-radius:7px;border:none;font-size:12px;font-weight:600;cursor:pointer;transition:.15s;display:inline-flex;align-items:center;gap:6px}
.btn-primary{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff}
.btn-primary:hover{opacity:.9;transform:translateY(-1px)}
.btn-primary:disabled{opacity:.35;cursor:not-allowed;transform:none}
.btn-dry{background:#0f1e2e;color:#7dd3fc;border:1px solid #1e3a5f}
.btn-dry:hover{background:#1a2f45}
.btn-dry:disabled{opacity:.35;cursor:not-allowed}
.btn-ghost{background:#1e2035;color:#94a3b8;border:1px solid #2d3148}
.btn-ghost:hover{background:#2d3148;color:#e2e8f0}
.btn-sm{padding:6px 12px;font-size:11px}
.btn-icon{padding:7px 10px;font-size:13px}
.actions{display:flex;gap:8px;align-items:center;margin-top:14px;flex-wrap:wrap}
.actions-note{font-size:11px;color:#475569}

/* ---- dry label ---- */
.dry-label{display:none;background:#0f1e2e;color:#7dd3fc;border:1px solid #1e3a5f;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;margin-left:6px}
.dry-label.show{display:inline-block}

/* ---- log ---- */
.log-console{background:#0a0c14;border:1px solid #2d3148;border-radius:9px;padding:16px;font-family:"Cascadia Code","Fira Code",monospace;font-size:11px;line-height:1.9;max-height:380px;overflow-y:auto;margin-top:4px}
.l-ok{color:#4ade80} .l-skip{color:#fbbf24} .l-fail{color:#f87171}
.l-info{color:#475569} .l-head{color:#818cf8;font-weight:bold} .l-dry{color:#7dd3fc}

/* ---- summary ---- */
.summary{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.sum-card{flex:1;min-width:100px;background:#1a1d27;border:1px solid #2d3148;border-radius:9px;padding:12px 14px;text-align:center}
.sum-n{font-size:24px;font-weight:700;margin-bottom:2px}
.sum-l{font-size:10px;color:#475569;text-transform:uppercase;letter-spacing:.05em}
.n-ok{color:#4ade80} .n-skip{color:#fbbf24} .n-fail{color:#f87171}

.hidden{display:none!important}
.divider{height:1px;background:#2d3148;margin:14px 0}

/* connection status */
.conn-status{display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:20px;font-size:11px;font-weight:500;border:1px solid transparent;cursor:default}
.conn-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.conn-unknown{background:#1e2035;border-color:#2d3148;color:#64748b}
.conn-unknown .conn-dot{background:#475569}
.conn-ok{background:#0a2218;border-color:#14532d;color:#4ade80}
.conn-ok .conn-dot{background:#4ade80;box-shadow:0 0 6px #4ade8088}
.conn-fail{background:#200a0a;border-color:#7f1d1d;color:#f87171}
.conn-fail .conn-dot{background:#f87171}
.conn-checking .conn-dot{background:#a78bfa;animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
</style>
</head>
<body>

<header>
  <div class="logo">A</div>
  <h1>Allure TestOps Importer</h1>
  <div class="header-actions">
    <div id="conn-status" class="conn-status conn-unknown" title="Connection status">
      <span class="conn-dot"></span>
      <span class="conn-label">Checking...</span>
    </div>
    <a href="/template" class="btn btn-ghost btn-sm" download="test_cases_template.csv">Download CSV template</a>
    <button class="btn btn-ghost btn-sm" onclick="openSettings()">Settings</button>
  </div>
</header>

<!-- Settings modal -->
<div class="settings-panel" id="settings-panel">
  <div class="settings-box">
    <div class="sh">
      <h2>Settings</h2>
      <button class="btn btn-ghost btn-sm" onclick="closeSettings()">Close</button>
    </div>
    <div class="sb">
      <div class="field-group">
        <label>Allure URL</label>
        <input class="field-input" id="cfg-url" placeholder="https://your-allure-instance.com"/>
      </div>
      <div class="field-group">
        <label>API Token</label>
        <input class="field-input" id="cfg-token" type="password" placeholder="Paste your Allure API token"/>
        <small style="font-size:11px;color:#3f4568;margin-top:4px">Profile -> API Tokens -> Generate new token</small>
      </div>
      <div class="field-group">
        <label>Project ID</label>
        <input class="field-input" id="cfg-project-id" placeholder="e.g. 34" style="width:120px"/>
      </div>
      <div id="auth-status" class="auth-status auth-idle">Not verified yet</div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost" onclick="testAuth()"><span id="auth-spin" class="spin" style="display:none"></span> Test connection</button>
        <button class="btn btn-primary" onclick="saveSettings()">Save</button>
      </div>
    </div>
    <div class="settings-footer">
      <small style="font-size:11px;color:#3f4568">Settings are saved to env.env and config.yml in your project folder</small>
    </div>
  </div>
</div>

<!-- Column mapper modal -->
<div class="settings-panel" id="mapper-panel">
  <div class="settings-box" style="max-width:600px">
    <div class="sh">
      <h2>Map your CSV columns</h2>
      <small style="font-size:11px;color:#475569">Your CSV headers don't match the expected names. Map them below.</small>
    </div>
    <div class="sb" id="mapper-body" style="gap:10px">
      <!-- rows injected by JS -->
    </div>
    <div class="settings-footer" style="justify-content:space-between;align-items:center">
      <small style="font-size:11px;color:#3f4568">Unmapped optional fields will be left blank</small>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost" onclick="closeMapper()">Cancel</button>
        <button class="btn btn-primary" onclick="applyMapping()">Apply & Preview</button>
      </div>
    </div>
  </div>
</div>

<!-- Column mapper modal -->
<div class="settings-panel" id="mapper-panel">
  <div class="settings-box" style="max-width:600px">
    <div class="sh">
      <h2>Map your CSV columns</h2>
      <small style="font-size:11px;color:#64748b;margin-left:8px">Match your CSV headers to Allure fields</small>
    </div>
    <div class="sb" id="mapper-body" style="gap:10px;max-height:70vh;overflow-y:auto">
    </div>
    <div class="settings-footer" style="justify-content:space-between;align-items:center">
      <small style="font-size:11px;color:#3f4568">Optional fields can be left unmapped</small>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost" onclick="closeMapper()">Cancel</button>
        <button class="btn btn-primary" onclick="applyMapping()">Apply & Preview</button>
      </div>
    </div>
  </div>
</div>

<div class="page">

  <!-- Step 1: Upload + Folder -->
  <div class="card" id="card-upload">
    <div class="card-head">
      <div class="step-num active" id="num-1">1</div>
      <h2>Upload CSV</h2>
      <span class="hint">Export from Google Sheets -> File -> Download -> CSV</span>
    </div>
    <div class="card-body">
      <div class="drop-zone" id="drop-zone">
        <input type="file" id="file-input" accept=".csv,.tsv"/>
        <div class="dz-icon">CSV</div>
        <p>Drag & drop your CSV here, or click to browse</p>
        <small>Comma or tab separated</small>
      </div>
      <div class="alert alert-info" id="alert-parse">
        <span class="spin"></span><span>Parsing and checking for duplicates...</span>
      </div>
      <div class="alert alert-error" id="alert-parse-err"></div>

      <div class="divider"></div>

      <!-- Folder form -->
      <div class="folder-form">
        <h3>Destination folder in Allure</h3>
        <div class="folder-grid">
          <div class="field-group fg">
            <label>Feature folder name</label>
            <input class="field-input" id="input-feature-name" placeholder="e.g. Remote vs Office"/>
          </div>
          <div class="field-group fg narrow">
            <label>Feature ID</label>
            <input class="field-input" id="input-feature-id" placeholder="e.g. 5162"/>
          </div>
        </div>
        <div class="folder-grid" style="margin-top:10px">
          <div class="field-group fg">
            <label>Story folder name <span style="color:#3f4568;font-weight:400;text-transform:none;letter-spacing:0">(optional)</span></label>
            <input class="field-input" id="input-story-name" placeholder="e.g. Benchmarks"/>
          </div>
          <div class="field-group fg narrow">
            <label>Story ID <span style="color:#3f4568;font-weight:400;text-transform:none;letter-spacing:0">(optional)</span></label>
            <input class="field-input" id="input-story-id" placeholder="e.g. 5163"/>
          </div>
        </div>
        <div class="folder-status" id="folder-status">Will use config.yml default if left empty</div>
      </div>

    </div>
  </div>

  <!-- Step 2: Preview -->
  <div class="card hidden" id="card-preview">
    <div class="card-head">
      <div class="step-num" id="num-2">2</div>
      <h2>Review parsed test cases</h2>
      <span class="hint" id="preview-hint"></span>
    </div>
    <div class="card-body">
      <div class="alert alert-warn hidden" id="alert-dupes"></div>
      <div class="alert alert-info hidden" id="alert-recheck">
        <span class="spin"></span><span>Re-checking duplicates...</span>
      </div>
      <div class="tbl-wrap">
        <table>
          <thead>
            <tr><th>#</th><th>Name</th><th>Precondition</th><th>Steps</th><th>Expected Result</th><th>Auto</th><th>Status</th></tr>
          </thead>
          <tbody id="tbl-body"></tbody>
        </table>
      </div>
      <div class="actions">
        <button class="btn btn-primary" id="btn-import" onclick="runAction('import')">Import to Allure</button>
        <button class="btn btn-dry" id="btn-dry" onclick="runAction('dry-run')">Dry Run</button>
        <button class="btn btn-ghost btn-sm" onclick="recheckDupes()">Re-check duplicates</button>
        <button class="btn btn-ghost btn-sm" onclick="resetAll()">Upload different file</button>
        <span class="actions-note" id="actions-note"></span>
      </div>
    </div>
  </div>

  <!-- Step 3: Log -->
  <div class="card hidden" id="card-log">
    <div class="card-head">
      <div class="step-num" id="num-3">3</div>
      <h2 id="log-title">Import log</h2>
      <span class="dry-label" id="dry-label">DRY RUN</span>
      <span class="hint" id="log-hint">Running...</span>
    </div>
    <div class="card-body">
      <div class="log-console" id="log-console"></div>
      <div class="summary hidden" id="summary"></div>
      <div class="actions" style="margin-top:14px">
        <button class="btn btn-ghost btn-sm" onclick="backToPreview()"><- Back to preview</button>
        <button class="btn btn-ghost btn-sm" onclick="resetAll()">Upload another file</button>
      </div>
    </div>
  </div>

</div>

<script>
let parsedRows   = [];
let dupeSet      = new Set();

// ---- Connection status ---------------------------------------------------
function checkConnection() {
  setConnStatus('checking', 'Checking...');
  fetch('/auth-test', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url: '', token: '__saved__'})
  })
  .then(r => r.json())
  .then(r => setConnStatus(r.ok ? 'ok' : 'fail', r.ok ? 'Connected' : (r.error || 'Auth failed')))
  .catch(() => setConnStatus('fail', 'Unreachable'));
}
function setConnStatus(type, label) {
  const el = document.getElementById('conn-status');
  el.className = 'conn-status conn-' + type;
  el.querySelector('.conn-label').textContent = label;
  el.title = label;
}

// ---- Column mapper -------------------------------------------------------
let pendingRawRows = [];
let csvHeaders     = [];

const ALLURE_FIELDS = [
  { key:'name',            label:'Name',           required:true  },
  { key:'precondition',    label:'Precondition',   required:false },
  { key:'scenario',        label:'Scenario/Steps', required:false },
  { key:'expected_result', label:'Expected Result',required:false },
  { key:'description',     label:'Description',    required:false },
  { key:'automated',       label:'Automated',      required:false },
  { key:'tag',             label:'Tag',            required:false },
  { key:'lead',            label:'Lead',           required:false },
  { key:'owner',           label:'Owner',          required:false },
];

function openMapper(rawRows, headers) {
  pendingRawRows = rawRows;
  csvHeaders     = headers;
  const body = document.getElementById('mapper-body');
  function guess(fieldKey) {
    const fl = fieldKey.toLowerCase().replace(/[^a-z]/g,'');
    return headers.find(h => h.toLowerCase().replace(/[^a-z]/g,'') === fl) || '';
  }
  body.innerHTML = ALLURE_FIELDS.map(f => `
    <div style="display:flex;align-items:center;gap:12px;padding:4px 0">
      <div style="width:150px;font-size:12px;color:${f.required?'#e2e8f0':'#94a3b8'};font-weight:${f.required?600:400}">
        ${f.label}${f.required?' <span style="color:#f87171">*</span>':''}
      </div>
      <div style="flex:1">
        <select class="field-input" id="map-${f.key}" style="cursor:pointer">
          <option value="">${f.required ? '-- select column --' : '-- not mapped --'}</option>
          ${headers.map(h => '<option value="'+esc(h)+'" '+(guess(f.key)===h?'selected':'')+'>'+esc(h)+'</option>').join('')}
        </select>
      </div>
    </div>`).join('');
  document.getElementById('mapper-panel').classList.add('open');
}

function closeMapper() {
  document.getElementById('mapper-panel').classList.remove('open');
  pendingRawRows = [];
}

function applyMapping() {
  const mapping = {};
  ALLURE_FIELDS.forEach(f => {
    const val = document.getElementById('map-'+f.key).value;
    if (val) mapping[f.key] = val;
  });
  if (!mapping.name) { alert('Name column is required'); return; }
  document.getElementById('mapper-panel').classList.remove('open');
  show('alert-parse');
  fetch('/parse-with-mapping', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({rows: pendingRawRows, mapping})})
  .then(r=>r.json())
  .then(data => {
    hide('alert-parse');
    if (data.error) { showErr('alert-parse-err', 'Error: '+data.error); return; }
    parsedRows = data.rows;
    renderPreview(data.rows, data.duplicates||[]);
  })
  .catch(()=>{ hide('alert-parse'); showErr('alert-parse-err', 'Mapping failed'); });
}

// ---- Settings ------------------------------------------------------------
function openSettings() {
  fetch('/settings').then(r=>r.json()).then(d => {
    document.getElementById('cfg-url').value        = d.allure_url || '';
    document.getElementById('cfg-token').value      = d.allure_token ? '********' : '';
    document.getElementById('cfg-project-id').value = d.project_id  || '';
    setAuthStatus('idle', 'Not verified');
  });
  document.getElementById('settings-panel').classList.add('open');
}
function closeSettings() {
  document.getElementById('settings-panel').classList.remove('open');
}
function setAuthStatus(type, msg) {
  const el = document.getElementById('auth-status');
  el.className = 'auth-status auth-' + type;
  el.textContent = msg;
}
function testAuth() {
  const url   = document.getElementById('cfg-url').value.trim();
  const token = document.getElementById('cfg-token').value.trim();
  if (!url || !token || token === '********') {
    setAuthStatus('fail', 'Enter URL and token first'); return;
  }
  document.getElementById('auth-spin').style.display = 'inline-block';
  setAuthStatus('idle', 'Testing...');
  fetch('/auth-test', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({url, token})
  }).then(r=>r.json()).then(d => {
    document.getElementById('auth-spin').style.display = 'none';
    if (d.ok) setAuthStatus('ok', 'Connected successfully');
    else      setAuthStatus('fail', 'Failed: ' + (d.error || 'unknown error'));
  }).catch(() => {
    document.getElementById('auth-spin').style.display = 'none';
    setAuthStatus('fail', 'Request failed');
  });
}
function saveSettings() {
  const url   = document.getElementById('cfg-url').value.trim();
  const token = document.getElementById('cfg-token').value.trim();
  const pid   = document.getElementById('cfg-project-id').value.trim();
  fetch('/settings', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({allure_url: url, allure_token: token, project_id: pid})
  }).then(r=>r.json()).then(d => {
    if (d.ok) { closeSettings(); loadConfigFolder(); checkConnection(); }
    else alert('Save failed: ' + (d.error || 'unknown'));
  });
}

// ---- Folder form ---------------------------------------------------------
window.addEventListener('DOMContentLoaded', () => {
  checkConnection();
  loadConfigFolder();
  ['input-feature-name','input-feature-id','input-story-name','input-story-id']
    .forEach(id => document.getElementById(id).addEventListener('input', updateFolderStatus));
});

function loadConfigFolder() {
  fetch('/config-folder').then(r=>r.json()).then(d => {
    if (d.feature_name) document.getElementById('input-feature-name').value = d.feature_name;
    if (d.feature_id)   document.getElementById('input-feature-id').value   = d.feature_id;
    if (d.story_name)   document.getElementById('input-story-name').value   = d.story_name || '';
    if (d.story_id)     document.getElementById('input-story-id').value     = d.story_id   || '';
    updateFolderStatus();
  }).catch(()=>{});
}

function getFolderFromInputs() {
  const fname = document.getElementById('input-feature-name').value.trim();
  const fid   = parseInt(document.getElementById('input-feature-id').value.trim(), 10);
  const sname = document.getElementById('input-story-name').value.trim();
  const sid   = parseInt(document.getElementById('input-story-id').value.trim(), 10);
  if (!fname || !fid) return null;
  return { featureId: fid, featureName: fname,
           storyId: (sname && sid) ? sid : null,
           storyName: (sname && sid) ? sname : null };
}

function updateFolderStatus() {
  const f  = getFolderFromInputs();
  const el = document.getElementById('folder-status');
  if (!f) { el.textContent = 'Will use config.yml default if left empty'; el.className='folder-status'; }
  else {
    const path = f.storyName ? `${f.featureName} / ${f.storyName}` : f.featureName;
    el.textContent = 'Will import into: ' + path + '  (ID ' + f.featureId + ')';
    el.className = 'folder-status set';
  }
}

// ---- Drag & drop ---------------------------------------------------------
const zone = document.getElementById('drop-zone');
zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('over'); });
zone.addEventListener('dragleave', () => zone.classList.remove('over'));
zone.addEventListener('drop', e => {
  e.preventDefault(); zone.classList.remove('over');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
document.getElementById('file-input').addEventListener('change', e => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
});

function handleFile(file) {
  show('alert-parse'); hide('alert-parse-err');
  const fd = new FormData(); fd.append('file', file);
  fetch('/parse', {method:'POST', body:fd})
    .then(r=>r.json())
    .then(data => {
      hide('alert-parse');
      if (data.error) { showErr('alert-parse-err', 'Error: ' + data.error); return; }
      // If server detected column mismatch, open the mapper
      if (data.needs_mapping) {
        openMapper(data.raw_rows, data.headers);
        return;
      }
      parsedRows = data.rows;
      renderPreview(data.rows, data.duplicates || []);
    })
    .catch(() => { hide('alert-parse'); showErr('alert-parse-err', 'Could not connect. Is app.py running?'); });
}

// ---- Re-check ------------------------------------------------------------
function recheckDupes() {
  const btn = document.querySelector('[onclick="recheckDupes()"]');
  btn.disabled = true; btn.textContent = 'Checking...';
  clearDupeWarning(); showInfo('alert-recheck');
  fetch('/check-dupes', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({names: parsedRows.map(r=>r.name)})})
  .then(r=>r.json())
  .then(d => {
    hideEl('alert-recheck'); btn.disabled=false; btn.textContent='Re-check duplicates';
    if (d.error) { showErr('alert-parse-err', d.error); return; }
    renderPreview(parsedRows, d.duplicates||[]);
  })
  .catch(()=>{ hideEl('alert-recheck'); btn.disabled=false; btn.textContent='Re-check duplicates'; });
}

// ---- Preview table -------------------------------------------------------
function renderPreview(rows, dupes) {
  const newCount = rows.length - dupes.length;
  dupeSet = new Set(dupes.map(d=>d.toLowerCase()));
  markDone(1); markActive(2);
  document.getElementById('preview-hint').textContent =
    `${rows.length} total - ${newCount} new - ${dupes.length} skip`;
  clearDupeWarning();
  if (dupes.length)
    showWarn('alert-dupes', `${dupes.length} test case${dupes.length>1?'s':''} already exist in Allure and will be skipped.`);
  document.getElementById('actions-note').textContent =
    newCount===0 ? 'Nothing new - all already exist.' : `${newCount} will be created.`;
  document.getElementById('btn-import').disabled = newCount===0;
  document.getElementById('btn-dry').disabled    = rows.length===0;

  const tbody = document.getElementById('tbl-body');
  tbody.innerHTML = '';
  rows.forEach((row,i) => {
    const skip  = dupeSet.has((row.name||'').toLowerCase());
    const steps = row.steps||[];
    tbody.innerHTML += `
      <tr class="${skip?'row-skip':''}">
        <td style="color:#3f4568;font-size:11px">${i+1}</td>
        <td class="td-name">${esc(row.name||'')}</td>
        <td class="td-pre">${esc(row.precondition||'-')}</td>
        <td class="td-steps">${steps.length
          ? `<ul class="steps-ul">${steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`
          : '<span style="color:#3f4568">-</span>'}
          <span class="badge b-count">${steps.length} step${steps.length!==1?'s':''}</span></td>
        <td class="td-exp">${esc(row.expected_result||'-')}</td>
        <td>${row.automated?'<span class="badge b-yes">yes</span>':'<span class="badge b-no">no</span>'}</td>
        <td>${skip?'<span class="badge b-skip">skip</span>':'<span class="badge b-yes">import</span>'}</td>
      </tr>`;
  });
  document.getElementById('card-preview').classList.remove('hidden');
  document.getElementById('card-preview').scrollIntoView({behavior:'smooth',block:'start'});
}

// ---- Import / Dry-run ----------------------------------------------------
function runAction(mode) {
  const isDry = mode==='dry-run';
  const btn   = document.getElementById(isDry?'btn-dry':'btn-import');
  btn.disabled=true;
  btn.innerHTML = isDry ? '<span class="spin"></span> Running...' : '<span class="spin"></span> Importing...';
  document.getElementById('log-title').textContent = isDry ? 'Dry run preview' : 'Import log';
  document.getElementById('dry-label').className   = isDry ? 'dry-label show' : 'dry-label';
  document.getElementById('log-hint').textContent  = 'Running...';
  document.getElementById('log-console').innerHTML = '';
  document.getElementById('summary').classList.add('hidden');
  document.getElementById('card-log').classList.remove('hidden');
  markActive(3);
  document.getElementById('card-log').scrollIntoView({behavior:'smooth',block:'start'});

  fetch('/import', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({rows: parsedRows, dry_run: isDry, folder: getFolderFromInputs()})})
  .then(r=>r.json())
  .then(data => {
    btn.disabled=false;
    btn.innerHTML = isDry ? 'Dry Run' : 'Import to Allure';
    if (data.error) { appendLog('[fail] '+data.error,'l-fail'); document.getElementById('log-hint').textContent='Failed'; return; }
    (data.log||[]).forEach(line => {
      if      (line.startsWith('[ok]'))      appendLog(line,'l-ok');
      else if (line.startsWith('[skip]'))    appendLog(line,'l-skip');
      else if (line.startsWith('[fail]'))    appendLog(line,'l-fail');
      else if (line.startsWith('[dry-run]')) appendLog(line,'l-dry');
      else if (line.startsWith('==='))       appendLog(line,'l-head');
      else                                   appendLog(line,'l-info');
    });
    markDone(3);
    document.getElementById('log-hint').textContent = isDry ? 'Dry run complete - no changes made' : 'Finished';
    const s = data.summary||{};
    document.getElementById('summary').classList.remove('hidden');
    document.getElementById('summary').innerHTML = isDry
      ? `<div class="sum-card"><div class="sum-n" style="color:#7dd3fc">${s.would_create||0}</div><div class="sum-l">Would create</div></div>
         <div class="sum-card"><div class="sum-n n-skip">${s.would_skip||0}</div><div class="sum-l">Would skip</div></div>`
      : `<div class="sum-card"><div class="sum-n n-ok">${s.created||0}</div><div class="sum-l">Created</div></div>
         <div class="sum-card"><div class="sum-n n-skip">${s.skipped||0}</div><div class="sum-l">Skipped</div></div>
         <div class="sum-card"><div class="sum-n n-fail">${s.failed||0}</div><div class="sum-l">Failed</div></div>`;
  })
  .catch(()=>{
    btn.disabled=false; btn.innerHTML=isDry?'Dry Run':'Import to Allure';
    appendLog('[fail] Request failed','l-fail'); document.getElementById('log-hint').textContent='Error';
  });
}

function backToPreview() {
  document.getElementById('card-log').classList.add('hidden');
  document.getElementById('card-preview').scrollIntoView({behavior:'smooth',block:'start'});
  markActive(2); unmark(3);
}

function resetAll() {
  parsedRows=[]; dupeSet=new Set();
  document.getElementById('file-input').value='';
  document.getElementById('tbl-body').innerHTML='';
  hide('alert-parse'); hide('alert-parse-err');
  clearDupeWarning(); hideEl('alert-recheck');
  document.getElementById('card-preview').classList.add('hidden');
  document.getElementById('card-log').classList.add('hidden');
  document.getElementById('log-console').innerHTML='';
  document.getElementById('summary').classList.add('hidden');
  markActive(1); unmark(2); unmark(3);
  window.scrollTo({top:0,behavior:'smooth'});
}

// ---- Helpers -------------------------------------------------------------
function appendLog(t,c){ const b=document.getElementById('log-console'),d=document.createElement('div'); d.className=c; d.textContent=t; b.appendChild(d); b.scrollTop=b.scrollHeight; }
function clearDupeWarning(){ const el=document.getElementById('alert-dupes'); el.textContent=''; el.classList.remove('show'); el.classList.add('hidden'); }
function show(id)    { document.getElementById(id).classList.add('show'); }
function hide(id)    { document.getElementById(id).classList.remove('show'); }
function hideEl(id)  { const el=document.getElementById(id); el.classList.remove('show'); el.classList.add('hidden'); }
function showInfo(id){ const el=document.getElementById(id); el.classList.remove('hidden'); el.classList.add('show'); }
function showErr(id,msg){ const el=document.getElementById(id); el.textContent=msg; el.classList.add('show'); }
function showWarn(id,msg){ const el=document.getElementById(id); el.textContent=msg; el.classList.remove('hidden'); el.classList.add('show'); }
function markDone(n) { const el=document.getElementById('num-'+n); el.className='step-num done'; el.textContent='v'; }
function markActive(n){ document.getElementById('num-'+n).className='step-num active'; }
function unmark(n)   { document.getElementById('num-'+n).className='step-num'; }
function esc(s)      { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>
</body>
</html>"""


# ---- Helpers ----------------------------------------------------------------

def read_csv_rows(file_bytes):
    text    = file_bytes.decode("utf-8-sig")
    dialect = "excel-tab" if "\t" in text[:300] else "excel"
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def parse_rows(raw_rows, cfg):
    col = cfg.get("columns", {})
    out = []
    for row in raw_rows:
        def get(key, fallback):
            return (row.get(col.get(key, fallback), "")
                    or row.get(fallback, "")
                    or row.get(fallback.capitalize(), "")
                    or "").strip()
        steps = parse_scenario(get("scenario", "scenario"))
        out.append({
            "name":            get("name", "name"),
            "precondition":    format_field(get("precondition", "precondition")),
            "expected_result": format_field(get("expected_result", "expected_result")),
            "description":     get("description", "description"),
            "automated":       get("automated", "automated").upper() == "TRUE",
            "labels":          build_labels(row, col),
            "steps":           steps,
        })
    return out


def allure_creds(cfg):
    url   = (os.getenv("ALLURE_URL") or cfg["allure"].get("url", "")).rstrip("/")
    token = os.getenv(cfg["allure"].get("token_env", "ALLURE_TOKEN"))
    return url, token


def safe_jwt(url, token):
    resp = req.post(
        f"{url}/api/uaa/oauth/token",
        data={"grant_type": "apitoken", "scope": "openid", "token": token},
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    jwt = resp.json().get("access_token")
    if not jwt:
        raise ValueError("Allure returned no access_token - check your ALLURE_TOKEN")
    return jwt


def get_headers(jwt):
    return {"Content-Type": "application/json", "Authorization": f"Bearer {jwt}"}


def build_custom_fields_for_folder(cfg, folder):
    if not folder:
        from importer import build_custom_fields_payload
        return build_custom_fields_payload(cfg)
    fields = []
    if folder.get("featureId"):
        fields.append({"id": folder["featureId"], "name": folder["featureName"],
                        "customField": {"id": -2, "name": "Feature"}})
    if folder.get("storyId"):
        fields.append({"id": folder["storyId"], "name": folder["storyName"],
                        "customField": {"id": -3, "name": "Story"}})
    return fields


# ---- Routes -----------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/template")
def template_endpoint():
    """Download a CSV template pre-filled with one example row."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_TEMPLATE_HEADERS)
    writer.writerow(CSV_TEMPLATE_EXAMPLE)
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=test_cases_template.csv"}
    )


@app.route("/settings", methods=["GET"])
def settings_get():
    try:
        cfg = load_config(CONFIG_PATH)
    except SystemExit:
        cfg = {}
    url, token = allure_creds(cfg) if cfg else ("", "")
    return jsonify({
        "allure_url":   url,
        "allure_token": "set" if token else "",
        "project_id":   cfg.get("project", {}).get("id", "") if cfg else "",
    })


@app.route("/settings", methods=["POST"])
def settings_save():
    data      = request.get_json() or {}
    allure_url   = data.get("allure_url", "").strip()
    allure_token = data.get("allure_token", "").strip()
    project_id   = data.get("project_id", "").strip()

    try:
        # Save token + URL to env.env
        if not os.path.exists(ENV_PATH):
            open(ENV_PATH, "w").close()
        if allure_url:
            set_key(ENV_PATH, "ALLURE_URL", allure_url)
        if allure_token and allure_token != "********":
            set_key(ENV_PATH, "ALLURE_TOKEN", allure_token)
        # Reload env
        load_dotenv(ENV_PATH, override=True)

        # Update project ID in config.yml
        if project_id:
            import yaml
            cfg_path = CONFIG_PATH
            if os.path.exists(cfg_path):
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            else:
                cfg = {}
            cfg.setdefault("project", {})["id"] = int(project_id)
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/auth-test", methods=["POST"])
def auth_test():
    data  = request.get_json() or {}
    url   = data.get("url", "").strip().rstrip("/")
    token = data.get("token", "").strip()

    # __saved__ = use whatever is in env.env right now (reload to pick up saves)
    if token == "__saved__" or not token or token == "********":
        load_dotenv(ENV_PATH, override=True)
        try:
            cfg   = load_config(CONFIG_PATH)
            url2, token2 = allure_creds(cfg)
            if not url:   url   = url2
            if not token or token in ("__saved__", "********"):
                token = token2
        except Exception:
            pass

    if not url or not token:
        return jsonify({"ok": False, "error": "Not configured - open Settings"})
    try:
        safe_jwt(url, token)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/config-folder")
def config_folder_endpoint():
    try:
        cfg = load_config(CONFIG_PATH)
        cfs = cfg.get("custom_fields", [])
        result = {}
        for cf in cfs:
            if cf.get("custom_field_id") == -2:
                result["feature_id"]   = cf.get("id")
                result["feature_name"] = cf.get("name", "")
            if cf.get("custom_field_id") == -3:
                result["story_id"]   = cf.get("id")
                result["story_name"] = cf.get("name", "")
        return jsonify(result)
    except Exception:
        return jsonify({})


ALLURE_REQUIRED = {"name", "precondition", "scenario", "expected_result"}
ALLURE_OPTIONAL = {"description", "automated", "tag", "lead", "owner"}
ALLURE_ALL      = ALLURE_REQUIRED | ALLURE_OPTIONAL


def detect_column_mismatch(headers, cfg):
    """Return True if the CSV headers don't cover the required Allure fields via config mapping."""
    col     = cfg.get("columns", {})
    h_lower = {h.lower() for h in headers}
    for field in ["name", "scenario"]:
        mapped = col.get(field, field).lower()
        if mapped not in h_lower and field not in h_lower and field.capitalize().lower() not in h_lower:
            return True
    return False


@app.route("/parse", methods=["POST"])
def parse_endpoint():
    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        cfg = load_config(CONFIG_PATH)
    except SystemExit:
        return jsonify({"error": f"config.yml not found at {CONFIG_PATH}"}), 500
    try:
        raw_bytes = request.files["file"].read()
        raw_rows  = read_csv_rows(raw_bytes)
    except Exception as e:
        return jsonify({"error": f"Could not read CSV: {e}"}), 400
    if not raw_rows:
        return jsonify({"error": "No rows found in the file"}), 400

    headers = list(raw_rows[0].keys())

    # If columns don't match, return raw data so JS can open the mapper
    if detect_column_mismatch(headers, cfg):
        return jsonify({
            "needs_mapping": True,
            "headers":       headers,
            "raw_rows":      [dict(r) for r in raw_rows],
        })

    rows = parse_rows(raw_rows, cfg)
    duplicates = []
    try:
        url, token = allure_creds(cfg)
        if url and token:
            jwt      = safe_jwt(url, token)
            hdrs     = get_headers(jwt)
            existing = fetch_existing_names(url, cfg["project"]["id"], hdrs)
            duplicates = [r["name"] for r in rows if r["name"].lower() in existing]
    except Exception:
        pass
    return jsonify({"rows": rows, "duplicates": duplicates})


@app.route("/parse-with-mapping", methods=["POST"])
def parse_with_mapping_endpoint():
    """Parse raw rows using a user-supplied column mapping from the UI."""
    body    = request.get_json() or {}
    raw_rows = body.get("rows", [])
    mapping  = body.get("mapping", {})  # {allure_field: csv_header}

    if not raw_rows or not mapping:
        return jsonify({"error": "rows and mapping required"}), 400

    try:
        cfg = load_config(CONFIG_PATH)
    except SystemExit:
        return jsonify({"error": "config.yml not found"}), 500

    # Build a synthetic col config from the mapping
    col = {k: v for k, v in mapping.items()}

    out = []
    for row in raw_rows:
        def get(key):
            csv_col = col.get(key, key)
            return (row.get(csv_col) or row.get(key) or row.get(key.capitalize()) or "").strip()

        steps = parse_scenario(get("scenario"))
        out.append({
            "name":            get("name"),
            "precondition":    format_field(get("precondition")),
            "expected_result": format_field(get("expected_result")),
            "description":     get("description"),
            "automated":       get("automated").upper() == "TRUE",
            "labels":          build_labels(row, col),
            "steps":           steps,
        })

    duplicates = []
    try:
        url, token = allure_creds(cfg)
        if url and token:
            jwt      = safe_jwt(url, token)
            hdrs     = get_headers(jwt)
            existing = fetch_existing_names(url, cfg["project"]["id"], hdrs)
            duplicates = [r["name"] for r in out if r["name"].lower() in existing]
    except Exception:
        pass

    return jsonify({"rows": out, "duplicates": duplicates})


@app.route("/check-dupes", methods=["POST"])
def check_dupes_endpoint():
    names = (request.get_json() or {}).get("names", [])
    try:
        cfg = load_config(CONFIG_PATH)
        url, token = allure_creds(cfg)
        if not url or not token:
            return jsonify({"error": "Missing ALLURE_URL or token"}), 500
        jwt      = safe_jwt(url, token)
        headers  = get_headers(jwt)
        existing = fetch_existing_names(url, cfg["project"]["id"], headers)
        return jsonify({"duplicates": [n for n in names if n.lower() in existing]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/import", methods=["POST"])
def import_endpoint():
    body    = request.get_json() or {}
    rows    = body.get("rows", [])
    dry_run = body.get("dry_run", False)
    folder  = body.get("folder")

    if not rows:
        return jsonify({"error": "No rows to import"}), 400
    try:
        cfg = load_config(CONFIG_PATH)
    except SystemExit:
        return jsonify({"error": "config.yml not found"}), 500

    url, token = allure_creds(cfg)
    if not url or not token:
        return jsonify({"error": "Missing ALLURE_URL or token - open Settings to configure"}), 500

    project_id    = cfg["project"]["id"]
    custom_fields = build_custom_fields_for_folder(cfg, folder)
    log           = []

    if folder:
        path = folder.get("featureName", "")
        if folder.get("storyName"):
            path += f" / {folder['storyName']}"
        log.append(f"Destination: {path}")
    else:
        log.append("Destination: config.yml default")
    log.append("-" * 44)

    try:
        log.append("Authenticating...")
        jwt      = safe_jwt(url, token)
        headers  = get_headers(jwt)
        log.append("Authenticated OK")
        existing = fetch_existing_names(url, project_id, headers)
        log.append(f"Found {len(existing)} existing test cases")
        log.append("-" * 44)
    except Exception as e:
        return jsonify({"error": f"Auth failed: {e}"}), 500

    if dry_run:
        counts = {"would_create": 0, "would_skip": 0}
        for row in rows:
            name  = (row.get("name") or "").strip()
            steps = row.get("steps") or []
            if name.lower() in existing:
                log.append(f"[skip] {name}"); counts["would_skip"] += 1
            else:
                log.append(f"[dry-run] Would create: {name}")
                for s in steps: log.append(f"          -> {s}")
                counts["would_create"] += 1
        log.append("-" * 44)
        log.append(f"=== Dry run: {counts['would_create']} would create - {counts['would_skip']} would skip ===")
        return jsonify({"log": log, "summary": counts})

    counts = {"created": 0, "skipped": 0, "failed": 0}
    for row in rows:
        name  = (row.get("name") or "").strip()
        steps = row.get("steps") or []
        if name.lower() in existing:
            log.append(f"[skip] {name}"); counts["skipped"] += 1; continue
        payload = {
            "name": name, "projectId": project_id,
            "automated": row.get("automated", False),
            "description": row.get("description", ""),
            "precondition": row.get("precondition", ""),
            "expectedResult": row.get("expected_result", ""),
            "labels": row.get("labels", []),
            "customFields": custom_fields,
        }
        try:
            resp = req.post(f"{url}/api/rs/testcase", json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            tc_id = resp.json().get("id")
            add_steps(tc_id, steps, headers, url, dry_run=False)
            log.append(f"[ok] {name}  ->  ID {tc_id}  ({len(steps)} steps)")
            counts["created"] += 1; existing.add(name.lower())
        except req.HTTPError as e:
            log.append(f"[fail] {name}  -  {e.response.status_code}: {e.response.text[:180]}")
            counts["failed"] += 1
        except Exception as e:
            log.append(f"[fail] {name}  -  {e}"); counts["failed"] += 1

    log.append("-" * 44)
    log.append(f"=== Done: {counts['created']} created - {counts['skipped']} skipped - {counts['failed']} failed ===")
    return jsonify({"log": log, "summary": counts})


if __name__ == "__main__":
    print("\n  Allure TestOps Importer - Web UI")
    print("  Open in your browser ->  http://localhost:5000\n")
    app.run(debug=False, port=5000)