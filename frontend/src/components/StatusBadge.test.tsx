import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "@/components/StatusBadge";

describe("StatusBadge - EntailmentStatus", () => {
  it("renders 'Supported' for SUPPORTED", () => {
    render(<StatusBadge status="SUPPORTED" />);
    expect(screen.getByText("Supported")).toBeInTheDocument();
  });

  it("renders 'Partial' for PARTIALLY_SUPPORTED", () => {
    render(<StatusBadge status="PARTIALLY_SUPPORTED" />);
    expect(screen.getByText("Partial")).toBeInTheDocument();
  });

  it("renders 'Contradicted' for CONTRADICTED", () => {
    render(<StatusBadge status="CONTRADICTED" />);
    expect(screen.getByText("Contradicted")).toBeInTheDocument();
  });

  it("renders 'Unknown' for UNKNOWN", () => {
    render(<StatusBadge status="UNKNOWN" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});

describe("StatusBadge - ContradictionSeverity", () => {
  it("renders 'Hard Contradiction' for HARD_CONTRADICTION", () => {
    render(<StatusBadge status="HARD_CONTRADICTION" />);
    expect(screen.getByText("Hard Contradiction")).toBeInTheDocument();
  });

  it("renders 'Soft Inconsistency' for SOFT_INCONSISTENCY", () => {
    render(<StatusBadge status="SOFT_INCONSISTENCY" />);
    expect(screen.getByText("Soft Inconsistency")).toBeInTheDocument();
  });
});

describe("StatusBadge - ring classes", () => {
  it("SUPPORTED badge has emerald ring class", () => {
    const { container } = render(<StatusBadge status="SUPPORTED" />);
    expect(container.firstChild).toHaveClass("ring-emerald-800");
  });

  it("CONTRADICTED badge has rose ring class", () => {
    const { container } = render(<StatusBadge status="CONTRADICTED" />);
    expect(container.firstChild).toHaveClass("ring-rose-800");
  });

  it("PARTIALLY_SUPPORTED badge has sky ring class", () => {
    const { container } = render(<StatusBadge status="PARTIALLY_SUPPORTED" />);
    expect(container.firstChild).toHaveClass("ring-sky-800");
  });

  it("UNKNOWN badge has amber ring class", () => {
    const { container } = render(<StatusBadge status="UNKNOWN" />);
    expect(container.firstChild).toHaveClass("ring-amber-800");
  });

  it("HARD_CONTRADICTION badge has rose ring class", () => {
    const { container } = render(<StatusBadge status="HARD_CONTRADICTION" />);
    expect(container.firstChild).toHaveClass("ring-rose-800");
  });

  it("SOFT_INCONSISTENCY badge has amber ring class", () => {
    const { container } = render(<StatusBadge status="SOFT_INCONSISTENCY" />);
    expect(container.firstChild).toHaveClass("ring-amber-800");
  });
});

describe("StatusBadge - ScrapingRisk", () => {
  it("renders 'Low Scraping Risk' for low", () => {
    render(<StatusBadge status="low" />);
    expect(screen.getByText("Low Scraping Risk")).toBeInTheDocument();
  });

  it("renders 'Moderate Scraping Risk' for moderate", () => {
    render(<StatusBadge status="moderate" />);
    expect(screen.getByText("Moderate Scraping Risk")).toBeInTheDocument();
  });

  it("renders 'Critical Scraping Risk' for critical", () => {
    render(<StatusBadge status="critical" />);
    expect(screen.getByText("Critical Scraping Risk")).toBeInTheDocument();
  });
});

describe("StatusBadge - className prop", () => {
  it("applies extra className", () => {
    const { container } = render(<StatusBadge status="SUPPORTED" className="ml-2" />);
    expect(container.firstChild).toHaveClass("ml-2");
  });
});