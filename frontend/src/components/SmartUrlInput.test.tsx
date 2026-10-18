import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import SmartUrlInput from "./SmartUrlInput";
import { URL_HISTORY_KEY, pushUrlHistory } from "@/lib/urlHistory";

describe("SmartUrlInput", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => store.clear(),
    });
  });

  it("emits https://example.com by default when domain and .com are set", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "example" },
    });

    expect(onChange).toHaveBeenCalled();
    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last).toBe("https://example.com");
    expect(screen.getByTestId("url-preview").textContent).toContain("https://example.com");
  });

  it("switches protocol to http", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "example" },
    });
    fireEvent.click(screen.getByTestId("url-protocol-select"));
    fireEvent.click(screen.getByTestId("url-protocol-select-option-http"));

    expect(onChange.mock.calls.at(-1)?.[0]).toBe("http://example.com");
  });

  it("composes selected TLD", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByTestId("url-tld-select"));
    fireEvent.click(screen.getByTestId("url-tld-select-option-io"));

    expect(onChange.mock.calls.at(-1)?.[0]).toBe("https://acme.io");
  });

  it("does not force TLD onto a domain that already has one", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "example.org" },
    });
    fireEvent.click(screen.getByTestId("url-tld-select"));
    fireEvent.click(screen.getByTestId("url-tld-select-option-com"));

    expect(onChange.mock.calls.at(-1)?.[0]).toBe("https://example.org");
  });

  it("absorbs a pasted full URL in builder mode", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "https://shop.example.com/cart?x=1" },
    });

    expect(onChange.mock.calls.at(-1)?.[0]).toBe("https://shop.example.com/cart?x=1");
  });

  it("custom mode preserves ports, paths, and query strings", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.click(screen.getByTestId("url-mode-custom"));
    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "http://example.com:8443/api?q=1#frag" },
    });

    expect(onChange.mock.calls.at(-1)?.[0]).toBe(
      "http://example.com:8443/api?q=1#frag"
    );
  });

  it("preserves composed URL when switching builder → custom → builder", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "example" },
    });
    fireEvent.click(screen.getByTestId("url-mode-custom"));
    expect(screen.getByTestId("scan-url-input")).toHaveProperty(
      "value",
      "https://example.com"
    );
    fireEvent.click(screen.getByTestId("url-mode-builder"));
    expect(screen.getByTestId("url-preview").textContent).toContain("https://example.com");
  });

  it("shows custom TLD field when Other is selected", () => {
    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.click(screen.getByTestId("url-tld-select"));
    fireEvent.click(screen.getByTestId("url-tld-select-option-other"));
    expect(screen.getByTestId("url-custom-tld")).toBeDefined();
    fireEvent.change(screen.getByTestId("scan-url-input"), {
      target: { value: "mysite" },
    });
    fireEvent.change(screen.getByTestId("url-custom-tld"), {
      target: { value: ".app" },
    });
    expect(onChange.mock.calls.at(-1)?.[0]).toBe("https://mysite.app");
  });

  it("shows up to 3 local history items on focus and applies on click", () => {
    pushUrlHistory("https://one.com");
    pushUrlHistory("https://two.com");
    pushUrlHistory("https://three.com");
    pushUrlHistory("https://four.com");

    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.focus(screen.getByTestId("scan-url-input"));
    const items = screen.getAllByTestId("url-history-item");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toBe("https://four.com");

    fireEvent.click(items[1]);
    expect(onChange.mock.calls.at(-1)?.[0]).toBe("https://three.com");
    expect(screen.queryByTestId("url-history-panel")).toBeNull();
  });

  it("deletes a history item and can clear all", () => {
    pushUrlHistory("https://keep.com");
    pushUrlHistory("https://drop.com");

    const onChange = vi.fn();
    render(<SmartUrlInput value="" onChange={onChange} />);

    fireEvent.focus(screen.getByTestId("scan-url-input"));
    const deletes = screen.getAllByTestId("url-history-delete");
    fireEvent.click(deletes[0]);
    expect(screen.getAllByTestId("url-history-item")).toHaveLength(1);
    expect(screen.getByTestId("url-history-item").textContent).toBe(
      "https://keep.com"
    );

    fireEvent.click(screen.getByTestId("url-history-clear"));
    expect(screen.queryByTestId("url-history-panel")).toBeNull();
    expect(localStorage.getItem(URL_HISTORY_KEY)).toBe("[]");
  });
});
