import type {
  ScanResponse, PatchProposal, PullRequestResult, ApiError,
} from "@/types/scan";

// Internal request body for createScan (mirrors backend ScanRequest schema)
interface CreateScanBody {
  url: string;
  max_pages?: number;
  personas?: string[];
  repo_url?: string | null;
}

const BASE = "/api/v1";

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
  signal?: AbortSignal
): Promise<PatchProposal[]> {
  return request<PatchProposal[]>(`/scans/${scanId}/patches`, { signal });
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

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}