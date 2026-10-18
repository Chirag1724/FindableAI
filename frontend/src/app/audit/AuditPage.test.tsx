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

  it("updates crawl scope via preset buttons and stepper controls", () => {
    render(<AuditPage />);

    // Default is 5 pages
    expect(screen.getByTestId("max-pages-count").textContent).toContain("5 pages");

    // Click 1 Page preset
    const preset1 = screen.getByTestId("preset-pages-1");
    fireEvent.click(preset1);
    expect(screen.getByTestId("max-pages-count").textContent).toContain("1 page");

    // Increase via stepper (+)
    const plusBtn = screen.getByRole("button", { name: "Increase crawl pages" });
    fireEvent.click(plusBtn);
    expect(screen.getByTestId("max-pages-count").textContent).toContain("2 pages");

    // Click 25 Pages preset
    const preset25 = screen.getByTestId("preset-pages-25");
    fireEvent.click(preset25);
    expect(screen.getByTestId("max-pages-count").textContent).toContain("25 pages");

    // Decrease via stepper (-)
    const minusBtn = screen.getByRole("button", { name: "Decrease crawl pages" });
    fireEvent.click(minusBtn);
    expect(screen.getByTestId("max-pages-count").textContent).toContain("24 pages");
  });

  it("populates target URL and GitHub repository when clicking FindableAI quick test", () => {
    render(<AuditPage />);

    const findableBtn = screen.getByTestId("demo-fill-btn");
    fireEvent.click(findableBtn);

    const preview = screen.getByTestId("url-preview");
    const repoInput = screen.getByLabelText(/GitHub Repository/i) as HTMLInputElement;

    expect(preview.textContent).toContain("https://findableai.vercel.app");
    expect(repoInput.value).toBe("https://github.com/Chirag1724/FindableAI");
  });

  it("builds a canonical https URL from domain + default TLD without typing the protocol", () => {
    render(<AuditPage />);

    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "example" },
    });
    expect(screen.getByTestId("url-preview").textContent).toContain("https://example.com");
  });
});
