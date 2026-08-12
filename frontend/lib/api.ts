export type User = {
  id: string;
  email: string;
  full_name: string;
  role: "reviewer" | "admin";
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

export type Citation = {
  id: string;
  extracted_field_id: string;
  url: string;
  title: string | null;
  cited_text: string | null;
  provider: string;
  retrieved_at: string;
};

export type ProductField = {
  field_name: string;
  value: unknown;
  unit: string | null;
  confidence: number;
  source_id: string | null;
  status: string;
  evidence: string | null;
  alternatives: Array<Record<string, unknown>> | null;
  validation: Record<string, unknown> | null;
  citations: Citation[];
};

export type Source = {
  id: string;
  product_id: string;
  source_type: "pdf" | "url" | "text";
  source_identifier: string;
  raw_content: string;
  storage_backend: string | null;
  content_length: number | null;
  content_sha256: string | null;
  authority_rank: number;
  created_at: string;
};

export type Product = {
  id: string;
  name: string;
  category: string | null;
  dynamic_schema: Record<string, unknown> | null;
  completeness_score: number;
  confidence_score: number;
  created_at: string;
  updated_at: string;
};

export type ProductDetail = Product & {
  sources: Source[];
  fields: ProductField[];
  citations: Citation[];
};

export type ReviewItem = {
  id: string;
  product_id: string;
  field_name: string | null;
  reason: string;
  severity: "low" | "medium" | "high";
  status: "open" | "resolved" | "dismissed";
  payload: Record<string, unknown> | null;
};

export type BatchItem = {
  id: string;
  batch_id: string;
  product_id: string | null;
  status: string;
  error: string | null;
  payload: Record<string, unknown>;
};

export type Batch = {
  id: string;
  status: string;
  total_items: number;
  processed_items: number;
  failed_items: number;
  items?: BatchItem[];
};

export type PipelineJob = {
  id: string;
  product_id: string;
  status: string;
  source_ids: string[] | null;
  stages: string[] | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type LlmRun = {
  id: string;
  product_id: string | null;
  provider: string;
  model: string;
  task: string;
  status: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  error: string | null;
  created_at: string;
};

const defaultApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api/v1";

export function getApiBase() {
  if (typeof window === "undefined") return defaultApiBase;
  return (localStorage.getItem("ferrox.ui.apiBase") || defaultApiBase).replace(/\/$/, "");
}

export function setApiBase(value: string) {
  localStorage.setItem("ferrox.ui.apiBase", value.replace(/\/$/, ""));
}

export function getToken() {
  return typeof window === "undefined" ? "" : sessionStorage.getItem("ferrox.auth.token") || "";
}

export function clearToken() {
  sessionStorage.removeItem("ferrox.auth.token");
}

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${getApiBase()}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const result = (await response.json()) as { access_token: string };
  sessionStorage.setItem("ferrox.auth.token", result.access_token);
  return result;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${getApiBase()}${path}`, { ...init, headers });
  if (response.status === 401 && typeof window !== "undefined") {
    clearToken();
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiDownload(path: string, filename: string) {
  const token = getToken();
  const response = await fetch(`${getApiBase()}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function errorMessage(response: Response) {
  try {
    const body = await response.json();
    return body.detail || `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export async function fileToBase64(file: File) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunk) {
    binary += String.fromCharCode(...Array.from(bytes.subarray(offset, offset + chunk)));
  }
  return btoa(binary);
}
