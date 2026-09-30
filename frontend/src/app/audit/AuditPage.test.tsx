import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AuditPage from "./page";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

describe("AuditPage", () => {
  it("renders the audit console with title, input, and persona selectors", () => {
    render(<AuditPage />);

    expect(screen.getByRole("heading", { name: "Initialize your machine audit" })).toBeDefined();
    expect(screen.getByTestId("scan-url-input")).toBeDefined();
    expect(screen.getByTestId("scan-submit")).toBeDefined();
    expect(screen.getByText("Skeptical CTO")).toBeDefined();
    expect(screen.getByText("Developer Evaluator")).toBeDefined();
    expect(screen.getByText("Procurement Officer")).toBeDefined();
  });

  it("shows an error when submitted with an empty or invalid URL", async () => {
    render(<AuditPage />);

    const submitBtn = screen.getByTestId("scan-submit");
    fireEvent.click(submitBtn);

    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText("Please enter a website URL.")).toBeDefined();
  });

  it("allows toggling intent personas", () => {
    render(<AuditPage />);

    const ctoBtn = screen.getByRole("button", { name: /Skeptical CTO/i });
    fireEvent.click(ctoBtn);

    // Persona count drops to 2 active
    expect(screen.getByText("2 of 3 active")).toBeDefined();
  });
});
