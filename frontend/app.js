const settings = {
  apiBase: localStorage.getItem("ferrox.ui.apiBase") || "http://127.0.0.1:8000/api/v1",
  apiKey: localStorage.getItem("ferrox.ui.apiKey") || "",
  productId: null,
};

const apiBaseInput = document.querySelector("#apiBaseInput");
const apiKeyInput = document.querySelector("#apiKeyInput");
const backendStatus = document.querySelector("#backendStatus");
const toast = document.querySelector("#toast");

apiBaseInput.value = settings.apiBase;
apiKeyInput.value = settings.apiKey;

apiBaseInput.addEventListener("change", () => {
  settings.apiBase = apiBaseInput.value.replace(/\/$/, "");
  localStorage.setItem("ferrox.ui.apiBase", settings.apiBase);
  notify("API base saved.");
});

apiKeyInput.addEventListener("change", () => {
  settings.apiKey = apiKeyInput.value;
  localStorage.setItem("ferrox.ui.apiKey", settings.apiKey);
  notify("Internal API key saved locally.");
});

document.querySelectorAll(".segmented button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segmented button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    notify(`${button.textContent.trim()} mode selected.`);
  });
});

document.querySelector("#healthButton").addEventListener("click", checkHealth);
document.querySelector("#pipelineButton").addEventListener("click", runPipeline);
document.querySelector("#reviewsButton").addEventListener("click", () => loadCollection("reviews"));
document.querySelector("#batchesButton").addEventListener("click", () => loadCollection("batches"));

document.querySelector("#ingestForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  try {
    const product = await request("/products/ingest/text", {
      method: "POST",
      body: JSON.stringify({
        product_name: data.get("productName"),
        source_identifier: data.get("sourceIdentifier"),
        text: data.get("sourceText"),
      }),
    });
    settings.productId = product.id;
    notify(`Ingested ${product.name}. Ready to run extraction.`);
  } catch (error) {
    notify(`Ingestion failed: ${error.message}`);
  }
});

async function checkHealth() {
  backendStatus.textContent = "Checking";
  try {
    await request("/health", { auth: false });
    backendStatus.textContent = "Healthy";
    notify("Backend is reachable.");
  } catch {
    backendStatus.textContent = "Offline";
    notify("Backend is not reachable from this API base.");
  }
}

async function runPipeline() {
  if (!settings.productId) {
    notify("Ingest a source first.");
    return;
  }
  try {
    const product = await request(`/products/${settings.productId}/pipeline`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    notify(`Extraction complete. Category: ${product.category || "Unknown"}.`);
  } catch (error) {
    notify(`Pipeline failed: ${error.message}`);
  }
}

async function loadCollection(name) {
  try {
    const items = await request(`/${name}`, { auth: false });
    notify(`Loaded ${items.length} ${name}.`);
  } catch {
    notify(`${name} endpoint is not reachable yet; preview data remains visible.`);
  }
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (options.auth !== false && settings.apiKey) {
    headers["X-API-Key"] = settings.apiKey;
  }
  const response = await fetch(`${settings.apiBase}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function notify(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove("visible"), 3200);
}

checkHealth();
