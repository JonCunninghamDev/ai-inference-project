import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const MODEL = __ENV.MODEL || '';
const POLL_INTERVAL_MS = Number(__ENV.POLL_INTERVAL_MS || 250);
const MAX_WAIT_MS = Number(__ENV.MAX_WAIT_MS || 60000);

const terminalLatency = new Trend('inference_terminal_latency_ms', true);
const terminalSuccess = new Rate('inference_terminal_success');
const rejected = new Counter('inference_rejected_total');

export const options = {
  scenarios: {
    async_inference: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 1),
      timeUnit: '1s',
      duration: __ENV.DURATION || '30s',
      preAllocatedVUs: Number(__ENV.PREALLOCATED_VUS || 20),
      maxVUs: Number(__ENV.MAX_VUS || 200),
    },
  },
  thresholds: {
    http_req_failed: ['rate<' + (__ENV.HTTP_ERROR_RATE_MAX || '0.01')],
    inference_terminal_success: ['rate>' + (__ENV.COMPLETION_RATE_MIN || '0.99')],
    inference_terminal_latency_ms: [
      'p(95)<' + (__ENV.P95_TERMINAL_MS_MAX || '60000'),
    ],
  },
};

function requestPayload() {
  const payload = {
    prompt:
      __ENV.PROMPT ||
      'Summarize why bounded queueing matters for an online inference service.',
    context:
      __ENV.CONTEXT ||
      'The service separates admission, queueing, scheduling, model execution, and result storage.',
    event_type: __ENV.EVENT_TYPE || 'benchmark',
    priority: Number(__ENV.PRIORITY || 5),
    metadata: { tenant: __ENV.TENANT || 'benchmark' },
  };
  if (MODEL) {
    payload.requested_model = MODEL;
  }
  return payload;
}

export default function () {
  const started = Date.now();
  const submit = http.post(
    BASE_URL + '/v1/inference',
    JSON.stringify(requestPayload()),
    { headers: { 'Content-Type': 'application/json' }, tags: { operation: 'submit' } },
  );

  if (submit.status === 429) {
    rejected.add(1);
    terminalSuccess.add(false);
    return;
  }

  const accepted = check(submit, {
    'submit accepted': (response) => response.status === 202,
  });
  if (!accepted) {
    terminalSuccess.add(false);
    return;
  }

  let requestId;
  try {
    requestId = submit.json('request_id');
  } catch (error) {
    terminalSuccess.add(false);
    return;
  }

  const deadline = started + MAX_WAIT_MS;
  while (Date.now() < deadline) {
    const result = http.get(
      BASE_URL + '/v1/inference/' + requestId,
      { tags: { operation: 'poll' } },
    );

    if (result.status === 200) {
      const state = result.json('status');
      if (state === 'completed' || state === 'failed') {
        terminalLatency.add(Date.now() - started);
        terminalSuccess.add(state === 'completed');
        return;
      }
    }

    sleep(POLL_INTERVAL_MS / 1000);
  }

  terminalLatency.add(Date.now() - started);
  terminalSuccess.add(false);
}
