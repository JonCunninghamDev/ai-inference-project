"""Browser-based walkthrough for the local in-process demo.

The page intentionally uses only inline HTML, CSS, and JavaScript so the demo
remains self-contained and works without CDN or other network dependencies.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


DEMO_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Secure AI Inference Demo</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111f;
      --panel: #0d1b2a;
      --panel-2: #122438;
      --border: #29435d;
      --text: #edf5ff;
      --muted: #9fb3c8;
      --accent: #63d3ff;
      --accent-2: #86efac;
      --warning: #fbbf24;
      --danger: #fb7185;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top right, rgba(99, 211, 255, 0.12), transparent 34rem),
        var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    a { color: inherit; }
    .shell { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 42px 0 72px; }
    .eyebrow { color: var(--accent); font-size: 0.78rem; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 800; }
    h1 { margin: 10px 0 12px; font-size: clamp(2.2rem, 5vw, 4.6rem); line-height: 0.98; max-width: 900px; }
    .lede { color: var(--muted); max-width: 820px; font-size: 1.08rem; line-height: 1.65; }
    .actions { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 34px; }
    .button {
      display: inline-flex; align-items: center; justify-content: center; min-height: 44px;
      padding: 0 16px; border-radius: 10px; border: 1px solid var(--border);
      background: var(--panel-2); color: var(--text); text-decoration: none; font-weight: 750; cursor: pointer;
    }
    .button.primary { background: var(--accent); color: #03121d; border-color: transparent; }
    .button:disabled { opacity: 0.5; cursor: wait; }
    .grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr); gap: 18px; }
    .panel { background: rgba(13, 27, 42, 0.94); border: 1px solid var(--border); border-radius: 18px; padding: 22px; box-shadow: 0 18px 60px rgba(0,0,0,0.18); }
    .panel h2 { margin: 0 0 8px; font-size: 1.15rem; }
    .panel p { color: var(--muted); line-height: 1.55; }
    label { display: block; margin: 18px 0 7px; font-size: 0.84rem; font-weight: 800; color: #cfe2f5; }
    textarea, input {
      width: 100%; border: 1px solid var(--border); border-radius: 10px; background: #081522;
      color: var(--text); padding: 12px 13px; font: inherit; outline: none;
    }
    textarea { min-height: 116px; resize: vertical; }
    textarea:focus, input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(99,211,255,0.1); }
    .pipeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
    .stage {
      min-height: 92px; padding: 12px; border: 1px solid var(--border); border-radius: 12px;
      background: #081522; transition: border-color .18s ease, transform .18s ease, background .18s ease;
    }
    .stage strong { display: block; font-size: 0.83rem; }
    .stage span { display: block; color: var(--muted); font-size: 0.73rem; margin-top: 7px; line-height: 1.35; }
    .stage.active { border-color: var(--warning); background: rgba(251,191,36,0.08); transform: translateY(-2px); }
    .stage.done { border-color: var(--accent-2); background: rgba(134,239,172,0.08); }
    .stage.failed { border-color: var(--danger); background: rgba(251,113,133,0.08); }
    .status-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 16px; }
    .metric { border: 1px solid var(--border); border-radius: 10px; padding: 12px; background: #081522; }
    .metric small { display: block; color: var(--muted); margin-bottom: 6px; }
    .metric code { color: #d8f2ff; word-break: break-all; }
    .log { margin-top: 14px; min-height: 250px; max-height: 420px; overflow: auto; border-radius: 12px; background: #050d16; border: 1px solid #1f3448; padding: 14px; }
    .log-line { margin: 0 0 9px; color: #b9cde0; font: 0.78rem/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space: pre-wrap; }
    .log-line.ok { color: var(--accent-2); }
    .log-line.warn { color: var(--warning); }
    .log-line.error { color: var(--danger); }
    .result { margin-top: 14px; padding: 14px; border-radius: 12px; border: 1px solid var(--border); background: #081522; display: none; }
    .result pre { margin: 9px 0 0; white-space: pre-wrap; word-break: break-word; color: #cfe2f5; font-size: 0.78rem; }
    .notes { margin-top: 18px; color: var(--muted); font-size: 0.82rem; line-height: 1.55; }
    @media (max-width: 880px) {
      .grid { grid-template-columns: 1fr; }
      .pipeline { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="eyebrow">Local portfolio walkthrough</div>
    <h1>Secure AI inference, visible end to end.</h1>
    <p class="lede">
      This demo runs the gateway, policy controls, priority queue, worker, mock vLLM adapter,
      result store, metrics, and audit trail in one local process. Run the guided request below,
      or open Swagger to exercise each API endpoint directly.
    </p>
    <div class="actions">
      <a class="button primary" href="/docs">Open interactive Swagger</a>
      <a class="button" href="/openapi.json">OpenAPI JSON</a>
      <a class="button" href="/health">Raw health endpoint</a>
    </div>

    <section class="grid">
      <div class="panel">
        <h2>Guided request lifecycle</h2>
        <p>Submit one request and watch the same asynchronous flow an API client would use.</p>

        <label for="prompt">Prompt</label>
        <textarea id="prompt">Summarize why deterministic routing and an audit trail matter in a secure inference platform.</textarea>

        <label for="context">Optional context</label>
        <textarea id="context">The platform separates the public control plane from isolated model execution, exposes routing reason codes, and records request lifecycle events.</textarea>

        <div class="actions">
          <button id="run" class="button primary" type="button">Run guided request</button>
          <button id="reset" class="button" type="button">Reset</button>
        </div>

        <div class="pipeline" id="pipeline">
          <div class="stage" data-stage="gateway"><strong>1. Gateway</strong><span>Validate and admit request</span></div>
          <div class="stage" data-stage="routing"><strong>2. Routing</strong><span>Select model with reason code</span></div>
          <div class="stage" data-stage="queue"><strong>3. Priority queue</strong><span>Decouple request from execution</span></div>
          <div class="stage" data-stage="batch"><strong>4. Batching</strong><span>Group compatible work</span></div>
          <div class="stage" data-stage="scheduler"><strong>5. GPU scheduler</strong><span>Check capacity and placement</span></div>
          <div class="stage" data-stage="inference"><strong>6. Inference</strong><span>Execute through vLLM adapter</span></div>
          <div class="stage" data-stage="result"><strong>7. Result store</strong><span>Persist terminal response</span></div>
          <div class="stage" data-stage="audit"><strong>8. Audit trail</strong><span>Reconstruct lifecycle events</span></div>
        </div>

        <div class="status-row">
          <div class="metric"><small>Request ID</small><code id="request-id">not submitted</code></div>
          <div class="metric"><small>Routing decision</small><code id="routing-decision">not available</code></div>
        </div>

        <div id="result" class="result"><strong>Terminal result</strong><pre id="result-json"></pre></div>
      </div>

      <aside class="panel">
        <h2>What is happening</h2>
        <p>The activity log uses the real demo API. Swagger remains the source of truth for the contract.</p>
        <div id="log" class="log" aria-live="polite"></div>
        <div class="notes">
          No AWS account, model server, or external network connection is required. The local worker uses a mock vLLM adapter so the platform behavior can be inspected without hiding the control-plane decisions behind model setup.
        </div>
      </aside>
    </section>
  </main>

  <script>
    const runButton = document.getElementById('run');
    const resetButton = document.getElementById('reset');
    const logBox = document.getElementById('log');
    const requestId = document.getElementById('request-id');
    const routingDecision = document.getElementById('routing-decision');
    const resultPanel = document.getElementById('result');
    const resultJson = document.getElementById('result-json');
    const stageNames = ['gateway', 'routing', 'queue', 'batch', 'scheduler', 'inference', 'result', 'audit'];

    function stage(name, state) {
      const el = document.querySelector(`[data-stage="${name}"]`);
      el.classList.remove('active', 'done', 'failed');
      if (state) el.classList.add(state);
    }

    function log(message, kind = '') {
      const line = document.createElement('div');
      line.className = `log-line ${kind}`.trim();
      line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
      logBox.appendChild(line);
      logBox.scrollTop = logBox.scrollHeight;
    }

    function reset() {
      stageNames.forEach(name => stage(name, ''));
      logBox.innerHTML = '';
      requestId.textContent = 'not submitted';
      routingDecision.textContent = 'not available';
      resultPanel.style.display = 'none';
      resultJson.textContent = '';
      runButton.disabled = false;
      log('Ready. The walkthrough will call /health, POST /v1/inference, poll the result, and fetch the audit trail.');
    }

    function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

    async function jsonOrThrow(response) {
      const body = await response.json();
      if (!response.ok) {
        const detail = body && body.detail ? body.detail : response.statusText;
        throw new Error(`${response.status} ${detail}`);
      }
      return body;
    }

    async function pollForResult(id) {
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await sleep(250);
        const body = await jsonOrThrow(await fetch(`/v1/inference/${id}`));
        log(`Result poll ${attempt + 1}: status=${body.status}`);
        if (body.status === 'pending') {
          stage('queue', 'active');
        } else if (body.status === 'processing') {
          stage('queue', 'done');
          stage('batch', 'active');
          stage('scheduler', 'active');
          stage('inference', 'active');
        } else if (body.status === 'completed') {
          ['queue', 'batch', 'scheduler', 'inference', 'result'].forEach(name => stage(name, 'done'));
          return body;
        } else if (body.status === 'failed') {
          ['batch', 'scheduler', 'inference', 'result'].forEach(name => stage(name, 'failed'));
          return body;
        }
      }
      throw new Error('Timed out waiting for a terminal result');
    }

    async function runGuidedDemo() {
      reset();
      runButton.disabled = true;
      try {
        stage('gateway', 'active');
        log('Checking gateway health...');
        const health = await jsonOrThrow(await fetch('/health'));
        log(`Gateway healthy. Models available: ${health.models.join(', ')}`, 'ok');

        const payload = {
          prompt: document.getElementById('prompt').value.trim(),
          context: document.getElementById('context').value.trim(),
          event_type: 'general_inference',
          priority: 5,
          metadata: { tenant: 'guided-demo' }
        };
        if (!payload.prompt) throw new Error('Prompt cannot be empty');

        log('Submitting POST /v1/inference...');
        const accepted = await jsonOrThrow(await fetch('/v1/inference', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }));

        requestId.textContent = accepted.request_id;
        routingDecision.textContent = `${accepted.routing.model_name} · ${accepted.routing.reason}`;
        stage('gateway', 'done');
        stage('routing', 'done');
        stage('queue', 'active');
        log(`Accepted as ${accepted.request_id}`, 'ok');
        log(`Routing: ${accepted.routing.model_name} (${accepted.routing.reason})`, 'ok');

        const result = await pollForResult(accepted.request_id);
        resultPanel.style.display = 'block';
        resultJson.textContent = JSON.stringify(result, null, 2);
        if (result.status === 'failed') {
          log(`Request failed: ${result.error || 'unknown error'}`, 'error');
        } else {
          log('Inference completed and terminal result is available.', 'ok');
        }

        stage('audit', 'active');
        const audit = await jsonOrThrow(await fetch(`/v1/audit/${accepted.request_id}`));
        stage('audit', 'done');
        log(`Audit trail contains ${audit.events.length} lifecycle event(s).`, 'ok');
        log('Walkthrough complete. Open Swagger to inspect or repeat individual API calls.', 'ok');
      } catch (error) {
        log(`Walkthrough stopped: ${error.message}`, 'error');
        const active = document.querySelector('.stage.active');
        if (active) {
          active.classList.remove('active');
          active.classList.add('failed');
        }
      } finally {
        runButton.disabled = false;
      }
    }

    runButton.addEventListener('click', runGuidedDemo);
    resetButton.addEventListener('click', reset);
    reset();
  </script>
</body>
</html>
"""


def attach_demo_ui(app: FastAPI) -> FastAPI:
    """Attach the browser walkthrough to a demo FastAPI application."""

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def demo_home() -> HTMLResponse:
        return HTMLResponse(content=DEMO_HTML)

    return app
