import { describe, it, expect } from "vitest";
import {
  composeFromBuilder,
  hostnameHasTld,
  ingestDomainPaste,
  parseIntoBuilder,
  partsFromCanonical,
  switchMode,
  validateScanUrl,
  DEFAULT_BUILDER,
} from "./smartUrl";

describe("hostnameHasTld", () => {
  it("detects common TLDs", () => {
    expect(hostnameHasTld("example.com")).toBe(true);
    expect(hostnameHasTld("www.example.in")).toBe(true);
    expect(hostnameHasTld("findableai.vercel.app")).toBe(true);
  });

  it("does not treat bare or partial hosts as having a TLD", () => {
    expect(hostnameHasTld("example")).toBe(false);
    expect(hostnameHasTld("www.example")).toBe(false);
  });
});

describe("composeFromBuilder", () => {
  it("defaults to https and appends selected TLD", () => {
    expect(
      composeFromBuilder({ ...DEFAULT_BUILDER, domain: "example", tld: ".com" })
    ).toBe("https://example.com");
  });

  it("uses http when selected", () => {
    expect(
      composeFromBuilder({
        ...DEFAULT_BUILDER,
        protocol: "http",
        domain: "example",
        tld: ".org",
      })
    ).toBe("http://example.org");
  });

  it("appends TLD to www.example", () => {
    expect(
      composeFromBuilder({ ...DEFAULT_BUILDER, domain: "www.example", tld: ".com" })
    ).toBe("https://www.example.com");
  });

  it("does not duplicate an existing TLD", () => {
    expect(
      composeFromBuilder({ ...DEFAULT_BUILDER, domain: "example.com", tld: ".io" })
    ).toBe("https://example.com");
  });

  it("composes .vercel.app from the selector", () => {
    expect(
      composeFromBuilder({
        ...DEFAULT_BUILDER,
        domain: "findableai",
        tld: ".vercel.app",
      })
    ).toBe("https://findableai.vercel.app");
  });

  it("preserves path, port, and query from the domain field", () => {
    expect(
      composeFromBuilder({
        ...DEFAULT_BUILDER,
        domain: "example.com:8443/path?q=1#top",
        tld: ".net",
      })
    ).toBe("https://example.com:8443/path?q=1#top");
  });

  it("appends TLD before port when host has no TLD yet", () => {
    expect(
      composeFromBuilder({
        ...DEFAULT_BUILDER,
        domain: "example:8080/health",
        tld: ".com",
      })
    ).toBe("https://example.com:8080/health");
  });

  it("supports Other / Custom TLD", () => {
    expect(
      composeFromBuilder({
        ...DEFAULT_BUILDER,
        domain: "mysite",
        tld: "other",
        customTld: "xyz",
      })
    ).toBe("https://mysite.xyz");
  });

  it("strips a pasted scheme from the domain field without duplicating", () => {
    expect(
      composeFromBuilder({
        ...DEFAULT_BUILDER,
        protocol: "https",
        domain: "http://example.com/docs",
        tld: ".com",
      })
    ).toBe("https://example.com/docs");
  });
});

describe("validateScanUrl", () => {
  it("accepts default https URLs", () => {
    expect(validateScanUrl("https://example.com")).toBeNull();
  });

  it("rejects empty and malformed URLs", () => {
    expect(validateScanUrl("")).toBe("Please enter a website URL.");
    expect(validateScanUrl("not a url")).toMatch(/valid URL/i);
  });

  it("rejects unsupported protocols", () => {
    expect(validateScanUrl("ftp://example.com")).toMatch(/http:\/\/ or https:\/\//i);
    expect(validateScanUrl("javascript:alert(1)")).toMatch(/http:\/\/ or https:\/\//i);
  });

  it("rejects embedded credentials", () => {
    expect(validateScanUrl("https://user:pass@example.com")).toMatch(/credentials/i);
  });
});

describe("pasted full URLs and custom mode", () => {
  it("parses a pasted full URL into builder parts", () => {
    const b = parseIntoBuilder("https://acme.io/pricing?ref=1");
    expect(b).not.toBeNull();
    expect(b!.protocol).toBe("https");
    expect(b!.tld).toBe(".io");
    expect(b!.domain).toContain("acme");
    expect(b!.domain).toContain("/pricing?ref=1");
  });

  it("ingestDomainPaste absorbs https paste", () => {
    const next = ingestDomainPaste(DEFAULT_BUILDER, "https://shop.example.com/cart");
    expect(next.protocol).toBe("https");
    expect(composeFromBuilder(next)).toBe("https://shop.example.com/cart");
  });

  it("custom mode preserves path/port/query exactly", () => {
    const parts = partsFromCanonical("http://example.com:3000/a?b=1#c");
    // May land in builder or custom; canonical compose must preserve semantics
    const custom = switchMode(
      { mode: "builder", builder: DEFAULT_BUILDER, customUrl: "" },
      "custom"
    );
    const withUrl = {
      ...custom,
      customUrl: "http://example.com:3000/a?b=1#c",
    };
    expect(withUrl.customUrl).toBe("http://example.com:3000/a?b=1#c");
    expect(validateScanUrl(withUrl.customUrl)).toBeNull();
  });
});

describe("mode switching preserves input", () => {
  it("builder → custom copies composed URL", () => {
    const start = {
      mode: "builder" as const,
      builder: { ...DEFAULT_BUILDER, domain: "example", tld: ".com" as const },
      customUrl: "",
    };
    const next = switchMode(start, "custom");
    expect(next.mode).toBe("custom");
    expect(next.customUrl).toBe("https://example.com");
  });

  it("custom → builder parses back", () => {
    const start = {
      mode: "custom" as const,
      builder: { ...DEFAULT_BUILDER },
      customUrl: "https://docs.example.org/guide",
    };
    const next = switchMode(start, "builder");
    expect(next.mode).toBe("builder");
    expect(next.builder.protocol).toBe("https");
    expect(composeFromBuilder(next.builder)).toBe("https://docs.example.org/guide");
  });

  it("repeated mode switches do not crash or wipe data", () => {
    let parts = partsFromCanonical("https://example.com/path");
    parts = switchMode(parts, "custom");
    parts = switchMode(parts, "builder");
    parts = switchMode(parts, "custom");
    expect(parts.customUrl).toContain("example.com");
    expect(validateScanUrl(parts.customUrl || composeFromBuilder(parts.builder))).toBeNull();
  });
});
