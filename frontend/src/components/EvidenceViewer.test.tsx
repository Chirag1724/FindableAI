import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvidenceViewer } from "@/components/EvidenceViewer";
import { useRef } from "react";
import type { EvidenceReference } from "@/types/scan";

// --- Fixtures ---

const EVIDENCE: EvidenceReference = {
  chunk_id: "chunk_001",
  dom_path: "body > main > section#menu > p.item",
  url: "https://example.com",
  rank: 1,
  rrf_score: 0.9142,
  excerpt: "Open daily 5 PM to 10 PM",
};

const EVIDENCE_NO_EXTRAS: EvidenceReference = {
  chunk_id: "chunk_002",
  dom_path: "body > footer > p.hours",
};

// --- Clipboard mock ---

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// --- Wrapper that provides a real triggerRef ---

function Wrapper({ evidence, onClose }: { evidence: EvidenceReference; onClose: () => void }) {
  const triggerRef = useRef<HTMLElement>(null);
  return (
    <>
      <button ref={triggerRef as React.RefObject<HTMLButtonElement>} aria-label="trigger" />
      <EvidenceViewer evidence={evidence} onClose={onClose} triggerRef={triggerRef as React.RefObject<HTMLElement>} />
    </>
  );
}

// --- Tests ---

describe("EvidenceViewer - renders content", () => {
  it("renders 'Evidence Reference' heading", () => {
    const onClose = vi.fn();
    render(<Wrapper evidence={EVIDENCE} onClose={onClose} />);
    expect(screen.getByText("Evidence Reference")).toBeInTheDocument();
  });

  it("renders DOM path", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByText(EVIDENCE.dom_path)).toBeInTheDocument();
  });

  it("renders excerpt when present", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByText("Open daily 5 PM to 10 PM")).toBeInTheDocument();
  });

  it("renders source URL link when present", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByRole("link", { name: "https://example.com" })).toBeInTheDocument();
  });

  it("renders rank when present", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByText("#1")).toBeInTheDocument();
  });

  it("renders RRF score when present", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByText("0.9142")).toBeInTheDocument();
  });

  it("does not render excerpt section when absent", () => {
    render(<Wrapper evidence={EVIDENCE_NO_EXTRAS} onClose={vi.fn()} />);
    expect(screen.queryByText("Excerpt")).not.toBeInTheDocument();
  });
});

describe("EvidenceViewer - closing behaviour", () => {
  it("calls onClose when X button is clicked", async () => {
    const onClose = vi.fn();
    render(<Wrapper evidence={EVIDENCE} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: /Close evidence viewer/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when Escape key is pressed", async () => {
    const onClose = vi.fn();
    render(<Wrapper evidence={EVIDENCE} onClose={onClose} />);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when backdrop (outer div) is clicked", async () => {
    const onClose = vi.fn();
    const { container } = render(<Wrapper evidence={EVIDENCE} onClose={onClose} />);
    // The backdrop is the outermost fixed div (first child after trigger button)
    const backdrop = container.querySelector(".fixed.inset-0") as HTMLElement;
    expect(backdrop).toBeInTheDocument();
    await userEvent.pointer({ keys: "[MouseLeft]", target: backdrop });
    // backdrop click is only fired when target === currentTarget; simulate with click on the element itself
    backdrop.click();
    expect(onClose).toHaveBeenCalled();
  });
});

describe("EvidenceViewer - focus management", () => {
  it("renders close button with correct aria-label", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Close evidence viewer/i })).toBeInTheDocument();
  });

  it("renders dialog with role=dialog", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("dialog is aria-modal=true", () => {
    render(<Wrapper evidence={EVIDENCE} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });
});