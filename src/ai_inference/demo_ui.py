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
    html { scroll-behavior: smooth; }
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
    .shell { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 26px 0 64px; }
    .eyebrow { color: var(--accent); font-size: 0.76rem; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 800; }
    h1 { margin: 8px 0 10px; font-size: clamp(2rem, 4vw, 3.55rem); line-height: 1.02; max-width: 940px; }
    .lede { color: var(--muted); max-width: 860px; font-size: 1.02rem; line-height: 1.55; margin: 0; }
    .hero-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 18px 0 22px; }
    .button {
      display: inline-flex; align-items: center; justify-content: center; min-height: 44px;
      padding: 0 16px; border-radius: 10px; border: 1px solid var(--border);
      background: var(--panel-2); color: var(--text); text-decoration: none; font-weight: 750; cursor: pointer;
    }
    .button.primary { background: var(--accent); color: #03121d; border-color: transparent; }
    .button:disabled { opacity: 0.5; cursor: wait; }
    .quiet-link { color: var(--muted); font-weight: 700; text-decoration: none; padding: 10px 4px; }
    .quiet-link:hover { color: var(--text); }
    .panel { background: rgba(13, 27, 42, 0.94); border: 1px solid var(--border); border-radius: 16px; padding: 18px; box-shadow: 0 18px 60px rgba(0,0,0,0.18); }
    .panel h2 { margin: 0 0 7px; font-size: 1.12rem; }
    .panel p { color: var(--muted); line-height: 1.5; margin: 0; }
    .pipeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; margin-top: 14px; }
    .stage {
      min-height: 96px; padding: 11px; border: 1px solid var(--border); border-radius: 11px;
      background: #081522; transition: border-color .18s ease, transform .18s ease, background .18s ease;
    }
    .stage small { display: block; color: var(--accent); font-size: 0.68rem; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; }
    .stage strong { display: block; font-size: 0.84rem; margin-top: 4px; }
    .stage span { display: block; color: var(--muted); font-size: 0.72rem; margin-top: 6px; line-height: 1.35; }
    .stage.active { border-color: var(--warning); background: rgba(251,191,36,0.08); transform: translateY(-2px); }
    .stage.done { border-color: var(--accent-2); background: rgba(134,239,172,0.08); }
    .stage.failed { border-color: var(--danger); background: rgba(251,113,133,0.08); }
    .grid { display: grid; grid-template-columns: minmax(0, 1.06fr) minmax(320px, 0.94fr); gap: 16px; margin-top: 16px; }
    .explain-card { margin-top: 14px; padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: #081522; min-height: 118px; }
    .explain-card .step-label { color: var(--accent); font-size: .72rem; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; }
    .explain-card h3 { margin: 5px 0 6px; font-size: 1.02rem; }
    .explain-card p { margin: 0; color: var(--muted); font-size: .9rem; line-height: 1.48; }
    details { border-top: 1px solid var(--border); margin-top: 14px; padding-top: 12px; }
    summary { cursor: pointer; font-weight: 750; color: #cfe2f5; }
    .engineer-links { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 11px; }
    .engineer-links a { font-size: .82rem; color: var(--accent); text-decoration: none; }
    label { display: block; margin: 13px 0 6px; font-size: 0.8rem; font-weight: 800; color: #cfe2f5; }
    textarea {
      width: 100%; border: 1px solid var(--border); border-radius: 10px; background: #081522;
      color: var(--text); padding: 11px 12px; font: inherit; outline: none; resize: vertical;
    }
    textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(99,211,255,0.1); }
    #prompt { min-height: 78px; }
    #context { min-height: 92px; }
    .run-row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
    .status-row { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-top: 13px; }
    .metric { border: 1px solid var(--border); border-radius: 10px; padding: 10px; background: #081522; }
    .metric small { display: block; color: var(--muted); margin-bottom: 5px; }
    .metric code { color: #d8f2ff; word-break: break-all; font-size: .76rem; }
    .log { margin-top: 11px; min-height: 180px; max-height: 310px; overflow: auto; border-radius: 10px; background: #050d16; border: 1px solid #1f3448; padding: 12px; }
    .log-line { margin: 0 0 8px; color: #b9cde0; font: 0.75rem/1.42 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space: pre-wrap; }
    .log-line.ok { color: var(--accent-2); }
    .log-line.warn { color: var(--warning); }
    .log-line.error { color: var(--danger); }
    .result { margin-top: 14px; padding: 14px; border-radius: 12px; border: 1px solid var(--border); background: #081522; display: none; }
    .result h3 { margin: 0 0 8px; font-size: 1rem; }
    .result-copy { color: #d8f2ff; line-height: 1.5; white-space: pre-wrap; }
    .result pre { white-space: pre-wrap; word-break: break-word; color: #cfe2f5; font-size: .76rem; }
    .proof { display: none; margin-top: 16px; }
    .proof-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; margin-top: 12px; }
    .proof-item { border: 1px solid var(--border); border-radius: 10px; padding: 11px; background: #081522; }
    .proof-item strong { display: block; font-size: .78rem; }
    .proof-item span { display: block; color: var(--muted); font-size: .72rem; margin-top: 5px; line-height: 1.35; }
    .notes { margin-top: 12px; color: var(--muted); font-size: 0.79rem; line-height: 1.5; }
    @media (max-width: 880px) {
      .grid { grid-template-columns: 1fr; }
      .pipeline, .proof-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 520px) {
      .pipeline, .proof-grid, .status-row { grid-template-columns: 1fr; }
      .shell { width: min(100% - 20px, 1180px); padding-top: 18px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div class="eyebrow">Interactive portfolio demo</div>
      <h1>See how a production-style AI request moves safely from request to result.</h1>
      <p class="lede">
        Click once to send a real request through the local inference platform. The walkthrough shows
        how the system controls load, chooses a model, manages compute, returns a result, and records what happened.
      </p>
      <div class="hero-actions">
        <button id="hero-run" class="button primary" type="button">Start guided demo</button>
        <a class="quiet-link" href="#how-it-works">See the 8 steps</a>
      </div>
    </header>

    <section id="how-it-works" class="panel">
      <h2>What happens to one AI request</h2>
      <p>Each box represents a real control-plane or worker decision. The active step will light up while the request runs.</p>
      <div class="pipeline" id="pipeline">
        <div class="stage" data-stage="gateway"><small>Step 1</small><strong>Request accepted</strong><span>Validate the request and protect the service from overload.</span></div>
        <div class="stage" data-stage="routing"><small>Step 2</small><strong>Model chosen</strong><span>Pick the appropriate model and expose the reason for that choice.</span></div>
        <div class="stage" data-stage="queue"><small>Step 3</small><strong>Work queued</strong><span>Separate intake from execution so traffic spikes stay controlled.</span></div>
        <div class="stage" data-stage="batch"><small>Step 4</small><strong>Work grouped</strong><span>Combine compatible requests without hiding policy decisions.</span></div>
        <div class="stage" data-stage="scheduler"><small>Step 5</small><strong>Compute checked</strong><span>Confirm enough GPU capacity is available before work runs.</span></div>
        <div class="stage" data-stage="inference"><small>Step 6</small><strong>AI work runs</strong><span>Execute through the same adapter boundary used by the platform.</span></div>
        <div class="stage" data-stage="result"><small>Step 7</small><strong>Result saved</strong><span>Persist the final state so clients can safely retrieve it.</span></div>
        <div class="stage" data-stage="audit"><small>Step 8</small><strong>Decisions recorded</strong><span>Keep a lifecycle trail so operators can reconstruct what happened.</span></div>
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Run the walkthrough</h2>
        <p>The sample request is ready to go. You can run it as-is or customize it first.</p>

        <details>
          <summary>Customize the sample request</summary>
          <label for="prompt">Prompt</label>
          <textarea id="prompt">Summarize why deterministic routing and an audit trail matter in a secure inference platform.</textarea>
          <label for="context">Optional context</label>
          <textarea id="context">The platform separates the public control plane from isolated model execution, exposes routing reason codes, and records request lifecycle events.</textarea>
        </details>

        <div class="run-row">
          <button id="run" class="button primary" type="button">Run sample request</button>
          <button id="reset" class="button" type="button">Reset</button>
        </div>

        <div class="status-row">
          <div class="metric"><small>Request ID</small><code id="request-id">not submitted</code></div>
          <div class="metric"><small>Model decision</small><code id="routing-decision">not available</code></div>
        </div>

        <div id="result" class="result">
          <h3>Result returned</h3>
          <div id="result-copy" class="result-copy"></div>
          <details>
            <summary>Show raw result JSON</summary>
            <pre id="result-json"></pre>
          </details>
        </div>
      </div>

      <aside class="panel">
        <h2>What is happening now</h2>
        <p>This explanation stays in plain English while the actual API runs underneath it.</p>
        <div class="explain-card" aria-live="polite">
          <div id="step-label" class="step-label">Ready</div>
          <h3 id="step-title">Start when you are ready</h3>
          <p id="step-copy">The demo will send one request through the real local gateway, worker, result store, and audit trail.</p>
        </div>

        <details>
          <summary>Show technical activity</summary>
          <div id="log" class="log" aria-live="polite"></div>
        </details>

        <details>
          <summary>For engineers</summary>
          <div class="engineer-links">
            <a href="/docs">Interactive Swagger</a>
            <a href="/openapi.json">OpenAPI JSON</a>
            <a href="/health">Raw health endpoint</a>
          </div>
        </details>

        <div class="notes">
          No AWS account, model server, or external network connection is required. The demo uses a mock vLLM adapter so the platform behavior can be inspected without model setup obscuring the control-plane design.
        </div>
      </aside>
    </section>

    <section id="proof" class="panel proof">
      <h2>What you just saw</h2>
      <p>The request completed through the same policy boundaries the project is designed to demonstrate.</p>
      <div class="proof-grid">
        <div class="proof-item"><strong>Load protected</strong><span>Admission and tenant policy run before work reaches inference.</span></div>
        <div class="proof-item"><strong>Routing explained</strong><span>The selected model includes an explicit reason code.</span></div>
        <div class="proof-item"><strong>Compute controlled</strong><span>Queueing, batching, scheduling, and circuit breaking surround execution.</span></div>
        <div class="proof-item"><strong>Lifecycle auditable</strong><span>The result and request events can be reconstructed after completion.</span></div>
      </div>
    </section>
  </main>

  <script>
    const heroRunButton = document.getElementById('hero-run');
    const runButton = document.getElementById('run');
    const resetButton = document.getElementById('reset');
    const logBox = document.getElementById('log');
    const requestId = document.getElementById('request-id');
    const routingDecision = document.getElementById('routing-decision');
    const resultPanel = document.getElementById('result');
    const resultCopy = document.getElementById('result-copy');
    const resultJson = document.getElementById('result-json');
    const proofPanel = document.getElementById('proof');
    const stepLabel = document.getElementById('step-label');
    const stepTitle = document.getElementById('step-title');
    const stepCopy = document.getElementById('step-copy');
    const stageNames = ['gateway', 'routing', 'queue', 'batch', 'scheduler', 'inference', 'result', 'audit'];

    const explanations = {
      ready: ['Ready', 'Start when you are ready', 'The demo will send one request through the real local gateway, worker, result store, and audit trail.'],
      gateway: ['Step 1 of 8', 'Checking whether the request should enter the system', 'The gateway validates the request and checks current load before accepting more work.'],
      routing: ['Step 2 of 8', 'Choosing the right model', 'The router makes a deterministic model choice and returns a reason code so the decision is explainable.'],
      queue: ['Step 3 of 8', 'Holding the work safely', 'The request waits in a priority queue instead of going straight to a model. That separation helps absorb traffic spikes.'],
      batch: ['Step 4 of 8', 'Grouping compatible work', 'The batcher combines work only when the model, priority, task type, and token budget are compatible.'],
      scheduler: ['Step 5 of 8', 'Checking compute capacity', 'The scheduler confirms the selected model and batch can fit available GPU capacity before execution begins.'],
      inference: ['Step 6 of 8', 'Running the AI work', 'The worker executes through the inference adapter while circuit-breaking logic protects the system from downstream failures.'],
      result: ['Step 7 of 8', 'Saving the final result', 'The terminal state is stored so the client can retrieve a completed or failed result safely.'],
      audit: ['Step 8 of 8', 'Recording what happened', 'The audit trail connects the gateway and worker lifecycle so an operator can reconstruct the important decisions later.'],
      complete: ['Complete', 'The request made it through the full platform', 'You just watched load protection, model routing, controlled execution, result persistence, and auditability work together.'],
      failed: ['Stopped', 'The walkthrough hit a failure path', 'The system surfaced the failure instead of hiding it. Open technical activity for the exact API detail.']
    };

    function explain(name) {
      const [label, title, copy] = explanations[name];
      stepLabel.textContent = label;
      stepTitle.textContent = title;
      stepCopy.textContent = copy;
    }

    function stage(name, state) {
      const el = document.querySelector(`[data-stage="${name}"]`);
      el.classList.remove('active', 'done', 'failed');
      if (state) el.classList.add(state);
    }

    function activate(name) {
      stage(name, 'active');
      explain(name);
    }

    function stageIsDone(name) {
      return document.querySelector(`[data-stage="${name}"]`).classList.contains('done');
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
      resultCopy.textContent = '';
      resultJson.textContent = '';
      proofPanel.style.display = 'none';
      runButton.disabled = false;
      heroRunButton.disabled = false;
      explain('ready');
      log('Ready. The walkthrough will check health, submit one request, poll the result, and fetch the audit trail.');
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

    async function revealExecutionPath() {
      stage('queue', 'done');
      for (const name of ['batch', 'scheduler', 'inference']) {
        if (!stageIsDone(name)) {
          activate(name);
          await sleep(280);
          stage(name, 'done');
        }
      }
    }

    async function pollForResult(id) {
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await sleep(250);
        const body = await jsonOrThrow(await fetch(`/v1/inference/${id}`));
        log(`Result poll ${attempt + 1}: status=${body.status}`);
        if (body.status === 'pending') {
          activate('queue');
        } else if (body.status === 'processing') {
          stage('queue', 'done');
          activate('batch');
        } else if (body.status === 'completed') {
          await revealExecutionPath();
          activate('result');
          return body;
        } else if (body.status === 'failed') {
          ['batch', 'scheduler', 'inference', 'result'].forEach(name => stage(name, 'failed'));
          explain('failed');
          return body;
        }
      }
      throw new Error('Timed out waiting for a terminal result');
    }

    async function runGuidedDemo() {
      reset();
      runButton.disabled = true;
      heroRunButton.disabled = true;
      document.getElementById('how-it-works').scrollIntoView({ behavior: 'smooth', block: 'start' });
      try {
        activate('gateway');
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

        stage('gateway', 'done');
        activate('routing');
        log('Submitting POST /v1/inference...');
        const accepted = await jsonOrThrow(await fetch('/v1/inference', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }));

        requestId.textContent = accepted.request_id;
        routingDecision.textContent = `${accepted.routing.model_name} · ${accepted.routing.reason}`;
        stage('routing', 'done');
        activate('queue');
        log(`Accepted as ${accepted.request_id}`, 'ok');
        log(`Routing: ${accepted.routing.model_name} (${accepted.routing.reason})`, 'ok');

        const result = await pollForResult(accepted.request_id);
        resultPanel.style.display = 'block';
        resultJson.textContent = JSON.stringify(result, null, 2);
        resultCopy.textContent = result.result || result.error || `Request finished with status: ${result.status}`;

        if (result.status === 'failed') {
          log(`Request failed: ${result.error || 'unknown error'}`, 'error');
        } else {
          stage('result', 'done');
          log('Inference completed and terminal result is available.', 'ok');
        }

        await sleep(220);
        activate('audit');
        const audit = await jsonOrThrow(await fetch(`/v1/audit/${accepted.request_id}`));
        stage('audit', 'done');
        log(`Audit trail contains ${audit.events.length} lifecycle event(s).`, 'ok');

        if (result.status === 'completed') {
          explain('complete');
          proofPanel.style.display = 'block';
          proofPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          log('Walkthrough complete.', 'ok');
        }
      } catch (error) {
        log(`Walkthrough stopped: ${error.message}`, 'error');
        const active = document.querySelector('.stage.active');
        if (active) {
          active.classList.remove('active');
          active.classList.add('failed');
        }
        explain('failed');
      } finally {
        runButton.disabled = false;
        heroRunButton.disabled = false;
      }
    }

    heroRunButton.addEventListener('click', runGuidedDemo);
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
