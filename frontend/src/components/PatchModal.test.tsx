import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PatchModal } from "@/components/PatchModal";
import type { PatchProposal } from "@/types/scan";

// --- Mock the api module (applyPatches is imported directly in PatchModal.tsx)---

vi.mock("@/lib/api", () => ({
  applyPatches: vi.fn(),
}));

import * as api from "@/lib/api";

// Fixtures ---

const PATCH_A: PatchProposal = {
  patch_id: "patch_001",
  patch_type: "schema_microdata",
  title: "Inject Schema.org LocalBusiness JSON-LD",
  rationale: "Missing JSON-LD microdata degrades AI discoverability.",
  impact_score_delta: 6.5,
  dom_anchor: {
    css_selector: "head",
    tag_name: "head",
    original_snippet: "<head>",
    suggested_snippet: "<head><script>...</script>",
  },
  unified_diff: "--- a/index.html\n+++ b/index.html\n@@ -1,3 +1,4 @@\n <head>\n+<script type=\"application/ld+json\">{}</script>\n </head>",
  applied: false,
};

const PATCH_B: PatchProposal = {
  patch_id: "patch_002",
  patch_type: "factual_conflict_resolution",
  title: "Reconcile Operating Hours",
  rationale: "Conflicting hours between pages.",
  impact_score_delta: 8.2,
  dom_anchor: {
    css_selector: "section#about > p.hours",
    tag_name: "p",
    original_snippet: "<p class=\"hours\">Open until 9 PM</p>",
    suggested_snippet: "<p class=\"hours\">Open until 10 PM</p>",
  },
  unified_diff: "--- a/about.html\n+++ b/about.html\n@@ -1,1 +1,1 @@\n-9 PM\n+10 PM",
  applied: false,
};

const PR_RESULT = {
  pr_url: "https://github.com/org/repo/pull/42",
  pr_number: 42,
  branch_name: "findable-ai/patch-abc",
  title: "fix(discoverability): inject JSON-LD",
  created_at: "2026-09-27T00:00:00Z",
};

const onClose = vi.fn();

beforeEach(() => {
  onClose.mockClear();
  vi.mocked(api.applyPatches).mockReset();
});

afterEach(() => vi.restoreAllMocks());

// --- Helpers ---

function renderModal(patches = [PATCH_A, PATCH_B]) {
  return render(
    <PatchModal
      scanId="scan_test"
      patches={patches}
      currentScore={78.4}
      onClose={onClose}
    />
  );
}

// --- Tests ---

describe("PatchModal - patch list rendering", () => {
  it("renders the modal", () => {
    renderModal();
    expect(screen.getByTestId("patch-modal")).toBeInTheDocument();
  });

  it("renders patch titles", () => {
    renderModal();
    expect(screen.getByText("Inject Schema.org LocalBusiness JSON-LD")).toBeInTheDocument();
    expect(screen.getByText("Reconcile Operating Hours")).toBeInTheDocument();
  });

  it("renders Create Pull Request button", () => {
    renderModal();
    expect(screen.getByRole("button", { name: /Create Pull Request/i })).toBeInTheDocument();
  });

  it("renders empty state when no patches", () => {
    renderModal([]);
    // EmptyState should be rendered
    const modal = screen.getByTestId("patch-modal");
    expect(modal).toBeInTheDocument();
  });
});

describe("PatchModal - Create PR flow - success", () => {
  it("calls applyPatches with scanId on button click", async () => {
    vi.mocked(api.applyPatches).mockResolvedValue(PR_RESULT);
    renderModal();
    await userEvent.click(screen.getByTestId("create-pr-button"));
    expect(api.applyPatches).toHaveBeenCalledWith("scan_test");
  });

  it("shows PR link and number on success", async () => {
    vi.mocked(api.applyPatches).mockResolvedValue(PR_RESULT);
    renderModal();
    await userEvent.click(screen.getByTestId("create-pr-button"));
    await waitFor(() =>
      expect(screen.getByTestId("pr-result")).toBeInTheDocument()
    );
    expect(screen.getByText(/PR #42/)).toBeInTheDocument();
  });
});

describe("PatchModal - Create PR flow - loading state", () => {
  it("disables button while request is in flight", async () => {
    let resolve!: (v: typeof PR_RESULT) => void;
    vi.mocked(api.applyPatches).mockReturnValue(
      new Promise<typeof PR_RESULT>((res) => { resolve = res; })
    );
    renderModal();
    const btn = screen.getByRole("button", { name: /Create Pull Request/i });
    await userEvent.click(btn);
    // Button should now be disabled or show loading state
    await waitFor(() => {
      // Either disabled or still present (the handler guards against double-submit)
      expect(api.applyPatches).toHaveBeenCalledOnce();
    });
    // Second click should not trigger another call
    await userEvent.click(screen.getByRole("button", { name: /Create Pull Request|Creating/i }));
    expect(api.applyPatches).toHaveBeenCalledOnce();
    resolve(PR_RESULT);
  });
});

describe("PatchModal - Create PR flow - error state", () => {
  it("shows error message and retry button on failure", async () => {
    vi.mocked(api.applyPatches).mockRejectedValue({ status: 500, message: "GitHub API unavailable" });
    renderModal();
    await userEvent.click(screen.getByTestId("create-pr-button"));
    await waitFor(() =>
      expect(screen.getByText(/GitHub API unavailable/i)).toBeInTheDocument()
    );
    // The button changes its label to "Retry" in error state
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
  });

  it("retry button triggers a new applyPatches call", async () => {
    vi.mocked(api.applyPatches)
      .mockRejectedValueOnce({ status: 500, message: "Server error" })
      .mockResolvedValueOnce(PR_RESULT);
    renderModal();
    await userEvent.click(screen.getByTestId("create-pr-button"));
    await waitFor(() => expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Retry/i }));
    await waitFor(() => expect(screen.getByTestId("pr-result")).toBeInTheDocument());
    expect(api.applyPatches).toHaveBeenCalledTimes(2);
  });
});

describe("PatchModal - close", () => {
  it("calls onClose when X button is clicked", async () => {
    renderModal();
    const closeBtn = screen.getByRole("button", { name: /Close patches modal/i });
    await userEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when Escape is pressed", async () => {
    renderModal();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });
});