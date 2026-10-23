const modelSelect = document.querySelector("#model");
const runButton = document.querySelector("#run");
const runStatus = document.querySelector("#run-status");
const connection = document.querySelector("#connection");
const privacyBadge = document.querySelector("#privacy-badge");

function showJson(selector, value) {
  const element = document.querySelector(selector);
  element.textContent = JSON.stringify(value, null, 2);
  element.classList.remove("empty-state");
}

function setFlowState(name, active) {
  const step = document.querySelector(`[data-step="${name}"]`);
  if (step) step.classList.toggle("active", active);
}

async function loadPreview() {
  const [statusResponse, previewResponse] = await Promise.all([
    fetch("/api/status"),
    fetch("/api/preview"),
  ]);
  const status = await statusResponse.json();
  const preview = await previewResponse.json();
  document.querySelector("#intent").textContent = preview.intent;
  showJson("#raw-data", preview.raw_api_response);
  showJson("#safe-data", {
    system: preview.model_context[0].content,
    user: JSON.parse(preview.model_context[1].content),
  });
  privacyBadge.textContent = `${preview.privacy.leaked_fields} LEAKS · ${preview.privacy.tokens_created} TOKENS`;
  privacyBadge.classList.add("pass");

  if (status.connected) {
    modelSelect.replaceChildren(...status.models.map((model) => {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      return option;
    }));
    modelSelect.disabled = false;
    runButton.disabled = false;
    connection.classList.add("online");
    connection.querySelector("span:last-child").textContent = "Ollama connected";
  } else {
    modelSelect.replaceChildren(new Option("Ollama not found", ""));
    connection.classList.add("offline");
    connection.querySelector("span:last-child").textContent = "Ollama offline";
    runStatus.textContent = "Start Ollama locally to run inference.";
  }
}

runButton.addEventListener("click", async () => {
  runButton.disabled = true;
  runButton.querySelector("span:first-child").textContent = "Running local inference...";
  runStatus.textContent = "The model receives only the mosaiced context.";
  setFlowState("model", false);
  setFlowState("restore", false);
  document.querySelector("#model-data").textContent = "Waiting for local model...";
  document.querySelector("#restored-data").textContent = "No action is executed.";
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: modelSelect.value }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Local model request failed.");
    showJson("#model-data", result.model_output);
    showJson("#restored-data", result.restored_action);
    privacyBadge.textContent = `${result.privacy.leaked_fields} LEAKS · ${result.privacy.tokens_created} TOKENS`;
    setFlowState("model", true);
    setFlowState("restore", true);
    runStatus.textContent = "Round trip verified. Dry run only; no Mist API call was made.";
  } catch (error) {
    document.querySelector("#model-data").textContent = error.message;
    runStatus.textContent = "No action was executed.";
  } finally {
    runButton.disabled = false;
    runButton.querySelector("span:first-child").textContent = "Run private flow";
  }
});

loadPreview().catch(() => {
  runStatus.textContent = "The local demo server could not load its privacy preview.";
});