import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AuditChecklist } from "@/components/AuditChecklist";
import type { AuditSummary } from "@/types/lighthouse";

const MOCK_AUDITS: AuditSummary = {
  opportunities: [
    {
      id: "unblock-perplexity",
      title: "Unblock PerplexityBot in robots.txt",
      score_lift: 18,
      engine: "perplexity",
      severity: "critical",
    },
    {
      id: "add-product-schema",
      title: "Add Product Schema.org JSON-LD",
      score_lift: 14,
      engine: "chatgpt",
      severity: "high",
    },
  ],
  diagnostics: [
    {
      id: "heading-skip",
      title: "Heading hierarchy skips h2 level",
      engines_affected: ["gemini", "chatgpt"],
    },
  ],
  passed: [
    {
      id: "https-active",
      title: "HTTPS / SSL active and valid",
    },
  ],
};

describe("AuditChecklist", () => {
  it("renders all three audit sections with their item counts", () => {
    render(<AuditChecklist audits={MOCK_AUDITS} />);

    expect(screen.getByText("Opportunities (2)")).toBeInTheDocument();
    expect(screen.getByText("Diagnostics (1)")).toBeInTheDocument();
    expect(screen.getByText("Passed Audits (1)")).toBeInTheDocument();
  });

  it("renders opportunity details, engine badges, and score lift badges", () => {
    render(<AuditChecklist audits={MOCK_AUDITS} />);

    expect(screen.getByText("Unblock PerplexityBot in robots.txt")).toBeInTheDocument();
    expect(screen.getByText("+18 pts")).toBeInTheDocument();
    expect(screen.getByText("Perplexity")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();

    expect(screen.getByText("Add Product Schema.org JSON-LD")).toBeInTheDocument();
    expect(screen.getByText("+14 pts")).toBeInTheDocument();
  });

  it("renders diagnostics and affected engine tags", () => {
    render(<AuditChecklist audits={MOCK_AUDITS} />);

    expect(screen.getByText("Heading hierarchy skips h2 level")).toBeInTheDocument();
    expect(screen.getByText("Gemini")).toBeInTheDocument();
  });

  it("allows expanding and collapsing the Passed Audits section", () => {
    render(<AuditChecklist audits={MOCK_AUDITS} />);

    // Passed audits is collapsed by default
    expect(screen.queryByText("HTTPS / SSL active and valid")).not.toBeInTheDocument();

    // Click to expand
    const passedBtn = screen.getByRole("button", { name: /passed audits/i });
    fireEvent.click(passedBtn);

    expect(screen.getByText("HTTPS / SSL active and valid")).toBeInTheDocument();

    // Click to collapse
    fireEvent.click(passedBtn);
    expect(screen.queryByText("HTTPS / SSL active and valid")).not.toBeInTheDocument();
  });

  it("renders empty state messages when arrays are empty", () => {
    const emptyAudits: AuditSummary = {
      opportunities: [],
      diagnostics: [],
      passed: [],
    };

    render(<AuditChecklist audits={emptyAudits} />);

    expect(
      screen.getByText(/no critical opportunities detected/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/zero diagnostic warnings/i)
    ).toBeInTheDocument();
  });
});
