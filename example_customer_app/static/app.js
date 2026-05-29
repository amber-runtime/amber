const state = {
  agents: [],
  selectedAgent: null,
  requests: [],
  selectedRequestId: null,
  activePolls: new Set(),
};

const specialistList = document.querySelector("#specialist-list");
const selectedName = document.querySelector("#selected-name");
const selectedCategory = document.querySelector("#selected-category");
const selectedDescription = document.querySelector("#selected-description");
const taskInput = document.querySelector("#task-input");
const taskForm = document.querySelector("#task-form");
const travelCrashControl = document.querySelector("#travel-crash-control");
const travelCrashToggle = document.querySelector("#travel-crash-toggle");
const accountResearchRatelimitControl = document.querySelector("#account-research-ratelimit-control");
const accountResearchRatelimitToggle = document.querySelector("#account-research-ratelimit-toggle");
const submitButton = document.querySelector("#submit-button");
const requestList = document.querySelector("#request-list");
const requestCount = document.querySelector("#request-count");
const responseViewer = document.querySelector("#response-viewer");
const viewerEmptyState = document.querySelector("#viewer-empty-state");
const viewerContent = document.querySelector("#viewer-content");
const viewerKicker = document.querySelector("#viewer-kicker");
const viewerTitle = document.querySelector("#viewer-title");
const viewerStatus = document.querySelector("#viewer-status");
const viewerMessage = document.querySelector("#viewer-message");
const viewerOutput = document.querySelector("#viewer-output");
const errorMessage = document.querySelector("#error-message");

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 90;
const MAX_VISIBLE_REQUESTS = 25;
const PENDING_REQUEST_KEY = "operationsResearchHub.pendingRequest";
const PENDING_REQUESTS_KEY = "operationsResearchHub.pendingRequests";
const TRAVEL_AGENT_NAME = "travel-concierge";
const ACCOUNT_RESEARCH_ERROR_DEMO_AGENT_NAME = "account-research-error-demo";

function setError(message) {
  if (!message) {
    errorMessage.hidden = true;
    errorMessage.textContent = "";
    return;
  }

  errorMessage.hidden = false;
  errorMessage.textContent = message;
}

function createRequestId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatRequestTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function requestStatusLabel(status) {
  if (status === "STARTING") return "Starting";
  if (status === "SUCCESS") return "Complete";
  if (status === "ERROR" || status === "CANCELLED") return "Needs attention";
  if (status === "TIMEOUT") return "Still working";
  return "Working";
}

function requestSummary(request) {
  if (request.status === "SUCCESS") return "Response ready";
  if (request.status === "ERROR" || request.status === "CANCELLED") {
    return "Please try again or ask your operations team for help.";
  }
  if (request.status === "TIMEOUT") return "Still checking for the response";
  if (request.status === "STARTING") return "Starting request";
  return "Working on your request";
}

function requestPreview(input) {
  const normalized = input.replace(/\s+/g, " ").trim();
  if (!normalized) return "No request details";
  return normalized.length > 94 ? `${normalized.slice(0, 91)}...` : normalized;
}

function savePendingRequests() {
  const pendingRequests = state.requests
    .filter((request) => request.workflowId && !isTerminalStatus(request.status))
    .map((request) => ({
      id: request.id,
      workflowId: request.workflowId,
      displayName: request.displayName,
      category: request.category,
      input: request.input,
      status: request.status,
      startedAt: request.startedAt,
      updatedAt: request.updatedAt,
    }));

  if (pendingRequests.length === 0) {
    window.localStorage.removeItem(PENDING_REQUESTS_KEY);
    window.localStorage.removeItem(PENDING_REQUEST_KEY);
    return;
  }

  window.localStorage.setItem(PENDING_REQUESTS_KEY, JSON.stringify(pendingRequests));
  window.localStorage.removeItem(PENDING_REQUEST_KEY);
}

function loadPendingRequests() {
  const requests = [];

  try {
    const raw = window.localStorage.getItem(PENDING_REQUESTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (Array.isArray(parsed)) {
      parsed.forEach((request) => {
        if (request?.workflowId) requests.push(request);
      });
    }
  } catch {
    window.localStorage.removeItem(PENDING_REQUESTS_KEY);
  }

  try {
    const raw = window.localStorage.getItem(PENDING_REQUEST_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed?.workflow_id) {
      requests.push({
        id: createRequestId(),
        workflowId: parsed.workflow_id,
        displayName: parsed.display_name || "Recovered request",
        category: "Request",
        input: "",
        status: "WORKING",
        startedAt: parsed.started_at || Date.now(),
        updatedAt: Date.now(),
      });
    }
  } catch {
    window.localStorage.removeItem(PENDING_REQUEST_KEY);
  }

  return requests;
}

function isTerminalStatus(status) {
  return status === "SUCCESS" || status === "ERROR" || status === "CANCELLED";
}

function getRequest(requestId) {
  return state.requests.find((request) => request.id === requestId);
}

function addRequest(request) {
  state.requests.unshift(request);
  state.requests = state.requests.slice(0, MAX_VISIBLE_REQUESTS);
  state.selectedRequestId = request.id;
  renderRequests();
  renderViewer();
  savePendingRequests();
}

function updateRequest(requestId, updates) {
  const request = getRequest(requestId);
  if (!request) return null;

  Object.assign(request, updates, { updatedAt: Date.now() });
  renderRequests();
  if (state.selectedRequestId === requestId) renderViewer();
  savePendingRequests();
  return request;
}

function selectRequest(requestId) {
  state.selectedRequestId = requestId;
  renderRequests();
  renderViewer();
}

function renderRequests() {
  requestList.innerHTML = "";
  requestCount.textContent = String(state.requests.length);

  if (state.requests.length === 0) {
    requestList.innerHTML = '<div class="empty-state">Started requests will appear here.</div>';
    return;
  }

  state.requests.forEach((request) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `request-card request-card-${request.status.toLowerCase()}`;
    button.dataset.requestId = request.id;
    button.setAttribute("aria-pressed", String(state.selectedRequestId === request.id));

    const topLine = document.createElement("span");
    topLine.className = "request-topline";
    topLine.textContent = `${request.category} · ${formatRequestTime(request.startedAt)}`;

    const title = document.createElement("strong");
    title.textContent = request.displayName;

    const status = document.createElement("span");
    status.className = "request-status";
    status.textContent = requestStatusLabel(request.status);

    const preview = document.createElement("span");
    preview.className = "request-preview";
    preview.textContent = requestSummary(request);

    button.append(topLine, title, status, preview);
    button.addEventListener("click", () => selectRequest(request.id));
    requestList.appendChild(button);
  });
}

function renderViewer() {
  const request = getRequest(state.selectedRequestId);
  if (!request) {
    viewerEmptyState.hidden = false;
    viewerContent.hidden = true;
    responseViewer.className = "response-viewer";
    return;
  }

  viewerEmptyState.hidden = true;
  viewerContent.hidden = false;
  responseViewer.className = `response-viewer response-viewer-${request.status.toLowerCase()}`;
  viewerKicker.textContent = requestStatusLabel(request.status);
  viewerTitle.textContent = request.displayName;
  viewerStatus.textContent = requestStatusLabel(request.status);
  viewerMessage.textContent = requestSummary(request);

  if (request.status === "SUCCESS") {
    viewerOutput.hidden = false;
    viewerOutput.textContent =
      request.output || "The request completed, but no response was returned.";
  } else if (request.status === "ERROR" || request.status === "CANCELLED") {
    viewerOutput.hidden = true;
    viewerOutput.textContent = "";
  } else {
    viewerOutput.hidden = false;
    viewerOutput.textContent = requestPreview(request.input);
  }
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function pollRunResult(requestId) {
  const request = getRequest(requestId);
  if (!request?.workflowId || state.activePolls.has(requestId)) return;

  state.activePolls.add(requestId);
  updateRequest(requestId, { status: "WORKING" });

  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetch(`runs/${encodeURIComponent(request.workflowId)}`);
      if (response.ok) {
        const run = await response.json();
        if (run.status === "SUCCESS") {
          updateRequest(requestId, { status: "SUCCESS", output: run.output });
          state.activePolls.delete(requestId);
          savePendingRequests();
          return;
        }
        if (run.status === "ERROR" || run.status === "CANCELLED") {
          updateRequest(requestId, { status: run.status });
          state.activePolls.delete(requestId);
          savePendingRequests();
          return;
        }
      }
    } catch {
      // The app may be restarting during the crash demo. Keep polling quietly.
    }

    await wait(POLL_INTERVAL_MS);
  }

  updateRequest(requestId, { status: "TIMEOUT" });
  state.activePolls.delete(requestId);
}

function renderSpecialists() {
  specialistList.innerHTML = "";

  if (state.agents.length === 0) {
    specialistList.innerHTML = '<div class="loading-card">No workflows are registered yet.</div>';
    return;
  }

  state.agents.forEach((agent) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "specialist-card";
    button.dataset.agent = agent.name;
    button.setAttribute("aria-pressed", String(state.selectedAgent?.name === agent.name));

    const category = document.createElement("span");
    category.className = "card-topline";
    category.textContent = agent.category;

    const title = document.createElement("strong");
    title.textContent = agent.display_name;

    const description = document.createElement("span");
    description.textContent = agent.description;

    button.append(category, title, description);
    button.addEventListener("click", () => selectAgent(agent.name, true));
    specialistList.appendChild(button);
  });
}

function selectAgent(agentName, replaceInput) {
  const agent = state.agents.find((candidate) => candidate.name === agentName);
  if (!agent) return;

  state.selectedAgent = agent;
  selectedName.textContent = agent.display_name;
  selectedCategory.textContent = agent.category;
  selectedDescription.textContent = agent.description;
  submitButton.disabled = false;
  const canCrashDuringHotel = agent.name === TRAVEL_AGENT_NAME;
  const canFailAccountResearchDeepScan = agent.name === ACCOUNT_RESEARCH_ERROR_DEMO_AGENT_NAME;
  travelCrashControl.hidden = !canCrashDuringHotel;
  travelCrashToggle.disabled = !canCrashDuringHotel;
  accountResearchRatelimitControl.hidden = !canFailAccountResearchDeepScan;
  accountResearchRatelimitToggle.disabled = !canFailAccountResearchDeepScan;
  if (!canCrashDuringHotel) travelCrashToggle.checked = false;
  if (!canFailAccountResearchDeepScan) {
    accountResearchRatelimitToggle.checked = true;
  }

  if (replaceInput || !taskInput.value.trim()) {
    taskInput.value = agent.sample_input || "";
    taskInput.placeholder = agent.sample_input || "Describe the vendor, market, memo, or travel request...";
  }

  renderSpecialists();
}

async function loadAgents() {
  try {
    const response = await fetch("agents");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    state.agents = await response.json();
    renderSpecialists();
    if (state.agents.length > 0) selectAgent(state.agents[0].name, false);
  } catch (error) {
    specialistList.innerHTML = '<div class="loading-card error">Failed to load workflows.</div>';
    selectedName.textContent = "Unavailable";
    selectedDescription.textContent = "Refresh the page after the customer app is healthy.";
    setError(error instanceof Error ? error.message : "Failed to load workflows.");
  }
}

taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setError("");

  if (!state.selectedAgent) {
    setError("Choose a workflow before starting a request.");
    return;
  }

  const input = taskInput.value.trim();
  if (!input) {
    setError("Describe the operations request before starting.");
    return;
  }

  const requestId = createRequestId();
  addRequest({
    id: requestId,
    workflowId: null,
    displayName: state.selectedAgent.display_name,
    category: state.selectedAgent.category,
    input,
    status: "STARTING",
    output: null,
    startedAt: Date.now(),
    updatedAt: Date.now(),
  });

  submitButton.disabled = true;
  submitButton.textContent = "Starting...";

  try {
    const shouldCrashDuringHotel =
      state.selectedAgent.name === TRAVEL_AGENT_NAME && travelCrashToggle.checked;
    const query = new URLSearchParams();
    if (shouldCrashDuringHotel) query.set("crash_during_hotel", "true");
    if (
      state.selectedAgent.name === ACCOUNT_RESEARCH_ERROR_DEMO_AGENT_NAME &&
      accountResearchRatelimitToggle.checked
    ) {
      query.set("trigger_account_research_ratelimit", "true");
    }
    const runsUrl = query.size > 0 ? `/runs?${query.toString()}` : "/runs";
    const response = await fetch(runsUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent: state.selectedAgent.name,
        input,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const result = await response.json();
    updateRequest(requestId, { workflowId: result.workflow_id, status: "WORKING" });
    pollRunResult(requestId);
  } catch (error) {
    updateRequest(requestId, { status: "ERROR" });
    setError("We could not start this request. Please try again.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Start request";
  }
});

loadPendingRequests().forEach((request) => {
  addRequest({
    id: request.id || createRequestId(),
    workflowId: request.workflowId,
    displayName: request.displayName || "Recovered request",
    category: request.category || "Request",
    input: request.input || "",
    status: "WORKING",
    output: null,
    startedAt: request.startedAt || Date.now(),
    updatedAt: request.updatedAt || Date.now(),
  });
});

state.requests.forEach((request) => {
  pollRunResult(request.id);
});

loadAgents();
