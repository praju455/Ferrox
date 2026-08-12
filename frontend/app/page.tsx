"use client";

import { useEffect, useMemo, useState } from "react";

const defaultApiBase = "http://127.0.0.1:8000/api/v1";

const workflowSteps = [
  {
    index: "01",
    title: "Ingest every product source",
    text: "Attach datasheets, supplier URLs, and pasted catalog text to the same product record.",
  },
  {
    index: "02",
    title: "Adapt schema by category",
    text: "Pumps, bearings, motors, and fasteners get their own attribute contracts.",
  },
  {
    index: "03",
    title: "Extract with evidence",
    text: "Every field carries value, unit, source, confidence, status, evidence, and alternatives.",
  },
  {
    index: "04",
    title: "Resolve conflicts clearly",
    text: "Authority rules and LLM review expose mismatches instead of hiding them.",
  },
];

const reviewItems = [
  ["AXP-200 Pump", "material conflict", "PDF datasheet beats supplier page"],
  ["VM-10 Motor", "speed_rpm missing", "required field needs review"],
  ["BR-6205 Bearing", "load rating mismatch", "semantic validation flagged"],
];

const endpoints = [
  "POST /products/ingest/text",
  "POST /products/{id}/pipeline",
  "GET /reviews",
  "PATCH /products/{id}/fields/{name}",
  "GET /batches/{id}",
  "GET /health",
];

export default function Home() {
  const [apiBase, setApiBase] = useState(defaultApiBase);
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState<"Not checked" | "Checking" | "Healthy" | "Offline">("Not checked");
  const [toast, setToast] = useState("");

  useEffect(() => {
    setApiBase(localStorage.getItem("ferrox.ui.apiBase") || defaultApiBase);
    setApiKey(localStorage.getItem("ferrox.ui.apiKey") || "");
  }, []);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timer = window.setTimeout(() => setToast(""), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const healthLabel = useMemo(() => {
    if (status === "Healthy") return "Backend online";
    if (status === "Offline") return "Backend offline";
    return status;
  }, [status]);

  function saveApiBase(value: string) {
    const normalized = value.replace(/\/$/, "");
    setApiBase(normalized);
    localStorage.setItem("ferrox.ui.apiBase", normalized);
    setToast("API base saved.");
  }

  function saveApiKey(value: string) {
    setApiKey(value);
    localStorage.setItem("ferrox.ui.apiKey", value);
    setToast("Internal API key saved locally.");
  }

  async function checkHealth() {
    setStatus("Checking");
    try {
      const response = await fetch(`${apiBase}/health`, {
        headers: apiKey ? { "X-API-Key": apiKey } : undefined,
      });
      if (!response.ok) {
        throw new Error(`${response.status}`);
      }
      setStatus("Healthy");
      setToast("Backend is reachable.");
    } catch {
      setStatus("Offline");
      setToast("Backend is not reachable from this API base.");
    }
  }

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#home" aria-label="Ferrox home">
          <span className="brand-mark">Fx</span>
          <span>Ferrox</span>
        </a>
        <nav className="top-nav" aria-label="Primary navigation">
          <a href="#workflow">Workflow</a>
          <a href="#validation">Validation</a>
          <a href="#review">Review</a>
          <a href="#api">API</a>
        </nav>
        <a className="header-action" href="#demo">
          Live check
        </a>
      </header>

      <main id="home">
        <section className="hero-section">
          <div className="hero-copy">
            <div className="signal-line">
              <span />
              Industrial catalog data, verified at source
            </div>
            <h1>Product data extraction for teams that cannot afford catalog errors.</h1>
            <p>
              Ferrox turns PDFs, supplier pages, and messy catalog snippets into structured product attributes
              with source traceability, conflict handling, validation, enrichment, and review workflows.
            </p>
            <div className="hero-actions">
              <a className="primary-action" href="#demo">
                Explore platform
              </a>
              <a className="secondary-action" href="#api">
                See API contract
              </a>
            </div>
            <div className="proof-strip" aria-label="Platform capabilities">
              <div>
                <strong>3 source types</strong>
                <span>PDF, URL, raw text</span>
              </div>
              <div>
                <strong>LLM failover</strong>
                <span>Gemini, Groq, OpenAI</span>
              </div>
              <div>
                <strong>Human review</strong>
                <span>Conflicts never hidden</span>
              </div>
            </div>
          </div>

          <div className="hero-visual" aria-label="Ferrox product intelligence preview">
            <div className="scanner-top">
              <span className="scanner-dot" />
              <span>AXP-200 ingestion run</span>
              <strong>Live</strong>
            </div>
            <div className="scanner-grid">
              <article className="source-card pdf">
                <span>PDF Datasheet</span>
                <strong>Aurora AXP-200</strong>
                <p>120 GPM - 50 ft head - 5 HP - cast iron</p>
              </article>
              <article className="source-card web">
                <span>Supplier Page</span>
                <strong>AXP-200 Pump</strong>
                <p>110 GPM - stainless steel impeller</p>
              </article>
              <article className="source-card text">
                <span>Catalog Dump</span>
                <strong>Model AXP-200</strong>
                <p>connection size 2 in NPT - 5 HP</p>
              </article>
            </div>
            <div className="pipeline-card">
              <div className="pipeline-node complete">Classify</div>
              <div className="pipeline-node complete">Schema</div>
              <div className="pipeline-node active">Extract</div>
              <div className="pipeline-node warn">Reconcile</div>
              <div className="pipeline-node">Validate</div>
            </div>
            <div className="result-card">
              <div>
                <span>Canonical value</span>
                <strong>flow_rate: 120 GPM</strong>
              </div>
              <em>source: PDF datasheet - confidence 0.83</em>
            </div>
          </div>
        </section>

        <section className="logo-band" aria-label="Industrial categories">
          <span>Industrial Pump</span>
          <span>Bearing</span>
          <span>Electric Motor</span>
          <span>Fastener</span>
          <span>Supplier Catalog</span>
        </section>

        <section className="section workflow-section" id="workflow">
          <div className="section-heading">
            <span className="eyebrow">Workflow</span>
            <h2>From scattered source material to clean product records.</h2>
          </div>
          <div className="workflow-grid">
            {workflowSteps.map((step) => (
              <article key={step.index}>
                <span className="step-index">{step.index}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="split-section" id="validation">
          <div className="validation-copy">
            <span className="eyebrow">Validation</span>
            <h2>Trust is built into the record, not added later.</h2>
            <p>
              Deterministic rules, semantic LLM checks, grounded enrichment, confidence scoring, and completeness
              scoring run before a product reaches catalog-ready status.
            </p>
            <ul className="check-list">
              <li>Strict JSON output contracts and retries</li>
              <li>Source authority ranking for reconciliation</li>
              <li>Review queue for low-confidence or missing fields</li>
              <li>Batch processing with item-level failures</li>
            </ul>
          </div>
          <div className="validation-panel">
            <div className="score-ring">
              <strong>92</strong>
              <span>quality score</span>
            </div>
            <div className="quality-list">
              <div>
                <span>Schema completeness</span>
                <strong>86%</strong>
              </div>
              <div>
                <span>Average confidence</span>
                <strong>0.81</strong>
              </div>
              <div>
                <span>Open conflicts</span>
                <strong>2</strong>
              </div>
              <div>
                <span>Evidence coverage</span>
                <strong>3.1x</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="review-showcase" id="review">
          <div className="section-heading">
            <span className="eyebrow">Review queue</span>
            <h2>Designed for fast human decisions.</h2>
          </div>
          <div className="review-board">
            <div className="review-list">
              {reviewItems.map(([product, issue, detail], index) => (
                <button className={`review-item ${index === 0 ? "selected" : ""}`} key={product} type="button">
                  <strong>{product}</strong>
                  <span>
                    {issue} - {detail}
                  </span>
                </button>
              ))}
            </div>
            <div className="resolution-card">
              <div className="card-header">
                <span>Resolve material</span>
                <strong>PDF wins by authority</strong>
              </div>
              <div className="compare-row">
                <div>
                  <em>PDF datasheet</em>
                  <strong>cast iron</strong>
                </div>
                <div>
                  <em>Supplier page</em>
                  <strong>stainless steel</strong>
                </div>
              </div>
              <div className="decision-row">
                <span>Reviewer action</span>
                <strong>Validate cast iron and close review</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="api-section" id="api">
          <div>
            <span className="eyebrow">Backend-ready</span>
            <h2>Built around the API already implemented in Ferrox.</h2>
            <p>The landing page can evolve into the working product UI without changing the backend contract.</p>
          </div>
          <div className="endpoint-grid">
            {endpoints.map((endpoint) => (
              <code key={endpoint}>{endpoint}</code>
            ))}
          </div>
        </section>

        <section className="demo-section" id="demo">
          <div>
            <span className="eyebrow">Live backend check</span>
            <h2>Connect this Next.js landing page to your local Ferrox API.</h2>
          </div>
          <div className="demo-card">
            <label>
              API base
              <input value={apiBase} onChange={(event) => saveApiBase(event.target.value)} />
            </label>
            <label>
              Internal key
              <input
                type="password"
                value={apiKey}
                onChange={(event) => saveApiKey(event.target.value)}
                placeholder="Optional X-API-Key"
              />
            </label>
            <button className="primary-action" onClick={checkHealth} type="button">
              Check backend
            </button>
            <span className={`backend-pill ${status.toLowerCase().replace(" ", "-")}`}>{healthLabel}</span>
          </div>
        </section>
      </main>

      <div className={`toast ${toast ? "visible" : ""}`} role="status" aria-live="polite">
        {toast}
      </div>
    </>
  );
}
