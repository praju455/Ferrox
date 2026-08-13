"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  apiFetch,
  apiDownload,
  Batch,
  clearToken,
  fileToBase64,
  getToken,
  LlmRun,
  PipelineJob,
  Product,
  ProductDetail,
  ReviewItem,
  User,
} from "../../lib/api";

type View = "overview" | "products" | "reviews" | "batches" | "operations";
type SourceMode = "text" | "url" | "pdf";
type BatchDraft = { name: string; source: Record<string, string> };

const views: Array<{ id: View; label: string; short: string }> = [
  { id: "overview", label: "Overview", short: "OV" },
  { id: "products", label: "Products", short: "PD" },
  { id: "reviews", label: "Review queue", short: "RQ" },
  { id: "batches", label: "Batch runs", short: "BT" },
  { id: "operations", label: "Operations", short: "OP" },
];

export default function WorkspacePage() {
  const router = useRouter();
  const [view, setView] = useState<View>("overview");
  const [products, setProducts] = useState<Product[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [jobs, setJobs] = useState<PipelineJob[]>([]);
  const [runs, setRuns] = useState<LlmRun[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadWorkspace = useCallback(async () => {
    setError("");
    try {
      const [productRows, reviewRows, batchRows, jobRows] = await Promise.all([
        apiFetch<Product[]>("/products"),
        apiFetch<ReviewItem[]>("/reviews?status=open"),
        apiFetch<Batch[]>("/batches"),
        apiFetch<PipelineJob[]>("/pipeline/jobs?limit=20"),
      ]);
      setProducts(productRows);
      setReviews(reviewRows);
      setBatches(batchRows);
      setJobs(jobRows);
      if (!selectedProductId && productRows.length) setSelectedProductId(productRows[0].id);
      if (getToken()) {
        try {
          const currentUser = await apiFetch<User>("/auth/me");
          setUser(currentUser);
          if (currentUser.role === "admin") setRuns(await apiFetch<LlmRun[]>("/observability/llm-runs?limit=30"));
        } catch {
          if (!getToken()) router.replace("/login");
        }
      } else {
        try {
          setRuns(await apiFetch<LlmRun[]>("/observability/llm-runs?limit=30"));
        } catch {
          setRuns([]);
        }
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Workspace could not be loaded";
      setError(message);
      if (!getToken() && message.toLowerCase().includes("authentication")) router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [router, selectedProductId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (!selectedProductId) return;
    apiFetch<ProductDetail>(`/products/${selectedProductId}`).then(setProduct).catch((reason) => setError(reason.message));
  }, [selectedProductId]);

  const openReviews = reviews.length;
  const activeJobs = jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  const averageCompleteness = products.length
    ? products.reduce((total, item) => total + item.completeness_score, 0) / products.length
    : 0;

  function signOut() {
    clearToken();
    router.push("/login");
  }

  async function refreshProduct() {
    if (!selectedProductId) return;
    setProduct(await apiFetch<ProductDetail>(`/products/${selectedProductId}`));
    await loadWorkspace();
  }

  return (
    <main className="workspace-shell">
      <aside className="workspace-sidebar">
        <Link className="brand workspace-brand" href="/">
          <span className="brand-mark">F/</span><span className="brand-word">Ferrox</span>
        </Link>
        <nav aria-label="Workspace navigation">
          {views.map((item) => (
            <button className={view === item.id ? "active" : ""} key={item.id} onClick={() => setView(item.id)} type="button">
              <span>{item.short}</span>{item.label}
              {item.id === "reviews" && openReviews > 0 && <em>{openReviews}</em>}
            </button>
          ))}
        </nav>
        <div className="workspace-account">
          <span>{user?.role || "LOCAL MODE"}</span>
          <strong>{user?.full_name || "Development workspace"}</strong>
          {user ? <button onClick={signOut} type="button">Sign out</button> : <Link href="/login">Configure sign in</Link>}
        </div>
      </aside>

      <section className="workspace-main">
        <header className="workspace-topbar">
          <div>
            <span>INDUSTRIAL PRODUCT INTELLIGENCE</span>
            <h1>{views.find((item) => item.id === view)?.label}</h1>
          </div>
          <div className={`workspace-health ${error ? "warning" : ""}`}><i /> {error ? "API ATTENTION" : "API CONNECTED"}</div>
        </header>

        {notice && <div className="workspace-notice"><span>{notice}</span><button onClick={() => setNotice("")} type="button">Close</button></div>}
        {error && <div className="workspace-error" role="alert"><span>{error}</span><button onClick={() => setError("")} type="button">Close</button></div>}
        {loading ? <div className="workspace-loading">Loading catalog operations...</div> : (
          <div className="workspace-content">
            {view === "overview" && (
              <Overview
                activeJobs={activeJobs}
                averageCompleteness={averageCompleteness}
                batches={batches}
                products={products}
                reviews={reviews}
                selectProduct={(id) => { setSelectedProductId(id); setView("products"); }}
              />
            )}
            {view === "products" && (
              <ProductsView
                onCreated={async (created) => { setSelectedProductId(created.id); await loadWorkspace(); }}
                onError={setError}
                onNotice={setNotice}
                onRefresh={refreshProduct}
                product={product}
                products={products}
                selectedId={selectedProductId}
                setSelectedId={setSelectedProductId}
              />
            )}
            {view === "reviews" && <ReviewsView onError={setError} onRefresh={loadWorkspace} reviews={reviews} />}
            {view === "batches" && <BatchesView batches={batches} onError={setError} onRefresh={loadWorkspace} onNotice={setNotice} />}
            {view === "operations" && <Operations jobs={jobs} runs={runs} />}
          </div>
        )}
      </section>
    </main>
  );
}

function Overview({ products, reviews, batches, activeJobs, averageCompleteness, selectProduct }: {
  products: Product[]; reviews: ReviewItem[]; batches: Batch[]; activeJobs: number; averageCompleteness: number; selectProduct: (id: string) => void;
}) {
  return (
    <>
      <div className="metric-strip">
        <Metric label="Catalog products" value={String(products.length)} detail="Structured product records" />
        <Metric label="Average completeness" value={`${Math.round(averageCompleteness * 100)}%`} detail="Required attributes populated" />
        <Metric label="Open reviews" value={String(reviews.length)} detail="Human decisions required" alert={reviews.length > 0} />
        <Metric label="Active jobs" value={String(activeJobs)} detail={`${batches.length} batch runs tracked`} />
      </div>
      <section className="workspace-band">
        <div className="band-heading"><div><span>RECENT RECORDS</span><h2>Catalog readiness</h2></div><span>{products.length} TOTAL</span></div>
        <div className="product-table">
          <div className="table-head"><span>Product</span><span>Category</span><span>Completeness</span><span>Confidence</span><span>Status</span></div>
          {products.slice(0, 8).map((item) => (
            <button className="table-row" key={item.id} onClick={() => selectProduct(item.id)} type="button">
              <strong>{item.name}</strong><span>{item.category || "Unclassified"}</span>
              <Progress value={item.completeness_score} />
              <span>{Math.round(item.confidence_score * 100)}%</span>
              <Status value={item.completeness_score >= 0.8 ? "ready" : "incomplete"} />
            </button>
          ))}
          {!products.length && <Empty text="No products yet. Add the first record from Products." />}
        </div>
      </section>
    </>
  );
}

function ProductsView({ products, product, selectedId, setSelectedId, onCreated, onRefresh, onNotice, onError }: {
  products: Product[]; product: ProductDetail | null; selectedId: string; setSelectedId: (id: string) => void;
  onCreated: (product: Product) => Promise<void>; onRefresh: () => Promise<void>; onNotice: (text: string) => void; onError: (text: string) => void;
}) {
  const [name, setName] = useState("");
  const [sourceMode, setSourceMode] = useState<SourceMode>("text");
  const [sourceIdentifier, setSourceIdentifier] = useState("catalog-snippet");
  const [sourceValue, setSourceValue] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  async function createProduct(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await apiFetch<Product>("/products", { method: "POST", body: JSON.stringify({ name }) });
      setName("");
      await onCreated(created);
      onNotice("Product record created. Add source evidence next.");
    } catch (reason) { onError(messageOf(reason)); } finally { setBusy(false); }
  }

  async function addSource(event: FormEvent) {
    event.preventDefault();
    if (!selectedId) return;
    setBusy(true);
    try {
      if (sourceMode === "text") {
        await apiFetch(`/products/${selectedId}/sources/text`, { method: "POST", body: JSON.stringify({ text: sourceValue, source_identifier: sourceIdentifier }) });
      } else if (sourceMode === "url") {
        await apiFetch(`/products/${selectedId}/sources/url`, { method: "POST", body: JSON.stringify({ url: sourceValue }) });
      } else {
        if (!file) throw new Error("Choose a PDF datasheet first");
        const form = new FormData();
        form.append("file", file);
        await apiFetch(`/products/${selectedId}/sources/pdf`, { method: "POST", body: form });
      }
      setSourceValue(""); setFile(null);
      await onRefresh();
      onNotice("Source evidence attached to this product.");
    } catch (reason) { onError(messageOf(reason)); } finally { setBusy(false); }
  }

  async function queuePipeline() {
    if (!selectedId) return;
    setBusy(true);
    try {
      const job = await apiFetch<PipelineJob>(`/products/${selectedId}/pipeline/jobs`, { method: "POST", body: "{}" });
      onNotice(`Pipeline job ${job.id.slice(0, 8)} queued. The worker will process it.`);
      await waitForJob(job.id, onRefresh);
    } catch (reason) { onError(messageOf(reason)); } finally { setBusy(false); }
  }

  return (
    <div className="products-layout">
      <aside className="record-list">
        <form className="quick-create" onSubmit={createProduct}>
          <label><span>NEW PRODUCT</span><input onChange={(event) => setName(event.target.value)} placeholder="Product name" required value={name} /></label>
          <button disabled={busy} title="Create product" type="submit">+</button>
        </form>
        <div className="record-list-scroll">
          {products.map((item) => (
            <button className={selectedId === item.id ? "active" : ""} key={item.id} onClick={() => setSelectedId(item.id)} type="button">
              <strong>{item.name}</strong><span>{item.category || "Awaiting classification"}</span><em>{Math.round(item.completeness_score * 100)}%</em>
            </button>
          ))}
        </div>
      </aside>
      <section className="record-detail">
        {!product ? <Empty text="Select a product record." /> : (
          <>
            <div className="record-detail-head">
              <div><span>{product.category || "UNCLASSIFIED"}</span><h2>{product.name}</h2><small>{product.sources.length} sources / {product.fields.length} canonical fields</small></div>
              <button className="solid-command" disabled={busy || !product.sources.length} onClick={queuePipeline} type="button">Run pipeline <span>&#8594;</span></button>
            </div>
            <div className="record-scores">
              <Metric label="Completeness" value={`${Math.round(product.completeness_score * 100)}%`} detail="Required schema coverage" />
              <Metric label="Confidence" value={`${Math.round(product.confidence_score * 100)}%`} detail="Mean canonical confidence" />
              <Metric label="Citations" value={String(product.citations.length)} detail="Grounded external sources" />
            </div>
            <form className="source-form" onSubmit={addSource}>
              <div className="band-heading"><div><span>INGEST EVIDENCE</span><h3>Attach another source</h3></div>
                <div className="segmented-control">{(["text", "url", "pdf"] as SourceMode[]).map((mode) => <button className={sourceMode === mode ? "active" : ""} key={mode} onClick={() => setSourceMode(mode)} type="button">{mode.toUpperCase()}</button>)}</div>
              </div>
              <div className="source-form-fields">
                {sourceMode !== "url" && <label><span>Source label</span><input onChange={(event) => setSourceIdentifier(event.target.value)} required value={sourceIdentifier} /></label>}
                {sourceMode === "text" && <label className="wide"><span>Raw catalog text</span><textarea onChange={(event) => setSourceValue(event.target.value)} required rows={5} value={sourceValue} /></label>}
                {sourceMode === "url" && <label className="wide"><span>Public product URL</span><input onChange={(event) => setSourceValue(event.target.value)} placeholder="https://manufacturer.example/product" required type="url" value={sourceValue} /></label>}
                {sourceMode === "pdf" && <label className="wide file-drop"><span>PDF datasheet</span><input accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} required type="file" /><strong>{file?.name || "Choose a PDF file"}</strong></label>}
                <button className="outline-command" disabled={busy} type="submit">Attach source</button>
              </div>
            </form>
            <div className="record-columns">
              <section>
                <div className="subhead"><span>CANONICAL ATTRIBUTES</span><strong>{product.fields.length}</strong></div>
                <div className="field-table">
                  {product.fields.map((field) => (
                    <div className="field-row" key={field.field_name}>
                      <div><code>{field.field_name}</code><strong>{displayValue(field.value)} {field.unit || ""}</strong>{field.evidence && <small>{field.evidence}</small>}</div>
                      <div><span>{Math.round(field.confidence * 100)}%</span><Status value={field.status} /></div>
                      {field.citations.map((citation) => <a href={citation.url} key={citation.id} rel="noreferrer" target="_blank">{citation.title || "Grounded source"} &#8599;</a>)}
                    </div>
                  ))}
                  {!product.fields.length && <Empty text="Run the pipeline after attaching source evidence." />}
                </div>
              </section>
              <section>
                <div className="subhead"><span>SOURCE LINEAGE</span><strong>{product.sources.length}</strong></div>
                <div className="source-list">
                  {product.sources.map((source) => (
                    <article key={source.id}><span>{source.source_type.toUpperCase()} / RANK {String(source.authority_rank).padStart(2, "0")}</span><strong>{source.source_identifier}</strong><p>{source.raw_content.slice(0, 180)}{source.raw_content.length > 180 ? "..." : ""}</p>{source.storage_backend && <button onClick={() => apiDownload(`/products/${product.id}/sources/${source.id}/content`, source.source_identifier).catch((reason) => onError(messageOf(reason)))} type="button">Download original</button>}</article>
                  ))}
                  {!product.sources.length && <Empty text="No source evidence attached." />}
                </div>
              </section>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function ReviewsView({ reviews, onRefresh, onError }: { reviews: ReviewItem[]; onRefresh: () => Promise<void>; onError: (text: string) => void }) {
  const [selected, setSelected] = useState(reviews[0]?.id || "");
  const active = reviews.find((item) => item.id === selected) || reviews[0];
  useEffect(() => { if (!selected && reviews[0]) setSelected(reviews[0].id); }, [reviews, selected]);
  async function decide(status: "resolved" | "dismissed") {
    if (!active) return;
    try { await apiFetch(`/reviews/${active.id}`, { method: "PATCH", body: JSON.stringify({ status }) }); await onRefresh(); }
    catch (reason) { onError(messageOf(reason)); }
  }
  if (!reviews.length) return <Empty text="The review queue is clear." />;
  return <div className="review-app"><aside>{reviews.map((item) => <button className={active?.id === item.id ? "active" : ""} key={item.id} onClick={() => setSelected(item.id)} type="button"><Status value={item.severity} /><strong>{item.field_name || "Product record"}</strong><span>{item.reason}</span></button>)}</aside><section><div className="band-heading"><div><span>HUMAN DECISION</span><h2>{active.field_name || "Product record"}</h2></div><Status value={active.severity} /></div><dl><dt>Reason</dt><dd>{active.reason}</dd><dt>Product ID</dt><dd><code>{active.product_id}</code></dd><dt>Context</dt><dd><pre>{JSON.stringify(active.payload || {}, null, 2)}</pre></dd></dl><div className="decision-actions"><button className="outline-command" onClick={() => decide("dismissed")} type="button">Dismiss</button><button className="solid-command" onClick={() => decide("resolved")} type="button">Mark resolved <span>&#8594;</span></button></div></section></div>;
}

function BatchesView({ batches, onRefresh, onNotice, onError }: { batches: Batch[]; onRefresh: () => Promise<void>; onNotice: (text: string) => void; onError: (text: string) => void }) {
  const [drafts, setDrafts] = useState<BatchDraft[]>([]);
  const [name, setName] = useState(""); const [mode, setMode] = useState<SourceMode>("text"); const [value, setValue] = useState(""); const [file, setFile] = useState<File | null>(null);
  async function addDraft() {
    try {
      let source: Record<string, string>;
      if (mode === "pdf") { if (!file) throw new Error("Choose a PDF"); source = { source_type: "pdf", source_identifier: file.name, content_base64: await fileToBase64(file) }; }
      else if (mode === "url") source = { source_type: "url", source_identifier: value, url: value };
      else source = { source_type: "text", source_identifier: "batch-catalog", raw_content: value };
      setDrafts((current) => [...current, { name, source }]); setName(""); setValue(""); setFile(null);
    } catch (reason) { onError(messageOf(reason)); }
  }
  async function submitBatch() {
    try {
      const batch = await apiFetch<Batch>("/batches", { method: "POST", body: JSON.stringify({ items: drafts.map((draft) => ({ name: draft.name, sources: [draft.source] })) }) });
      setDrafts([]); await onRefresh(); onNotice(`Batch ${batch.id.slice(0, 8)} queued for the worker.`);
    } catch (reason) { onError(messageOf(reason)); }
  }
  return <div className="batch-layout"><section className="batch-builder"><div className="band-heading"><div><span>NEW BATCH</span><h2>Stage products</h2></div><strong>{drafts.length} ITEMS</strong></div><div className="batch-form"><label><span>Product name</span><input onChange={(event) => setName(event.target.value)} value={name} /></label><div className="segmented-control">{(["text", "url", "pdf"] as SourceMode[]).map((item) => <button className={mode === item ? "active" : ""} key={item} onClick={() => setMode(item)} type="button">{item.toUpperCase()}</button>)}</div>{mode === "pdf" ? <label className="wide"><span>PDF datasheet</span><input accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} type="file" /></label> : <label className="wide"><span>{mode === "url" ? "Public URL" : "Catalog text"}</span><textarea onChange={(event) => setValue(event.target.value)} rows={4} value={value} /></label>}<button className="outline-command" disabled={!name || (mode !== "pdf" && !value) || (mode === "pdf" && !file)} onClick={addDraft} type="button">Add to batch</button></div><div className="draft-list">{drafts.map((draft, index) => <div key={`${draft.name}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{draft.name}</strong><em>{draft.source.source_type}</em><button onClick={() => setDrafts((items) => items.filter((_, itemIndex) => itemIndex !== index))} type="button">Remove</button></div>)}</div><button className="solid-command batch-submit" disabled={!drafts.length} onClick={submitBatch} type="button">Queue batch <span>&#8594;</span></button></section><section className="batch-history"><div className="subhead"><span>RUN HISTORY</span><strong>{batches.length}</strong></div>{batches.map((batch) => <article key={batch.id}><div><Status value={batch.status} /><code>{batch.id.slice(0, 8)}</code></div><strong>{batch.processed_items} / {batch.total_items} processed</strong><span>{batch.failed_items} failed</span></article>)}{!batches.length && <Empty text="No batch runs yet." />}</section></div>;
}

function Operations({ jobs, runs }: { jobs: PipelineJob[]; runs: LlmRun[] }) {
  const estimatedCost = runs.reduce((total, run) => total + run.estimated_cost_usd, 0);
  const averageLatency = runs.length ? Math.round(runs.reduce((total, run) => total + run.latency_ms, 0) / runs.length) : 0;
  return <><div className="metric-strip operations-metrics"><Metric label="Provider attempts" value={String(runs.length)} detail="Latest telemetry window" /><Metric label="Average latency" value={`${averageLatency} ms`} detail="All provider attempts" /><Metric label="Estimated cost" value={`$${estimatedCost.toFixed(4)}`} detail="Configured token rates" /><Metric label="Pipeline jobs" value={String(jobs.length)} detail="Latest persisted jobs" /></div><div className="operations-grid"><section><div className="subhead"><span>LLM TELEMETRY</span><strong>ADMIN</strong></div><div className="ops-table">{runs.map((run) => <div key={run.id}><Status value={run.status} /><strong>{run.provider}</strong><span>{run.task}</span><code>{run.latency_ms} ms</code><small>{run.input_tokens + run.output_tokens} tokens</small></div>)}{!runs.length && <Empty text="Admin telemetry is unavailable or no LLM calls have run." />}</div></section><section><div className="subhead"><span>PIPELINE JOBS</span><strong>{jobs.length}</strong></div><div className="job-list">{jobs.map((job) => <article key={job.id}><div><Status value={job.status} /><code>{job.id.slice(0, 8)}</code></div><strong>{job.stages?.join(" / ") || "Complete pipeline"}</strong><span>{job.error || new Date(job.created_at).toLocaleString()}</span></article>)}</div></section></div></>;
}

function Metric({ label, value, detail, alert = false }: { label: string; value: string; detail: string; alert?: boolean }) { return <article className={alert ? "metric alert" : "metric"}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>; }
function Progress({ value }: { value: number }) { return <div className="progress"><i style={{ width: `${Math.max(2, Math.round(value * 100))}%` }} /><span>{Math.round(value * 100)}%</span></div>; }
function Status({ value }: { value: string }) { return <em className={`status-chip ${value.replaceAll("_", "-")}`}>{value.replaceAll("_", " ")}</em>; }
function Empty({ text }: { text: string }) { return <div className="empty-state">{text}</div>; }
function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not found";
  if (Array.isArray(value)) {
    if (value.every((item) => typeof item !== "object")) return value.join(", ");
    return value.map((item) => {
      if (item && typeof item === "object" && "pressure" in item && "torque" in item) {
        const row = item as { pressure?: { value?: unknown; unit?: unknown }; torque?: { value?: unknown; unit?: unknown } };
        return `${row.pressure?.value ?? "?"} ${row.pressure?.unit ?? ""} -> ${row.torque?.value ?? "?"} ${row.torque?.unit ?? ""}`;
      }
      return JSON.stringify(item);
    }).join("; ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${key}: ${String(item)}`).join(", ");
  }
  return String(value);
}
function messageOf(reason: unknown) { return reason instanceof Error ? reason.message : "Request failed"; }
async function waitForJob(jobId: string, onDone: () => Promise<void>) { for (let attempt = 0; attempt < 30; attempt += 1) { await new Promise((resolve) => setTimeout(resolve, 1000)); const job = await apiFetch<PipelineJob>(`/pipeline/jobs/${jobId}`); if (["completed", "failed"].includes(job.status)) { await onDone(); return; } } }
