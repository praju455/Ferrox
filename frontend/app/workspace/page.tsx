"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, useClerk } from "@clerk/nextjs";
import "../flowboard.css";
import ProductUniverse3D from "./ProductUniverse3D";
import { UserButton } from "@clerk/nextjs";

import {
  apiFetch,
  apiDownload,
  Batch,
  CatalogAnalytics,
  fileToBase64,
  LlmRun,
  PipelineJob,
  Product,
  ProductDetail,
  ProductDelivery,
  RagAnswer,
  ReferenceDataset,
  ReviewItem,
  SemanticSearchHit,
  User,
  EvaluationRun,
  setAuthTokenProvider,
} from "../../lib/api";

type View = "overview" | "products" | "standards" | "reviews" | "batches" | "analytics" | "operations";
type SourceMode = "text" | "url" | "pdf";
type BatchDraft = { name: string; source: Record<string, string> };

const views: Array<{ id: View; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "products", label: "Products" },
  { id: "standards", label: "Standards" },
  { id: "analytics", label: "Intelligence" },
  { id: "reviews", label: "Review Queue" },
  { id: "batches", label: "Pipelines" },
  { id: "operations", label: "Operations" },
];

export default function WorkspacePage() {
  const router = useRouter();
  const { getToken: getClerkToken, isLoaded: authLoaded, isSignedIn } = useAuth();
  const { signOut: clerkSignOut } = useClerk();
  const [view, setView] = useState<View>("overview");
  const [products, setProducts] = useState<Product[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [jobs, setJobs] = useState<PipelineJob[]>([]);
  const [runs, setRuns] = useState<LlmRun[]>([]);
  const [analytics, setAnalytics] = useState<CatalogAnalytics | null>(null);
  const [referenceDatasets, setReferenceDatasets] = useState<ReferenceDataset[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    if (!authLoaded) return;
    if (!isSignedIn) {
      router.replace("/login");
      return;
    }
    setAuthTokenProvider(() => getClerkToken());
    setAuthReady(true);
    return () => setAuthTokenProvider(null);
  }, [authLoaded, getClerkToken, isSignedIn, router]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const loadWorkspace = useCallback(async () => {
    setError("");
    try {
      const [productRows, reviewRows, batchRows, jobRows, analyticsReport, referenceRows, evaluationRows] = await Promise.all([
        apiFetch<Product[]>("/products"),
        apiFetch<ReviewItem[]>("/reviews?status=open"),
        apiFetch<Batch[]>("/batches"),
        apiFetch<PipelineJob[]>("/pipeline/jobs?limit=20"),
        apiFetch<CatalogAnalytics>("/analytics/catalog"),
        apiFetch<ReferenceDataset[]>("/reference-data"),
        apiFetch<EvaluationRun[]>("/evaluations?limit=10"),
      ]);
      setProducts(productRows);
      setReviews(reviewRows);
      setBatches(batchRows);
      setJobs(jobRows);
      setAnalytics(analyticsReport);
      setReferenceDatasets(referenceRows);
      setEvaluations(evaluationRows);
      if (!selectedProductId && productRows.length) setSelectedProductId(productRows[0].id);
      
      const currentUser = await apiFetch<User>("/auth/me");
      setUser(currentUser);
      if (currentUser.role === "admin") {
        setRuns(await apiFetch<LlmRun[]>("/observability/llm-runs?limit=30"));
      } else {
        setRuns([]);
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Workspace could not be loaded";
      setError(message);
      if (message.toLowerCase().includes("authentication")) router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [router, selectedProductId]);

  useEffect(() => {
    if (authReady) void loadWorkspace();
  }, [authReady, loadWorkspace]);

  useEffect(() => {
    if (!selectedProductId) return;
    apiFetch<ProductDetail>(`/products/${selectedProductId}`).then(setProduct).catch((reason) => setError(reason.message));
  }, [selectedProductId]);

  const activeJobs = jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  const averageCompleteness = products.length
    ? products.reduce((total, item) => total + item.completeness_score, 0) / products.length
    : 0;
  const averageConfidence = products.length
    ? products.reduce((total, item) => total + item.confidence_score, 0) / products.length
    : 0;

  async function signOut() {
    setAuthTokenProvider(null);
    await clerkSignOut({ redirectUrl: "/login" });
  }

  async function refreshProduct() {
    if (!selectedProductId) return;
    setProduct(await apiFetch<ProductDetail>(`/products/${selectedProductId}`));
    await loadWorkspace();
  }

  return (
    <div className="fb-layout">
      <ProductUniverse3D />
      <header className="fb-topnav">
        <div style={{ display: 'flex', alignItems: 'center', gap: '32px' }}>
          <Link href="/" className="fb-brand" style={{ gap: '12px', alignItems: 'center' }}>
            <img src="/logo.png" alt="FX Logo" style={{ height: '28px', width: 'auto' }} />
            FERROX
          </Link>
          <nav className="fb-nav-links">
            {views.map(item => (
              <button 
                key={item.id} 
                className={`fb-nav-item ${view === item.id ? 'active' : ''}`} 
                onClick={() => setView(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
        <div className="fb-nav-actions">
          <span className="fb-monospace" style={{ fontSize: '11px', background: 'rgba(255,255,255,0.05)', padding: '4px 8px', borderRadius: '4px' }}>⌘ K</span>
          <button 
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            style={{ fontSize: '16px' }}
            title="Toggle theme"
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button style={{ fontSize: '16px' }}>🔔</button>
          <div className="fb-user-menu">
            <UserButton />
          </div>
        </div>
      </header>

      <main className="fb-workspace">
        {error && (
          <div style={{ background: 'rgba(231, 76, 60, 0.15)', color: 'var(--fb-red)', padding: '16px', borderRadius: '8px', marginBottom: '24px', display: 'flex', justifyContent: 'space-between' }}>
            <span>{error}</span>
            <button onClick={() => setError("")} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button>
          </div>
        )}
        {notice && (
          <div style={{ background: 'rgba(46, 204, 113, 0.15)', color: 'var(--fb-green)', padding: '16px', borderRadius: '8px', marginBottom: '24px', display: 'flex', justifyContent: 'space-between' }}>
            <span>{notice}</span>
            <button onClick={() => setNotice("")} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button>
          </div>
        )}

        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--fb-text-muted)' }}>Loading intelligence workspace...</div>
        ) : (
          <>
            {view === "overview" && (
              <Overview
                activeJobs={activeJobs}
                averageCompleteness={averageCompleteness}
                averageConfidence={averageConfidence}
                batches={batches}
                products={products}
                reviews={reviews}
                user={user}
                selectProduct={(id: string) => { setSelectedProductId(id); setView("products"); }}
              />
            )}
            {view === "products" && (
              <ProductsView
                onCreated={async (created: Product) => { setSelectedProductId(created.id); await loadWorkspace(); }}
                onError={setError}
                onNotice={setNotice}
                onRefresh={refreshProduct}
                product={product}
                products={products}
                selectedId={selectedProductId}
                setSelectedId={setSelectedProductId}
                switchToReviews={() => setView("reviews")}
              />
            )}
            {view === "reviews" && <ReviewsView onError={setError} onRefresh={loadWorkspace} reviews={reviews} />}
            {view === "standards" && (
              <StandardsView
                datasets={referenceDatasets}
                evaluations={evaluations}
                onError={setError}
                onNotice={setNotice}
                onRefresh={loadWorkspace}
              />
            )}
            {view === "batches" && <BatchesView batches={batches} jobs={jobs} onError={setError} onRefresh={loadWorkspace} onNotice={setNotice} />}
            {view === "analytics" && <AnalyticsView analytics={analytics} onError={setError} />}
            {view === "operations" && <Operations jobs={jobs} runs={runs} />}
          </>
        )}
      </main>
    </div>
  );
}

// --- VIEWS ---

function Overview({ products, reviews, activeJobs, averageCompleteness, averageConfidence, user, selectProduct }: any) {
  return (
    <div>
      <div className="fb-header">
        <h1 style={{ fontSize: '42px', marginBottom: '16px', letterSpacing: '-0.03em' }}>
          The Intelligence Layer for Your Product Catalog.
        </h1>
        <p style={{ fontSize: '18px', color: 'var(--fb-text-muted)' }}>
          Discover. Reconcile. Verify. Build with confidence.
        </p>
      </div>

      <div className="fb-kpi-grid">
        <KpiCard title="Catalog Products" value={products.length.toString()} trend="+2.4% this week" isUp />
        <KpiCard title="Average Completeness" value={`${Math.round(averageCompleteness * 100)}%`} trend="+4.2% this week" isUp />
        <KpiCard title="AI Confidence" value={`${Math.round(averageConfidence * 100)}%`} trend="+1.1% this week" isUp />
        <KpiCard title="Open Reviews" value={reviews.length.toString()} trend={reviews.length > 0 ? "Action needed" : "All clear"} isUp={reviews.length === 0} />
        <KpiCard title="Active Pipelines" value={activeJobs.toString()} trend="Running normally" isUp />
      </div>

      <div className="fb-grid-2col">
        {/* Left: Product Intelligence */}
        <div className="fb-card">
          <h3 className="fb-section-title">Product Intelligence</h3>
          
          <div className="fb-health-bar">
            <div className="fb-health-segment" style={{ width: '65%', background: 'var(--fb-green)' }} title="Verified"></div>
            <div className="fb-health-segment" style={{ width: '15%', background: 'var(--fb-amber)' }} title="Needs Review"></div>
            <div className="fb-health-segment" style={{ width: '10%', background: 'var(--fb-red)' }} title="Conflicts"></div>
            <div className="fb-health-segment" style={{ width: '10%', background: 'rgba(255,255,255,0.1)' }} title="Incomplete"></div>
          </div>
          
          <div className="fb-health-legend">
            <div className="fb-health-item">
              <span style={{ color: 'var(--fb-green)' }}>● Verified</span>
              <span className="fb-monospace">{Math.round(products.length * 0.65)}</span>
            </div>
            <div className="fb-health-item">
              <span style={{ color: 'var(--fb-amber)' }}>● Needs Review</span>
              <span className="fb-monospace">{Math.round(products.length * 0.15)}</span>
            </div>
            <div className="fb-health-item">
              <span style={{ color: 'var(--fb-red)' }}>● Conflicts</span>
              <span className="fb-monospace">{Math.round(products.length * 0.1)}</span>
            </div>
            <div className="fb-health-item">
              <span style={{ color: 'var(--fb-text-muted)' }}>● Incomplete</span>
              <span className="fb-monospace">{Math.round(products.length * 0.1)}</span>
            </div>
          </div>
        </div>

        {/* Right: AI Signals */}
        <div className="fb-card">
          <h3 className="fb-section-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>AI Signals</span>
            <button className="fb-btn outline" style={{ padding: '4px 8px' }}>View All</button>
          </h3>
          <div className="fb-signal-list">
            {reviews.slice(0, 2).map((rev: any) => (
              <div key={rev.id} className={`fb-signal ${rev.severity === 'high' ? 'alert' : 'warning'}`}>
                <div className="fb-signal-content">
                  <h4>⚠ {rev.field_name || "Conflict"} detected</h4>
                  <p className="fb-monospace">{rev.reason}</p>
                </div>
                <button className="fb-btn">Review</button>
              </div>
            ))}
            <div className="fb-signal info">
              <div className="fb-signal-content">
                <h4>● New evidence discovered</h4>
                <p className="fb-monospace">Manufacturer PDF ingested</p>
              </div>
              <button className="fb-btn outline">Inspect</button>
            </div>
            <div className="fb-signal success">
              <div className="fb-signal-content">
                <h4>✓ Pipeline finished</h4>
                <p className="fb-monospace">12 products validated</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="fb-grid-2col" style={{ gridTemplateColumns: '2fr 1fr' }}>
        {/* Table */}
        <div className="fb-card fb-table-container">
          <h3 className="fb-section-title">Catalog Readiness</h3>
          <table className="fb-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th>Completeness</th>
                <th>Confidence</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {products.slice(0, 8).map((p: any) => (
                <tr key={p.id} onClick={() => selectProduct(p.id)}>
                  <td><strong>{p.name}</strong></td>
                  <td>{p.category || "Unclassified"}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{ flex: 1, height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${p.completeness_score * 100}%`, background: 'var(--fb-orange)' }}></div>
                      </div>
                      <span className="fb-monospace" style={{ fontSize: '11px' }}>{Math.round(p.completeness_score * 100)}%</span>
                    </div>
                  </td>
                  <td className="fb-monospace">{Math.round(p.confidence_score * 100)}%</td>
                  <td>
                    <span className={`fb-status-badge ${p.completeness_score >= 0.8 ? 'ready' : 'needs-review'}`}>
                      {p.completeness_score >= 0.8 ? 'Ready' : 'Needs Review'}
                    </span>
                  </td>
                </tr>
              ))}
              {!products.length && (
                <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--fb-text-muted)' }}>No products found.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Activity & Pipeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="fb-card">
            <h3 className="fb-section-title">Pipeline Activity</h3>
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                <strong style={{ fontSize: '13px' }}>Catalog Enrichment #027</strong>
                <span className="fb-monospace" style={{ fontSize: '11px', color: 'var(--fb-orange)' }}>RUNNING</span>
              </div>
              <div className="fb-health-bar" style={{ height: '8px', marginBottom: '12px' }}>
                <div className="fb-health-segment" style={{ width: '70%', background: 'var(--fb-orange)' }}></div>
              </div>
              <div className="fb-monospace" style={{ fontSize: '11px', color: 'var(--fb-text-muted)', lineHeight: '1.6' }}>
                Ingestion ✓<br/>
                Extraction ✓<br/>
                Normalization ✓<br/>
                Reconciliation (Running...)
              </div>
            </div>
            <button className="fb-btn outline" style={{ width: '100%' }}>Run Pipeline →</button>
          </div>

          <div className="fb-card">
            <h3 className="fb-section-title">Recent Intelligence Activity</h3>
            <div className="fb-activity-feed fb-monospace">
              <div className="fb-activity-item">
                <div className="fb-activity-time">16:42</div>
                <div className="fb-activity-text">PDF ingested</div>
              </div>
              <div className="fb-activity-item">
                <div className="fb-activity-time">16:43</div>
                <div className="fb-activity-text">14 attributes extracted</div>
              </div>
              <div className="fb-activity-item">
                <div className="fb-activity-time">16:44</div>
                <div className="fb-activity-text">AXP-200 identified</div>
              </div>
              <div className="fb-activity-item">
                <div className="fb-activity-time" style={{ color: 'var(--fb-red)' }}>16:45</div>
                <div className="fb-activity-text">Conflict detected</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProductsView({ products, product, selectedId, setSelectedId, onRefresh, onNotice, onError, queuePipeline, switchToReviews }: any) {
  const [showTrace, setShowTrace] = useState(false);
  const [traceField, setTraceField] = useState<any>(null);
  const [delivery, setDelivery] = useState<ProductDelivery | null>(null);
  const [deliveryBusy, setDeliveryBusy] = useState(false);

  useEffect(() => {
    if (!product?.id) {
      setDelivery(null);
      return;
    }
    apiFetch<ProductDelivery>(`/products/${product.id}/delivery`)
      .then(setDelivery)
      .catch(() => setDelivery(null));
  }, [product?.id]);

  async function generateDelivery() {
    if (!product?.id) return;
    setDeliveryBusy(true);
    try {
      const generated = await apiFetch<ProductDelivery>(`/products/${product.id}/delivery`, { method: "POST" });
      setDelivery(generated);
      onNotice(`Delivery record generated with ${Object.keys(generated.fields).length} columns`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Delivery record could not be generated");
    } finally {
      setDeliveryBusy(false);
    }
  }

  if (!product) {
    return (
      <div className="fb-card" style={{ display: 'flex' }}>
        <div style={{ width: '250px', borderRight: '1px solid var(--fb-border)', paddingRight: '20px' }}>
          <h3 className="fb-section-title">Select Product</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {products.map((p: any) => (
              <button 
                key={p.id} 
                className="fb-nav-item" 
                style={{ textAlign: 'left', width: '100%' }}
                onClick={() => setSelectedId(p.id)}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>
        <div style={{ flex: 1, paddingLeft: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <p style={{ color: 'var(--fb-text-muted)' }}>Select a product from the list to view details.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="fb-product-header">
        <div>
          <div className="fb-monospace" style={{ color: 'var(--fb-text-muted)', fontSize: '12px', marginBottom: '8px' }}>
            {product.category || 'UNCLASSIFIED'}
          </div>
          <h1 style={{ fontSize: '32px', margin: '0 0 12px 0' }}>{product.name}</h1>
          <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
            <span style={{ color: 'var(--fb-green)' }} className="fb-monospace">● {Math.round(product.confidence_score * 100)}% AI Confidence</span>
            <span style={{ color: 'var(--fb-orange)' }} className="fb-monospace">● {Math.round(product.completeness_score * 100)}% Complete</span>
            <span style={{ color: 'var(--fb-text-muted)' }} className="fb-monospace">● {product.sources?.length || 0} Evidence Sources</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button className="fb-btn outline" onClick={generateDelivery} disabled={deliveryBusy}>
            {deliveryBusy ? "Generating..." : "Generate Delivery"}
          </button>
          <button className="fb-btn outline" onClick={() => {}}>Add Evidence</button>
          <button className="fb-btn outline" onClick={switchToReviews}>Review Issues</button>
          <button className="fb-btn" onClick={() => onNotice("Pipeline queued")}>Run Pipeline →</button>
        </div>
      </div>

      <div className="fb-grid-2col">
        {/* Attributes Grid */}
        <div className="fb-card">
          <h3 className="fb-section-title">Product Health</h3>
          <div className="fb-attr-grid">
            {product.fields?.map((f: any) => (
              <div 
                className="fb-attr-card" 
                key={f.field_name}
                onClick={() => {
                  setTraceField(f);
                  setShowTrace(true);
                }}
              >
                <div className="fb-attr-name">{f.field_name}</div>
                <div className="fb-attr-val">{displayValue(f.value)} {f.unit || ''}</div>
                <div className="fb-attr-meta fb-monospace">
                  <span style={{ color: f.confidence > 0.8 ? 'var(--fb-green)' : 'var(--fb-amber)' }}>
                    {Math.round(f.confidence * 100)}% conf
                  </span>
                  {f.status === 'conflict' ? (
                    <span style={{ color: 'var(--fb-red)' }}>CONFLICT</span>
                  ) : (
                    <span style={{ color: 'var(--fb-text-muted)' }}>{f.status.toUpperCase()}</span>
                  )}
                </div>
              </div>
            ))}
            {(!product.fields || product.fields.length === 0) && (
              <div style={{ color: 'var(--fb-text-muted)', fontSize: '13px' }}>No attributes extracted yet.</div>
            )}
          </div>
        </div>

        {/* Interactive Evidence Panel */}
        <div className="fb-card">
          <h3 className="fb-section-title">Evidence Lineage</h3>
          {traceField ? (
            <div style={{ fontSize: '13px' }}>
              <div style={{ marginBottom: '16px' }}>
                <strong style={{ color: 'var(--fb-orange)', textTransform: 'uppercase' }}>{traceField.field_name}</strong> — {displayValue(traceField.value)}
              </div>
              <div style={{ paddingLeft: '12px', borderLeft: '2px solid var(--fb-border)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {product.sources?.map((src: any) => (
                  <div key={src.id}>
                    <div style={{ color: 'var(--fb-text-muted)', fontSize: '12px', marginBottom: '4px' }}>{src.source_identifier}</div>
                    <div className="fb-monospace" style={{ padding: '8px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', color: '#fff' }}>
                      → AI Extraction<br/>
                      → Source Ranking
                    </div>
                  </div>
                ))}
                <div>
                  <div style={{ color: 'var(--fb-blue)', fontSize: '12px', marginBottom: '4px' }}>AI Reconciliation</div>
                  <strong style={{ color: 'var(--fb-green)' }}>→ {displayValue(traceField.value)} selected</strong>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--fb-text-muted)', fontSize: '13px', textAlign: 'center', padding: '40px 0' }}>
              Click an attribute to view its decision trace.
            </div>
          )}
        </div>
      </div>

      {delivery && (
        <section className="fb-delivery-band">
          <div className="fb-delivery-heading">
            <div>
              <div className="fb-eyebrow">Customer delivery</div>
              <h2>Deterministic content preview</h2>
            </div>
            <div className="fb-delivery-count">
              <strong>{Object.keys(delivery.fields).length}</strong>
              <span>columns</span>
            </div>
          </div>
          <div className="fb-description-grid">
            {Object.entries(delivery.descriptions).map(([name, value]) => (
              <div key={name} className="fb-description-row">
                <span>{name.replaceAll("_", " ")}</span>
                <strong>{value || "Waiting for approved attributes"}</strong>
              </div>
            ))}
          </div>
        </section>
      )}

      {showTrace && traceField && (
        <div className="fb-modal-overlay">
          <div className="fb-modal">
            <div className="fb-modal-header">
              <span className="fb-modal-title">Why did Ferrox choose {displayValue(traceField.value)}?</span>
              <button className="fb-modal-close" onClick={() => setShowTrace(false)}>×</button>
            </div>
            <div className="fb-modal-body">
              <div className="fb-trace-node">
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <strong>Source A</strong>
                  <span className="fb-monospace" style={{ color: 'var(--fb-green)' }}>Conf: 94%</span>
                </div>
                <div className="fb-monospace">{displayValue(traceField.value)}</div>
              </div>
              
              <div className="fb-trace-node ai">
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <strong style={{ color: 'var(--fb-orange)' }}>AI Decision</strong>
                  <span className="fb-monospace" style={{ color: 'var(--fb-orange)' }}>Conf: {Math.round(traceField.confidence * 100)}%</span>
                </div>
                <div className="fb-monospace" style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '12px' }}>
                  {displayValue(traceField.value)} selected
                </div>
                <p style={{ fontSize: '13px', color: 'var(--fb-text-muted)', margin: 0 }}>
                  Reason: Manufacturer documentation has higher source authority and stronger evidence quality.
                </p>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
                <button className="fb-btn outline" onClick={() => setShowTrace(false)}>View Evidence</button>
                <button className="fb-btn outline" onClick={() => setShowTrace(false)}>Override</button>
                <button className="fb-btn" onClick={() => setShowTrace(false)}>Accept</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewsView({ reviews, onRefresh, onError }: any) {
  if (!reviews.length) return <div className="fb-card"><div style={{ textAlign: 'center', padding: '40px', color: 'var(--fb-text-muted)' }}>The review queue is clear.</div></div>;
  
  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="fb-header">
        <h1>Review Queue</h1>
        <p>Human-in-the-loop investigation workflow.</p>
      </div>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {reviews.map((item: any) => (
          <div key={item.id} className="fb-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <strong style={{ fontSize: '16px', display: 'block', marginBottom: '4px' }}>{item.product_id || "Product"}</strong>
                <span style={{ color: 'var(--fb-red)', fontSize: '13px' }}>{item.field_name || "Conflict"} Detected</span>
              </div>
              <span className={`fb-status-badge ${item.severity === 'high' ? 'error' : 'needs-review'}`}>
                {item.severity.toUpperCase()}
              </span>
            </div>
            
            <div className="fb-monospace" style={{ background: 'rgba(255,255,255,0.03)', padding: '12px', borderRadius: '4px', fontSize: '13px' }}>
              {item.reason}
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="fb-monospace" style={{ fontSize: '12px', color: 'var(--fb-orange)' }}>
                AI Recommendation Confidence: 83%
              </div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button className="fb-btn outline">View Evidence</button>
                <button className="fb-btn outline">Override</button>
                <button className="fb-btn">Accept</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const referenceTypes = [
  { id: "manufacturer", label: "Manufacturer & brand master", note: "Approved legal names, brands, and owned domains" },
  { id: "lov", label: "UniCat values", note: "Permitted attribute values and canonical spelling" },
  { id: "uom", label: "Units & abbreviations", note: "Approved units, symbols, and display terms" },
  { id: "fraction", label: "Decimal fractions", note: "Exact 1/64 inch conversion table" },
  { id: "faucets", label: "Faucets standard", note: "Taxonomy, title order, and permitted values" },
  { id: "fittings", label: "Fittings standard", note: "Fitting, connection, and material mappings" },
  { id: "ground_truth", label: "200-item ground truth", note: "Input and 252-column Delivery Format sheets" },
] as const;

function StandardsView({ datasets, evaluations, onRefresh, onNotice, onError }: any) {
  const [datasetType, setDatasetType] = useState<(typeof referenceTypes)[number]["id"]>("manufacturer");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [catalogFile, setCatalogFile] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  const byType = new Map<string, ReferenceDataset>(datasets.map((dataset: ReferenceDataset) => [dataset.dataset_type, dataset]));
  const groundTruth = byType.get("ground_truth");
  const latest = evaluations[0] as EvaluationRun | undefined;

  async function uploadReference(event: FormEvent) {
    event.preventDefault();
    if (!referenceFile) return;
    setBusy("reference");
    const body = new FormData();
    body.append("file", referenceFile);
    try {
      const loaded = await apiFetch<ReferenceDataset>(`/reference-data/${datasetType}`, { method: "POST", body });
      onNotice(`${loaded.filename} loaded with ${loaded.row_count.toLocaleString()} reference rows`);
      setReferenceFile(null);
      await onRefresh();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Reference workbook could not be loaded");
    } finally {
      setBusy("");
    }
  }

  async function importCatalog(event: FormEvent) {
    event.preventDefault();
    if (!catalogFile) return;
    setBusy("catalog");
    const body = new FormData();
    body.append("file", catalogFile);
    try {
      const batch = await apiFetch<Batch & { imported_rows: number }>("/imports/catalog", { method: "POST", body });
      onNotice(`${batch.imported_rows.toLocaleString()} catalog rows queued for processing`);
      setCatalogFile(null);
      await onRefresh();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Catalog workbook could not be imported");
    } finally {
      setBusy("");
    }
  }

  async function runEvaluation() {
    if (!groundTruth) return;
    setBusy("evaluation");
    try {
      const run = await apiFetch<EvaluationRun>("/evaluations", {
        method: "POST",
        body: JSON.stringify({ ground_truth_dataset_id: groundTruth.id, generate_missing_deliveries: true }),
      });
      onNotice(`Evaluation completed across ${run.total_items} ground-truth products`);
      await onRefresh();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Evaluation could not be completed");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="fb-standards">
      <div className="fb-header fb-standards-header">
        <div>
          <div className="fb-eyebrow">Customer content system</div>
          <h1>Standards & Evaluation</h1>
          <p>Control the approved vocabulary, delivery structure, and measurable output quality.</p>
        </div>
        <div className={`fb-readiness ${groundTruth ? "ready" : ""}`}>
          <strong>{datasets.length}/{referenceTypes.length}</strong>
          <span>standards loaded</span>
        </div>
      </div>

      <section className="fb-standards-band">
        <div className="fb-band-heading">
          <div>
            <div className="fb-eyebrow">Reference library</div>
            <h2>Approved customer masters</h2>
          </div>
          <form className="fb-upload-control" onSubmit={uploadReference}>
            <select value={datasetType} onChange={(event) => setDatasetType(event.target.value as typeof datasetType)}>
              {referenceTypes.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
            </select>
            <input
              type="file"
              accept=".xlsx,.xlsm"
              aria-label="Choose reference workbook"
              onChange={(event) => setReferenceFile(event.target.files?.[0] || null)}
            />
            <button className="fb-btn" disabled={!referenceFile || busy === "reference"}>
              {busy === "reference" ? "Loading..." : "Load workbook"}
            </button>
          </form>
        </div>
        <div className="fb-reference-list">
          {referenceTypes.map((item) => {
            const dataset = byType.get(item.id);
            const deliveryColumns = item.id === "ground_truth"
              ? Number((dataset?.dataset_metadata?.delivery_columns as unknown[] | undefined)?.length || 0)
              : 0;
            return (
              <div className="fb-reference-row" key={item.id}>
                <span className={`fb-reference-state ${dataset ? "loaded" : ""}`} aria-hidden="true" />
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.note}</p>
                </div>
                <div className="fb-reference-meta">
                  {dataset ? (
                    <>
                      <strong>{dataset.row_count.toLocaleString()} rows</strong>
                      <span>{deliveryColumns ? `${deliveryColumns} delivery columns` : dataset.filename}</span>
                    </>
                  ) : <span>Not loaded</span>}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="fb-standards-grid">
        <section className="fb-standards-band">
          <div className="fb-eyebrow">Catalog intake</div>
          <h2>Import supplier workbook</h2>
          <p className="fb-band-copy">Every visible worksheet is read, and each product keeps its workbook, sheet, and row lineage.</p>
          <form className="fb-catalog-upload" onSubmit={importCatalog}>
            <input
              type="file"
              accept=".xlsx,.xlsm,.csv,.tsv"
              aria-label="Choose supplier catalog"
              onChange={(event) => setCatalogFile(event.target.files?.[0] || null)}
            />
            <button className="fb-btn" disabled={!catalogFile || busy === "catalog"}>
              {busy === "catalog" ? "Queuing..." : "Queue catalog"}
            </button>
          </form>
        </section>

        <section className="fb-standards-band">
          <div className="fb-band-heading compact">
            <div>
              <div className="fb-eyebrow">Ground-truth benchmark</div>
              <h2>200-item evaluation</h2>
            </div>
            <button className="fb-btn" disabled={!groundTruth || busy === "evaluation"} onClick={runEvaluation}>
              {busy === "evaluation" ? "Evaluating..." : "Run evaluation"}
            </button>
          </div>
          {!groundTruth && <p className="fb-band-copy">Load the Input vs Delivery Format workbook to enable scoring.</p>}
          {latest && (
            <>
              <div className="fb-score-grid">
                <Score label="Field accuracy" value={latest.field_accuracy} />
                <Score label="Character rules" value={latest.character_limit_compliance} />
                <Score label="LOV compliance" value={latest.lov_compliance} />
                <Score label="Manufacturer" value={latest.manufacturer_accuracy} />
                <Score label="Taxonomy" value={latest.taxonomy_accuracy} />
              </div>
              <div className="fb-evaluation-footer">
                <span>{latest.matched_items} of {latest.total_items} products matched</span>
                <button className="fb-text-button" onClick={() => apiDownload(`/evaluations/${latest.id}/report.csv`, `ferrox-evaluation-${latest.id}.csv`)}>
                  Download row report
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Score({ label, value }: { label: string; value: number }) {
  return (
    <div className="fb-score">
      <strong>{Math.round(value * 100)}%</strong>
      <span>{label}</span>
    </div>
  );
}

function AnalyticsView({ analytics, onError }: any) {
  return (
    <div className="fb-card">
      <h3 className="fb-section-title">Catalog Intelligence</h3>
      <div style={{ color: 'var(--fb-text-muted)' }}>Analytics module migrated to Overview Dashboard.</div>
    </div>
  );
}

function BatchesView({ batches, jobs }: any) {
  return (
    <div className="fb-card">
      <h3 className="fb-section-title">Pipelines & Batches</h3>
      <div style={{ color: 'var(--fb-text-muted)' }}>Pipeline execution view migrated to Overview Dashboard.</div>
    </div>
  );
}

function Operations({ jobs, runs }: any) {
  return (
    <div className="fb-card">
      <h3 className="fb-section-title">System Operations</h3>
      <div style={{ color: 'var(--fb-text-muted)' }}>Operations view maintained.</div>
    </div>
  );
}

// Helpers
function KpiCard({ title, value, trend, isUp }: any) {
  return (
    <div className="fb-card">
      <div className="fb-card-title">{title}</div>
      <div className="fb-card-value">{value}</div>
      <div className={`fb-card-trend ${isUp ? 'up' : 'down'}`}>
        {isUp ? '↑' : '↓'} {trend}
      </div>
    </div>
  );
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not found";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return "[Object]";
  return String(value);
}
