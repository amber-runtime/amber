const state = {
  agents: [],
  selectedAgent: null,
};

const specialistList = document.querySelector("#specialist-list");
const selectedName = document.querySelector("#selected-name");
const selectedCategory = document.querySelector("#selected-category");
const selectedDescription = document.querySelector("#selected-description");
const taskInput = document.querySelector("#task-input");
const taskForm = document.querySelector("#task-form");
const submitButton = document.querySelector("#submit-button");
const resultPanel = document.querySelector("#result-panel");
const resultKicker = document.querySelector("#result-kicker");
const resultTitle = document.querySelector("#result-title");
const resultMessage = document.querySelector("#result-message");
const resultOutput = document.querySelector("#result-output");
const loadingIndicator = document.querySelector("#loading-indicator");
const errorMessage = document.querySelector("#error-message");

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 90;

function setError(message) {
  if (!message) {
    errorMessage.hidden = true;
    errorMessage.textContent = "";
    return;
  }

  errorMessage.hidden = false;
  errorMessage.textContent = message;
}

function showLoadingResult() {
  resultPanel.hidden = false;
  resultPanel.className = "result-panel result-panel-loading";
  loadingIndicator.hidden = false;
  resultOutput.hidden = true;
  resultOutput.textContent = "";
  resultKicker.textContent = "Working on your request";
  resultTitle.textContent = "Working on your request";
  resultMessage.textContent = "This can take a moment while the workflow completes.";
}

function showFinalResult(output) {
  resultPanel.className = "result-panel result-panel-success";
  loadingIndicator.hidden = true;
  resultOutput.hidden = false;
  resultKicker.textContent = "Response";
  resultTitle.textContent = "Response";
  resultMessage.textContent = "";
  resultOutput.textContent = output || "The request completed, but no response was returned.";
}

function showFailedResult(message) {
  resultPanel.hidden = false;
  resultPanel.className = "result-panel result-panel-error";
  loadingIndicator.hidden = true;
  resultOutput.hidden = true;
  resultOutput.textContent = "";
  resultKicker.textContent = "We could not complete this request";
  resultTitle.textContent = "We could not complete this request";
  resultMessage.textContent = message;
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function pollRunResult(workflowId) {
  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
    const response = await fetch(`/runs/${encodeURIComponent(workflowId)}`);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const run = await response.json();
    if (run.status === "SUCCESS") return run;
    if (run.status === "ERROR" || run.status === "CANCELLED") return run;

    await wait(POLL_INTERVAL_MS);
  }

  return { status: "TIMEOUT", output: null };
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

  if (replaceInput || !taskInput.value.trim()) {
    taskInput.value = agent.sample_input || "";
    taskInput.placeholder = agent.sample_input || "Describe the vendor, market, memo, or travel request...";
  }

  renderSpecialists();
}

async function loadAgents() {
  try {
    const response = await fetch("/agents");
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

  submitButton.disabled = true;
  submitButton.textContent = "Starting...";
  showLoadingResult();

  try {
    const response = await fetch("/runs", {
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
    const run = await pollRunResult(result.workflow_id);
    if (run.status === "SUCCESS") {
      showFinalResult(run.output);
    } else if (run.status === "TIMEOUT") {
      showFailedResult("This is taking longer than expected. Please check back later.");
    } else {
      showFailedResult("Please try again or ask your operations team for help.");
    }
  } catch (error) {
    showFailedResult("Please try again or ask your operations team for help.");
    setError(error instanceof Error ? error.message : "Failed to start request.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Start request";
  }
});

loadAgents();
