import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const MODEL = __ENV.MODEL || '';
const POLL_INTERVAL_MS = Number(__ENV.POLL_INTERVAL_MS || 250);
const MAX_WAIT_MS = Number(__ENV.MAX_WAIT_MS || 60000);
const RATE = Number(__ENV.RATE || 1);
const EXPECTED_TERMINAL_SECONDS = Number(__ENV.EXPECTED_TERMINAL_SECONDS || 5);
const VU_HEADROOM = Number(__ENV.VU_HEADROOM || 1.25);
const RECOMMENDED_VUS = Math.max(
  RATE,
  Math.ceil(RATE * EXPECTED_TERMINAL_SECONDS * VU_HEADROOM),
);
const PREALLOCATED_VUS = Number(__ENV.PREALLOCATED_VUS || RECOMMENDED_VUS);

const terminalLatency = new Trend('inference_terminal_latency_ms', true);
const acceptedTerminalSuccess = new Rate('accepted_terminal_success');
const admissionRejectedRate = new Rate('inference_admission_rejected_rate');
const unexpectedSubmitFailure = new Rate('unexpected_submit_failure');
const pollHttpFailure = new Rate('poll_http_failure');
const rejected = new Counter('inference_rejected_total');

const thresholds = {
  accepted_terminal_success: [
    'rate>' + (__ENV.COMPLETION_RATE_MIN || '0.99'),
  ],
  unexpected_submit_failure: [
    'rate<' + (__ENV.UNEXPECTED_SUBMIT_FAILURE_RATE_MAX || '0.01'),
  ],
  poll_http_failure: [
    'rate<' + (__ENV.POLL_HTTP_FAILURE_RATE_MAX || '0.01'),
  ],
  inference_terminal_latency_ms: [
    'p(95)<' + (__ENV.P95_TERMINAL_MS_MAX || '60000'),
  ],
  dropped_iterations: ['count==0'],
};

if (__ENV.ADMISSION_REJECTION_RATE_MAX) {
  thresholds.inference_admission_rejected_rate = [
    'rate<=' + __ENV.ADMISSION_REJECTION_RATE_MAX,
  ];
}

export const options = {
  scenarios: {
    async_inference: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: __ENV.DURATION || '30s',
      preAllocatedVUs: PREALLOCATED_VUS,
    },
  },
  thresholds,
};

export function setup() {
  console.log(
    JSON.stringify({
      target_rate_rps: RATE,
      expected_terminal_seconds: EXPECTED_TERMINAL_SECONDS,
      vu_headroom: VU_HEADROOM,
      recommended_preallocated_vus: RECOMMENDED_VUS,
      configured_preallocated_vus: PREALLOCATED_VUS,
      admission_rejection_threshold:
        __ENV.ADMISSION_REJECTION_RATE_MAX || null,
    }),
  );
}

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
    admissionRejectedRate.add(true);
    unexpectedSubmitFailure.add(false);
    return;
  }

  admissionRejectedRate.add(false);

  const accepted = check(submit, {
    'submit accepted': (response) => response.status === 202,
  });
  if (!accepted) {
    unexpectedSubmitFailure.add(true);
    return;
  }
  unexpectedSubmitFailure.add(false);

  let requestId;
  try {
    requestId = submit.json('request_id');
  } catch (error) {
    acceptedTerminalSuccess.add(false);
    return;
  }

  const deadline = started + MAX_WAIT_MS;
  while (Date.now() < deadline) {
    const result = http.get(
      BASE_URL + '/v1/inference/' + requestId,
      { tags: { operation: 'poll' } },
    );

    const pollOk = result.status === 200;
    pollHttpFailure.add(!pollOk);

    if (pollOk) {
      const state = result.json('status');
      if (state === 'completed' || state === 'failed') {
        terminalLatency.add(Date.now() - started);
        acceptedTerminalSuccess.add(state === 'completed');
        return;
      }
    }

    sleep(POLL_INTERVAL_MS / 1000);
  }

  terminalLatency.add(Date.now() - started);
  acceptedTerminalSuccess.add(false);
}
