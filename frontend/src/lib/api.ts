import type {
  ScanResponse,
  PatchProposal,
  PullRequestResult,
  RemediationRun,
  VerificationRun,
  ValidationCheck,
  ApiError,
  ScanSummaryResponse,
} from "@/types/scan";
import type { LighthouseResponse } from "@/types/lighthouse";
import { getAuthHeaders } from "@/lib/authHeaders";

// Internal request body for createScan (mirrors backend ScanRequest schema)
interface CreateScanBody {
  url: string;
  max_pages?: number;
  personas?: string[];
  repo_url?: string | null;
}

const BASE = "/api/v1";

const SUMMARY_STATUSES = new Set(["none", "generating", "ready", "failed"]);

function isScanSummaryResponse(body: Record<string, unknown>): boolean {
  const status = body["status"];
  return typeof status === "string" && SUMMARY_STATUSES.has(status);
}

function parseSummaryErrorBody(
  body: Record<string, unknown>,
  status: number,
  fallbackMessage: string
): ApiError {
  if (isScanSummaryResponse(body)) {
    const summaryBody = body as unknown as ScanSummaryResponse;
    const message =
      typeof summaryBody.message === "string" && summaryBody.message.trim()
        ? summaryBody.message
        : fallbackMessage;
    return {
      status,
      message,
      body: summaryBody,
      retry_after: summaryBody.retry_after ?? null,
    };
  }
  let detail: string | undefined;
  let message = fallbackMessage;
  if (typeof body["detail"] === "string") {
    detail = body["detail"];
    message = detail;
  } else if (Array.isArray(body["detail"])) {
    detail = (body["detail"] as unknown[])
      .map((d) => JSON.stringify(d))
      .join("; ");
    message = detail;
  }
  return { status, message, detail };
}

async function request<T>(
  path: string,
  options?: RequestInit & { signal?: AbortSignal }
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
        ...(options?.headers ?? {}),
      },
    });
  } catch (networkErr) {
    const err: ApiError = {
      status: 0,
      message:
        networkErr instanceof Error
          ? networkErr.message
          : "Network request failed",
    };
    throw err;
  }

  if (!res.ok) {
    let detail: string | undefined;
    let message = `Request failed with status ${res.status}`;
    try {
      const body = (await res.json()) as Record<string, unknown>;
      if (typeof body["detail"] === "string") {
        detail = body["detail"];
        message = detail;
      } else if (Array.isArray(body["detail"])) {
        detail = (body["detail"] as unknown[])
          .map((d) => JSON.stringify(d))
          .join("; ");
        message = detail;
      }
    } catch {
      // non-JSON error body - keep default message
    }
    const err: ApiError = { status: res.status, message, detail };
    throw err;
  }

  try {
    return (await res.json()) as T;
  } catch {
    const err: ApiError = {
      status: res.status,
      message: "Invalid JSON in response",
    };
    throw err;
  }
}

export async function createScan(
  body: CreateScanBody,
  signal?: AbortSignal
): Promise<ScanResponse> {
  return request<ScanResponse>("/scans", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

export async function getScan(
  scanId: string,
  signal?: AbortSignal
): Promise<ScanResponse> {
  return request<ScanResponse>(`/scans/${scanId}`, { signal });
}

// Returns raw unknown[] because the shape is loose - normalize.ts handles it
export async function getIntents(
  scanId: string,
  signal?: AbortSignal
): Promise<unknown[]> {
  return request<unknown[]>(`/scans/${scanId}/intents`, { signal });
}

// Returns raw unknown[] because the shape is loose - normalize.ts handles it
export async function getContradictions(
  scanId: string,
  signal?: AbortSignal
): Promise<unknown[]> {
  return request<unknown[]>(`/scans/${scanId}/contradictions`, { signal });
}

export async function getPatches(
  scanId: string,
  repoUrlOrSignal?: string | null | AbortSignal,
  maybeSignal?: AbortSignal
): Promise<PatchProposal[]> {
  let repoUrl: string | null | undefined;
  let signal: AbortSignal | undefined;

  if (repoUrlOrSignal instanceof AbortSignal) {
    signal = repoUrlOrSignal;
    repoUrl = undefined;
  } else {
    repoUrl = repoUrlOrSignal;
    signal = maybeSignal;
  }

  const query = repoUrl ? `?repo_url=${encodeURIComponent(repoUrl)}` : "";
  return request<PatchProposal[]>(`/scans/${scanId}/patches${query}`, { signal });
}

export async function applyPatches(
  scanId: string,
  payload?: { repo_url?: string | null; target_branch?: string },
  signal?: AbortSignal
): Promise<PullRequestResult> {
  return request<PullRequestResult>(`/scans/${scanId}/patches/apply`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined,
    signal,
  });
}

export async function evaluateScan(
  scanId: string,
  personas?: string[],
  signal?: AbortSignal
): Promise<ScanResponse> {
  return request<ScanResponse>(`/scans/${scanId}/evaluate`, {
    method: "POST",
    body: personas ? JSON.stringify({ personas }) : undefined,
    signal,
  });
}

export async function remediateScan(
  scanId: string,
  signal?: AbortSignal
): Promise<PatchProposal[]> {
  return request<PatchProposal[]>(`/scans/${scanId}/remediate`, {
    method: "POST",
    signal,
  });
}

export async function validatePatches(
  scanId: string,
  signal?: AbortSignal
): Promise<{ eligible_for_validated_pr: boolean; checks: ValidationCheck[] }> {
  return request(`/scans/${scanId}/patches/validate`, {
    method: "POST",
    signal,
  });
}

export async function getRemediationRuns(
  scanId: string,
  signal?: AbortSignal
): Promise<RemediationRun[]> {
  return request<RemediationRun[]>(`/scans/${scanId}/remediation`, { signal });
}

export async function verifyRemediation(
  scanId: string,
  payload?: { remediation_run_id?: string; acceptance_keywords?: string[] },
  signal?: AbortSignal
): Promise<VerificationRun> {
  return request<VerificationRun>(`/scans/${scanId}/remediation/verify`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined,
    signal,
  });
}

export async function getVerifications(
  scanId: string,
  signal?: AbortSignal
): Promise<VerificationRun[]> {
  return request<VerificationRun[]>(`/scans/${scanId}/remediation/verifications`, {
    signal,
  });
}

export async function getLighthouse(
  scanId: string,
  signal?: AbortSignal
): Promise<LighthouseResponse> {
  return request<LighthouseResponse>(`/scans/${scanId}/lighthouse`, { signal });
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}

export async function getScanSummary(
  scanId: string,
  signal?: AbortSignal
): Promise<ScanSummaryResponse> {
  return request<ScanSummaryResponse>(`/scans/${scanId}/summary`, { signal });
}

export async function generateScanSummary(
  scanId: string,
  signal?: AbortSignal
): Promise<ScanSummaryResponse> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/scans/${scanId}/summary`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      signal,
    });
  } catch (networkErr) {
    const err: ApiError = {
      status: 0,
      message:
        networkErr instanceof Error
          ? networkErr.message
          : "Network request failed",
    };
    throw err;
  }

  let body: Record<string, unknown> = {};
  try {
    body = (await res.json()) as Record<string, unknown>;
  } catch {
    if (!res.ok) {
      throw parseSummaryErrorBody({}, res.status, `Request failed with status ${res.status}`);
    }
    const err: ApiError = {
      status: res.status,
      message: "Invalid JSON in response",
    };
    throw err;
  }

  if (res.ok) {
    return body as unknown as ScanSummaryResponse;
  }

  throw parseSummaryErrorBody(
    body,
    res.status,
    `Request failed with status ${res.status}`
  );
}