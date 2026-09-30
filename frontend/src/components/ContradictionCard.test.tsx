import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContradictionCard } from "@/components/ContradictionCard";
import type { Contradiction } from "@/types/scan";

// --- Fixtures ---

const CONTRADICTION: Contradiction = {
  contradiction_id: "con_abc",
  entity: "opening_hours",
  conflict: "Landing page says 10 PM, About page says 9 PM.",
  values: ["Open until 10 PM (Landing)", "Open until 9 PM (About)"],
  severity: "HARD_CONTRADICTION",
  source_urls: ["https://example.com/", "https://example.com/about"],
  dom_paths: ["body > .hours", "body > footer > p.hours"],
};

const SOFT_CONTRADICTION: Contradiction = {
  contradiction_id: "con_xyz",
  entity: "price",
  conflict: "Price discrepancy between pages.",
  values: ["$14 (Menu page)", "$15 (Checkout)"],
  severity: "SOFT_INCONSISTENCY",
  source_urls: [],
  dom_paths: ["body > section#menu > td.price"],
};

// --- navigator.clipboard mock ---

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    writable: true,
    configurable: true,
  });
});

afterEach(() => vi.restoreAllMocks());

// --- Empty state ---

describe("ContradictionCard - empty state", () => {
  it("renders empty state when no contradictions", () => {
    render(<ContradictionCard contradictions={[]} />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("No contradictions found")).toBeInTheDocument();
  });
});

// --- Single card rendering ---

describe("ContradictionCard - single card content", () => {
  it("renders entity name", () => {
    render(<ContradictionCard contradictions={[CONTRADICTION]} />);
    expect(screen.getByText("opening_hours")).toBeInTheDocument();
  });

  it("renders conflict description", () => {
    render(<ContradictionCard contradictions={[CONTRADICTION]} />);
    expect(screen.getByText(/Landing page says 10 PM/)).toBeInTheDocument();
  });

  it("renders severity badge for HARD_CONTRADICTION", () => {
    render(<ContradictionCard contradictions={[CONTRADICTION]} />);
    expect(screen.getByText("Hard Contradiction")).toBeInTheDocument();
  });

  it("renders severity badge for SOFT_INCONSISTENCY", () => {
    render(<ContradictionCard contradictions={[SOFT_CONTRADICTION]} />);
    expect(screen.getByText("Soft Inconsistency")).toBeInTheDocument();
  });

  it("renders both conflicting values", () => {
    render(<ContradictionCard contradictions={[CONTRADICTION]} />);
    expect(screen.getByText(/Open until 10 PM/)).toBeInTheDocument();
    expect(screen.getByText(/Open until 9 PM/)).toBeInTheDocument();
  });

  it("sets data-testid to contradiction-card-{id}", () => {
    render(<ContradictionCard contradictions={[CONTRADICTION]} />);
    expect(document.querySelector("[data-testid='contradiction-card-con_abc']")).toBeInTheDocument();
  });
});

// --- Multiple cards ---

describe("ContradictionCard - multiple contradictions", () => {
  it("renders one card per contradiction", () => {
    render(<ContradictionCard contradictions={[CONTRADICTION, SOFT_CONTRADICTION]} />);
    expect(document.querySelector("[data-testid='contradiction-card-con_abc']")).toBeInTheDocument();
    expect(document.querySelector("[data-testid='contradiction-card-con_xyz']")).toBeInTheDocument();
  });
});

// --- DOM path copy button ---

describe("ContradictionCard - copy DOM path", () => {
  it("copy button copies the first dom_path", async () => {
    render(<ContradictionCard contradictions={[CONTRADICTION]} />);
    const copyButtons = screen.getAllByRole("button", { name: /Copy/i });
    expect(copyButtons.length).toBeGreaterThan(0);
    await userEvent.click(copyButtons[0]!);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining("body >")
    );
  });
});