import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PatchModal } from "@/components/PatchModal";
import type { PatchProposal } from "@/types/scan";

// --- Mock the api module (applyPatches is imported directly in PatchModal.tsx)---

vi.mock("@/lib/api", () => ({
  applyPatches: vi.fn(),
  getPatches: vi.fn().mockResolvedValue([]),
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

function renderModal(patches = [PATCH_A, PATCH_B], repoUrl: string | null = "https://github.com/org/repo") {
  return render(
    <PatchModal
      scanId="scan_test"
      patches={patches}
      currentScore={78.4}
      repoUrl={repoUrl}
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

describe("PatchModal - repository connection gating", () => {
  it("disables Create PR button and shows warning when repoUrl is not configured", () => {
    renderModal([PATCH_A], null);
    const btn = screen.getByTestId("create-pr-button");
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("no-repo-warning")).toBeInTheDocument();
    expect(screen.getByText(/No GitHub repository connected for this scan/i)).toBeInTheDocument();
  });

  it("enables Create PR button when repoUrl is provided", () => {
    renderModal([PATCH_A], "https://github.com/example/my-repo");
    const btn = screen.getByTestId("create-pr-button");
    expect(btn).not.toBeDisabled();
    expect(screen.queryByTestId("no-repo-warning")).not.toBeInTheDocument();
    expect(screen.getByText(/example\/my-repo/)).toBeInTheDocument();
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

describe("PatchModal - Framework-Native tabs and Dual Perspective", () => {
  const FRAMEWORK_PATCH: PatchProposal = {
    patch_id: "patch_fw_001",
    patch_type: "schema_microdata",
    title: "Inject Next.js JsonLd Component",
    rationale: "Synthesizes framework-native TypeScript React component.",
    impact_score_delta: 9.0,
    target_file: "frontend/src/app/layout.tsx",
    code_diff: "--- a/frontend/src/app/layout.tsx\n+++ b/frontend/src/app/layout.tsx\n@@ -1,3 +1,4 @@\n+import { JsonLd } from '@/components/JsonLd';\n <html lang=\"en\">",
    auxiliary_files: [
      {
        file_path: "frontend/src/components/JsonLd.tsx",
        content: "export function JsonLd() {\n  return <script type=\"application/ld+json\" />;\n}",
        action: "create",
      },
    ],
    framework: "nextjs_app_router",
    dom_anchor: {
      css_selector: "head",
      tag_name: "head",
      original_snippet: "<head>",
      suggested_snippet: "<head><script>...</script>",
    },
    unified_diff: "--- a/index.html\n+++ b/index.html\n@@ -1,3 +1,4 @@\n <head>\n+<script>{}</script>\n </head>",
    applied: false,
  };

  it("renders target_file tab, auxiliary file tab, and framework badge", () => {
    renderModal([FRAMEWORK_PATCH]);
    expect(screen.getByText("layout.tsx")).toBeInTheDocument();
    expect(screen.getByText("JsonLd.tsx")).toBeInTheDocument();
    expect(screen.getByText(/Next.js App Router/i)).toBeInTheDocument();
  });

  it("switches to auxiliary file content when clicked", async () => {
    renderModal([FRAMEWORK_PATCH]);
    const auxTab = screen.getByTestId("tab-frontend/src/components/JsonLd.tsx");
    await userEvent.click(auxTab);
    expect(screen.getByText("+ NEW COMPONENT")).toBeInTheDocument();
    expect(screen.getByText(/export function JsonLd/i)).toBeInTheDocument();
  });

  it("displays strictly real PR files and no simulated HTML diffs", () => {
    renderModal([FRAMEWORK_PATCH]);
    expect(screen.getByText("1:1 GitHub PR Parity")).toBeInTheDocument();
    expect(screen.getByText("layout.tsx")).toBeInTheDocument();
    expect(screen.getByText("JsonLd.tsx")).toBeInTheDocument();

    // Must NOT render simulated index.html diff
    expect(screen.queryByText(/index.html/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/<!DOCTYPE html>/i)).not.toBeInTheDocument();
  });

  it("renders secondary framework patch in bundled remediations list with no raw diff", () => {
    const secondaryPatch: PatchProposal = {
      ...FRAMEWORK_PATCH,
      patch_id: "patch_fw_002",
      title: "Inject Schema.org FAQPage JSON-LD",
      target_file: undefined,
      code_diff: undefined,
      auxiliary_files: [],
      framework: undefined,
    };

    renderModal([FRAMEWORK_PATCH, secondaryPatch]);
    expect(screen.getByText(/Remediations Bundled in this PR/i)).toBeInTheDocument();
    expect(screen.getByText("Inject Schema.org FAQPage JSON-LD")).toBeInTheDocument();
    expect(screen.queryByText(/<!DOCTYPE html>/i)).not.toBeInTheDocument();
  });
});