import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CopyButton } from "@/components/CopyButton";

// --- navigator.clipboard mock ---

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

describe("CopyButton - with clipboard API", () => {
  it("renders a Copy button by default", () => {
    render(<CopyButton text="hello" />);
    expect(screen.getByRole("button")).toBeInTheDocument();
    expect(screen.getByText("Copy")).toBeInTheDocument();
  });

  it("calls navigator.clipboard.writeText with the correct text on click", async () => {
    render(<CopyButton text="selector > p" />);
    await userEvent.click(screen.getByRole("button"));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("selector > p");
  });

  it("shows 'Copied' text after click", async () => {
    render(<CopyButton text="test" />);
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Copied")).toBeInTheDocument();
  });

  it("uses custom label prop", () => {
    render(<CopyButton text="x" label="Copy path" />);
    expect(screen.getByText("Copy path")).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-label", "Copy path");
  });

  it("does not copy a second time while already in 'copied' state", async () => {
    render(<CopyButton text="test" />);
    await userEvent.click(screen.getByRole("button"));
    await userEvent.click(screen.getByRole("button"));
    // writeText should still be called only once
    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
  });
});

describe("CopyButton - clipboard API unavailable (fallback)", () => {
  beforeEach(() => {
    // Remove clipboard API to test execCommand fallback
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      writable: true,
      configurable: true,
    });
    // jsdom does not implement execCommand - define it so vi.spyOn works
    if (!document.execCommand) {
      Object.defineProperty(document, "execCommand", {
        value: () => true,
        writable: true,
        configurable: true,
      });
    }
    vi.spyOn(document, "execCommand").mockReturnValue(true);
  });

  it("falls back to execCommand and shows 'Copied'", async () => {
    render(<CopyButton text="fallback text" />);
    await userEvent.click(screen.getByRole("button"));
    expect(document.execCommand).toHaveBeenCalledWith("copy");
    expect(screen.getByText("Copied")).toBeInTheDocument();
  });
});