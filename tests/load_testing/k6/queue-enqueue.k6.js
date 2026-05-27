import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const apiUrl = (__ENV.API_URL || 'http://localhost:8003').replace(/\/$/, '');
const agentName = __ENV.AGENT_NAME || 'synthetic-queue-agent';
const sleepSeconds = __ENV.SLEEP_SECONDS || '5';
const requests = Number.parseInt(__ENV.REQUESTS || '20', 10);
const vus = Number.parseInt(__ENV.VUS || String(Math.min(requests, 10)), 10);

export const enqueuedRuns = new Counter('enqueued_runs');

export const options = {
  scenarios: {
    enqueue: {
      executor: 'shared-iterations',
      vus,
      iterations: requests,
      maxDuration: __ENV.MAX_DURATION || '2m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
    enqueued_runs: [`count==${requests}`],
  },
};

export default function () {
  const payload = JSON.stringify({
    agent: agentName,
    input: `sleep=${sleepSeconds}`,
  });
  const response = http.post(`${apiUrl}/runs`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const ok = check(response, {
    'enqueue returned 200': (r) => r.status === 200,
    'workflow_id returned': (r) => Boolean(r.json('workflow_id')),
    'agent echoed': (r) => r.json('agent') === agentName,
  });

  if (ok) {
    enqueuedRuns.add(1);
  }
  sleep(0.1);
}
