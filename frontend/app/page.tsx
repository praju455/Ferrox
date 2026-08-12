"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const defaultApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api/v1";

const sourceData = {
  PDF: {
    title: "AXP-200 Technical Datasheet",
    detail: "Manufacturer-issued - 14 pages",
    fields: ["Flow rate 120 GPM", "Head 50 ft", "Power 5 HP", "Cast iron body"],
    authority: "01 / highest authority",
  },
  URL: {
    title: "Supplier product page",
    detail: "Authorized distributor - scraped now",
    fields: ["Flow rate 110 GPM", "Head 50 ft", "Power 5 HP", "Stainless steel body"],
    authority: "03 / secondary source",
  },
  TEXT: {
    title: "Legacy catalog export",
    detail: "ERP snippet - imported today",
    fields: ["Model AXP-200", "2 in NPT", "Power 5 HP", "60 Hz"],
    authority: "02 / internal record",
  },
} as const;

type SourceName = keyof typeof sourceData;

const pipeline = [
  ["01", "Ingest", "PDF, URL and text stay attached to one product."],
  ["02", "Classify", "Category selects the right industrial schema."],
  ["03", "Extract", "Every value keeps evidence and source lineage."],
  ["04", "Reconcile", "Conflicts are surfaced and ranked by authority."],
  ["05", "Validate", "Rules and semantic checks gate catalog readiness."],
];

const reviewItems = [
  { product: "Aurora AXP-200", field: "body_material", issue: "Conflicting values", severity: "High" },
  { product: "VoltEdge VM-10", field: "speed_rpm", issue: "Required value missing", severity: "Medium" },
  { product: "Borex BR-6205", field: "load_rating", issue: "Unit mismatch", severity: "Medium" },
];

const contract = [
  ["POST", "/products/ingest/text", "Create a product from raw catalog evidence"],
  ["POST", "/products/{id}/pipeline", "Run classification through validation"],
  ["GET", "/reviews", "List conflicts and low-confidence fields"],
  ["PATCH", "/products/{id}/fields/{name}", "Approve or correct a canonical value"],
];

export default function Home() {
  const [selectedSource, setSelectedSource] = useState<SourceName>("PDF");
  const [selectedReview, setSelectedReview] = useState(0);
  const [apiBase, setApiBase] = useState(defaultApiBase);
  const [status, setStatus] = useState<"Not checked" | "Checking" | "Healthy" | "Offline">("Not checked");

  useEffect(() => {
    setApiBase(localStorage.getItem("ferrox.ui.apiBase") || defaultApiBase);
  }, []);

  const activeSource = sourceData[selectedSource];
  const activeReview = reviewItems[selectedReview];
  const healthCopy = useMemo(() => {
    if (status === "Healthy") return "API online";
    if (status === "Offline") return "API offline";
    return status;
  }, [status]);

  function updateApiBase(value: string) {
    setApiBase(value);
    localStorage.setItem("ferrox.ui.apiBase", value.replace(/\/$/, ""));
  }

  async function checkHealth() {
    setStatus("Checking");
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/health`);
      if (!response.ok) throw new Error(String(response.status));
      setStatus("Healthy");
    } catch {
      setStatus("Offline");
    }
  }

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Ferrox home">
          <span className="brand-mark">F/</span>
          <span className="brand-word">Ferrox</span>
        </a>
        <nav className="top-nav" aria-label="Primary navigation">
          <a href="#platform">Platform</a>
          <a href="#evidence">Evidence</a>
          <a href="#review">Review</a>
          <a href="#developers">Developers</a>
        </nav>
        <Link className="header-cta" href="/workspace">
          Open workspace <span aria-hidden="true">&#8599;</span>
        </Link>
      </header>

      <main id="top">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-media" aria-hidden="true" />
          <div className="hero-shade" aria-hidden="true" />
          <div className="hero-inner">
            <div className="hero-copy">
              <div className="system-label">
                <span className="status-light" /> Industrial product intelligence
              </div>
              <h1 id="hero-title">Every product spec. Verified.</h1>
              <p>
                Ferrox turns scattered datasheets, supplier pages and catalog dumps into structured industrial
                product records with evidence attached to every field.
              </p>
              <div className="hero-actions">
                <Link className="action-primary" href="/workspace">
                  Start an extraction <span aria-hidden="true">&#8594;</span>
                </Link>
                <a className="action-secondary" href="#platform">
                  See how it works
                </a>
              </div>
            </div>

            <div className="hero-inspector" aria-label="Live product source inspector">
              <div className="inspector-header">
                <div>
                  <span>PRODUCT RECORD</span>
                  <strong>AXP-200 / Industrial Pump</strong>
                </div>
                <span className="live-state"><i /> PROCESSING</span>
              </div>
              <div className="source-tabs" role="tablist" aria-label="Product sources">
                {(Object.keys(sourceData) as SourceName[]).map((source) => (
                  <button
                    aria-selected={selectedSource === source}
                    className={selectedSource === source ? "active" : ""}
                    key={source}
                    onClick={() => setSelectedSource(source)}
                    role="tab"
                    type="button"
                  >
                    {source}
                  </button>
                ))}
              </div>
              <div className="source-summary">
                <div className="file-icon" aria-hidden="true">{selectedSource.slice(0, 1)}</div>
                <div>
                  <strong>{activeSource.title}</strong>
                  <span>{activeSource.detail}</span>
                </div>
              </div>
              <div className="field-list">
                {activeSource.fields.map((field, index) => (
                  <div key={field}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{field}</strong>
                    <i className={index === 0 && selectedSource === "URL" ? "conflict" : "verified"} />
                  </div>
                ))}
              </div>
              <div className="authority-row">
                <span>SOURCE RANK</span>
                <strong>{activeSource.authority}</strong>
              </div>
            </div>
          </div>

          <div className="hero-proof" aria-label="Platform proof points">
            <div><strong>03</strong><span>source types</span></div>
            <div><strong>16</strong><span>seeded industrial products</span></div>
            <div><strong>03</strong><span>LLM providers in failover</span></div>
            <div><strong>100%</strong><span>field-level traceability</span></div>
          </div>
        </section>

        <section className="category-rail" aria-label="Supported industrial categories">
          <span>Built for</span>
          <strong>Industrial pumps</strong>
          <strong>Bearings</strong>
          <strong>Electric motors</strong>
          <strong>Fasteners</strong>
          <strong>Technical catalogs</strong>
        </section>

        <section className="platform-section" id="platform">
          <div className="section-intro">
            <span className="section-index">01 / PLATFORM</span>
            <h2>One evidence chain from source to catalog.</h2>
            <p>
              Product teams can see what Ferrox found, where it found it, why a value won, and what still needs a
              human decision.
            </p>
          </div>
          <div className="pipeline-table">
            {pipeline.map(([number, title, copy], index) => (
              <article key={number}>
                <span>{number}</span>
                <div className={`pipeline-symbol symbol-${index + 1}`} aria-hidden="true"><i /></div>
                <h3>{title}</h3>
                <p>{copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="evidence-section" id="evidence">
          <div className="evidence-copy">
            <span className="section-index light">02 / EVIDENCE</span>
            <h2>Trust the record because you can inspect the proof.</h2>
            <p>
              The canonical value is never a black box. Each decision includes its source, confidence, evidence,
              competing values and validation outcome.
            </p>
            <div className="validation-stats">
              <div><strong>0.94</strong><span>record confidence</span></div>
              <div><strong>86%</strong><span>schema complete</span></div>
              <div><strong>2</strong><span>open conflicts</span></div>
            </div>
          </div>

          <div className="record-console" aria-label="Canonical product record example">
            <div className="console-topbar">
              <div><i /><i /><i /></div>
              <span>ferrox / products / AXP-200</span>
              <strong>CATALOG READY</strong>
            </div>
            <div className="record-head">
              <div>
                <span>AURORA INDUSTRIAL</span>
                <h3>End-Suction Pump AXP-200</h3>
              </div>
              <div className="record-score"><strong>94</strong><span>QUALITY</span></div>
            </div>
            <div className="record-grid">
              <div className="record-labels">
                <span>ATTRIBUTE</span><span>CANONICAL VALUE</span><span>CONFIDENCE</span><span>STATUS</span>
              </div>
              {[
                ["flow_rate", "120 GPM", "0.96", "validated"],
                ["head", "50 ft", "0.91", "validated"],
                ["power_rating", "5 HP", "0.98", "validated"],
                ["body_material", "cast iron", "0.78", "resolved"],
                ["connection_size", "2 in NPT", "0.84", "extracted"],
              ].map((field) => (
                <div className="record-row" key={field[0]}>
                  <code>{field[0]}</code><strong>{field[1]}</strong><span>{field[2]}</span><em>{field[3]}</em>
                </div>
              ))}
            </div>
            <div className="evidence-drawer">
              <div>
                <span>SELECTED EVIDENCE</span>
                <strong>&ldquo;Rated capacity: 120 US GPM at 50 ft total dynamic head.&rdquo;</strong>
              </div>
              <div>
                <span>SOURCE</span>
                <strong>AXP-200-datasheet.pdf - page 4</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="review-section" id="review">
          <div className="section-intro compact">
            <span className="section-index">03 / REVIEW</span>
            <h2>Human review, only where judgment matters.</h2>
          </div>
          <div className="review-workspace">
            <div className="review-queue">
              <div className="queue-heading"><span>OPEN REVIEWS</span><strong>23 items</strong></div>
              {reviewItems.map((item, index) => (
                <button
                  className={selectedReview === index ? "active" : ""}
                  key={item.product}
                  onClick={() => setSelectedReview(index)}
                  type="button"
                >
                  <span className={`severity ${item.severity.toLowerCase()}`}>{item.severity}</span>
                  <strong>{item.product}</strong>
                  <small>{item.field} - {item.issue}</small>
                </button>
              ))}
            </div>
            <div className="review-detail">
              <div className="detail-heading">
                <div><span>REVIEWING</span><h3>{activeReview.product}</h3></div>
                <strong>{activeReview.field}</strong>
              </div>
              <div className="comparison-grid">
                <div className="candidate selected">
                  <span>PDF DATASHEET - AUTHORITY 01</span>
                  <strong>cast iron</strong>
                  <p>&ldquo;Casing material: ASTM A48 Class 30 cast iron.&rdquo;</p>
                  <em>Recommended</em>
                </div>
                <div className="candidate">
                  <span>SUPPLIER PAGE - AUTHORITY 03</span>
                  <strong>stainless steel</strong>
                  <p>&ldquo;Corrosion-resistant stainless construction.&rdquo;</p>
                  <em>Alternative</em>
                </div>
              </div>
              <div className="review-decision">
                <div><span>FERROX DECISION</span><strong>Datasheet value wins by source authority.</strong></div>
                <button type="button">Approve &amp; close <span aria-hidden="true">&#8594;</span></button>
              </div>
            </div>
          </div>
        </section>

        <section className="developer-section" id="developers">
          <div className="developer-copy">
            <span className="section-index light">04 / DEVELOPERS</span>
            <h2>A backend contract ready for the product UI.</h2>
            <p>
              FastAPI, PostgreSQL and a provider fallback chain from Gemini to Groq to OpenAI. Reviewer and admin
              accounts use expiring JWT access, and every response carries a request ID.
            </p>
          </div>
          <div className="contract-list">
            {contract.map(([method, path, description]) => (
              <div key={path}>
                <span>{method}</span><code>{path}</code><p>{description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="connect-section" id="connect">
          <div>
            <span className="section-index">LIVE CONNECTION</span>
            <h2>Point Ferrox at your backend.</h2>
            <p>Connection details stay in this browser only.</p>
          </div>
          <div className="connection-form">
            <label>
              <span>API BASE</span>
              <input aria-label="API base" value={apiBase} onChange={(event) => updateApiBase(event.target.value)} />
            </label>
            <label>
              <span>TEAM ACCESS</span>
              <Link className="connection-login" href="/login">Sign in with a reviewer account <span aria-hidden="true">&#8599;</span></Link>
            </label>
            <button onClick={checkHealth} type="button">Check connection <span aria-hidden="true">&#8594;</span></button>
            <div className={`connection-state ${status.toLowerCase().replace(" ", "-")}`}>
              <i /> {healthCopy}
            </div>
          </div>
        </section>
      </main>

      <footer>
        <a className="brand footer-brand" href="#top"><span className="brand-mark">F/</span><span>Ferrox</span></a>
        <p>Industrial product intelligence, verified at source.</p>
        <span>BACKEND v1.0 - NEXT.JS</span>
      </footer>
    </>
  );
}
