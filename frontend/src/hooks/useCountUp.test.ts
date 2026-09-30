import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, render } from "@testing-library/react";
import React from "react";
import { useCountUp } from "@/hooks/useCountUp";

// --- IntersectionObserver mock ---

const disconnectMock = vi.fn();
const observeMock = vi.fn();

beforeEach(() => {
  disconnectMock.mockClear();
  observeMock.mockClear();

  vi.stubGlobal(
    "IntersectionObserver",
    vi.fn().mockImplementation(() => ({
      observe: observeMock,
      disconnect: disconnectMock,
    }))
  );

  // Default: reduced motion OFF
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

// --- Component wrapper so the ref attaches to a real DOM element ---

function CountUpSpan({ target, decimals }: { target: number; decimals?: number }) {
  const { value, ref } = useCountUp(target, decimals);
  return React.createElement("span", { ref }, value);
}

// --- prefers-reduced-motion ON - effect sets value to target immediately ---

describe("useCountUp - prefers-reduced-motion ON", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })
    );
  });

  it("sets value to target after effect fires", async () => {
    const { getByText } = render(React.createElement(CountUpSpan, { target: 78.4, decimals: 1 }));
    await waitFor(() => expect(getByText("78.4")).toBeInTheDocument());
  });

  it("returns integer string for decimals=0", async () => {
    const { getByText } = render(React.createElement(CountUpSpan, { target: 42, decimals: 0 }));
    await waitFor(() => expect(getByText("42")).toBeInTheDocument());
  });
});

// --- Normal path (reduced motion OFF) ---

describe("useCountUp - normal path", () => {
  it("starts at '0' before IntersectionObserver fires", () => {
    const { result } = renderHook(() => useCountUp(100));
    expect(result.current.value).toBe("0");
  });

  it("returns a ref object", () => {
    const { result } = renderHook(() => useCountUp(50));
    expect(result.current.ref).toBeDefined();
    expect(typeof result.current.ref).toBe("object");
  });

  it("creates an IntersectionObserver when a real element is rendered", () => {
    render(React.createElement(CountUpSpan, { target: 50 }));
    expect(IntersectionObserver).toHaveBeenCalled();
    expect(observeMock).toHaveBeenCalled();
  });
});

// --- Cleanup ---

describe("useCountUp - cleanup", () => {
  it("does not throw on unmount (no DOM element)", () => {
    const { unmount } = renderHook(() => useCountUp(50));
    expect(() => unmount()).not.toThrow();
  });

  it("calls observer.disconnect() on unmount when a real element is attached", () => {
    const { unmount } = render(React.createElement(CountUpSpan, { target: 50 }));
    unmount();
    expect(disconnectMock).toHaveBeenCalled();
  });
});