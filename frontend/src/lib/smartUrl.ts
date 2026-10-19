/**
 * Smart URL builder helpers — pure, side-effect free.
 * Canonical output is always a full http(s) URL for scan submission.
 */

export const URL_PROTOCOLS = ["https", "http"] as const;
export type UrlProtocol = (typeof URL_PROTOCOLS)[number];

/** TLD options shown in the selector (leading dot). */
export const URL_TLD_OPTIONS = [
  ".com",
  ".in",
  ".org",
  ".net",
  ".io",
  ".dev",
  ".ai",
  ".co",
  ".vercel.app",
] as const;

export type UrlTldOption = (typeof URL_TLD_OPTIONS)[number] | "other";

/** Known suffixes for "already has a TLD" detection (includes selector list + common hosts). */
const KNOWN_TLD_SUFFIXES: readonly string[] = [
  ...URL_TLD_OPTIONS,
  ".app",
  ".edu",
  ".gov",
  ".info",
  ".biz",
  ".me",
  ".tv",
  ".us",
  ".uk",
  ".ca",
  ".de",
  ".fr",
  ".jp",
  ".au",
  ".nz",
  ".tech",
  ".cloud",
  ".shop",
  ".blog",
  ".netlify.app",
  ".github.io",
  ".co.uk",
  ".com.au",
  ".org.uk",
].sort((a, b) => b.length - a.length);

export type UrlInputMode = "builder" | "custom";

export interface BuilderState {
  protocol: UrlProtocol;
  domain: string;
  tld: UrlTldOption;
  customTld: string;
}

export interface SmartUrlParts {
  mode: UrlInputMode;
  builder: BuilderState;
  customUrl: string;
}

export const DEFAULT_BUILDER: BuilderState = {
  protocol: "https",
  domain: "",
  tld: ".com",
  customTld: "",
};

function trim(s: string): string {
  return s.trim();
}

/** Strip accidental scheme from a domain field paste. */
export function stripScheme(raw: string): { protocol: UrlProtocol | null; rest: string } {
  const t = trim(raw);
  const m = t.match(/^(https?):\/\/(.*)$/i);
  if (m) {
    return { protocol: m[1].toLowerCase() as UrlProtocol, rest: m[2] };
  }
  return { protocol: null, rest: t };
}

/**
 * Split host[/path?query#hash] into hostname(+port) and the remainder.
 * Does not rewrite path/query/fragment contents.
 */
export function splitHostAndRest(hostAndRest: string): { host: string; rest: string } {
  const s = trim(hostAndRest);
  if (!s) return { host: "", rest: "" };
  // Authority ends at first /, ?, or #
  const idx = s.search(/[/?#]/);
  if (idx < 0) return { host: s, rest: "" };
  return { host: s.slice(0, idx), rest: s.slice(idx) };
}

/** True when hostname already ends with a known public suffix / TLD. */
export function hostnameHasTld(hostname: string): boolean {
  const host = trim(hostname).toLowerCase().split(":")[0] ?? "";
  if (!host || !host.includes(".")) return false;
  return KNOWN_TLD_SUFFIXES.some(
    (suffix) => host.endsWith(suffix) && host.length > suffix.length
  );
}

function normalizeCustomTld(custom: string): string {
  const t = trim(custom).toLowerCase();
  if (!t) return "";
  return t.startsWith(".") ? t : `.${t}`;
}

/**
 * Compose a canonical URL from builder fields.
 * - Adds protocol only via the selector (never duplicates).
 * - Appends TLD only when hostname does not already have one.
 * - Preserves path, query, port, and fragment present in the domain field.
 */
export function composeFromBuilder(builder: BuilderState): string {
  const protocol = builder.protocol;
  let raw = trim(builder.domain);
  if (!raw) return "";

  const stripped = stripScheme(raw);
  raw = stripped.rest;

  // Drop credentials if pasted into domain (rejected at validate)
  if (raw.includes("@")) {
    // Keep as-is for preview; validateScanUrl will reject
  }

  const { host, rest } = splitHostAndRest(raw);
  if (!host) return "";

  // Append TLD to the hostname label only — never after :port.
  const { name: hostName, portSuffix } = splitHostPort(host);
  let hostname = hostName;
  if (!hostnameHasTld(hostname)) {
    if (builder.tld === "other") {
      const suffix = normalizeCustomTld(builder.customTld);
      if (suffix) hostname = `${hostname}${suffix}`;
    } else {
      hostname = `${hostname}${builder.tld}`;
    }
  }

  return `${protocol}://${hostname}${portSuffix}${rest}`;
}

/** Split `host` or `host:port` (IPv6 bracket form supported). */
export function splitHostPort(host: string): { name: string; portSuffix: string } {
  const h = trim(host);
  if (!h) return { name: "", portSuffix: "" };
  if (h.startsWith("[")) {
    const end = h.indexOf("]");
    if (end >= 0) {
      return { name: h.slice(0, end + 1), portSuffix: h.slice(end + 1) };
    }
  }
  const lastColon = h.lastIndexOf(":");
  if (lastColon > 0 && /^\d+$/.test(h.slice(lastColon + 1))) {
    return { name: h.slice(0, lastColon), portSuffix: h.slice(lastColon) };
  }
  return { name: h, portSuffix: "" };
}

/** Canonical URL for the current smart-url state. */
export function composeCanonical(parts: SmartUrlParts): string {
  if (parts.mode === "custom") {
    return trim(parts.customUrl);
  }
  return composeFromBuilder(parts.builder);
}

/**
 * Parse a full URL into builder fields when possible.
 * Preserves path/query/port/fragment inside the domain field.
 */
export function parseIntoBuilder(url: string): BuilderState | null {
  const trimmed = trim(url);
  if (!trimmed) return { ...DEFAULT_BUILDER };

  try {
    const withScheme =
      /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(trimmed) ? trimmed : `https://${trimmed}`;
    const u = new URL(withScheme);
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;

    const protocol = u.protocol === "http:" ? "http" : "https";
    const hostPort = u.host; // hostname:port
    const pathRest = `${u.pathname === "/" && !u.search && !u.hash ? "" : u.pathname}${u.search}${u.hash}`;

    let domain = hostPort;
    let tld: UrlTldOption = ".com";
    let customTld = "";

    const hostOnly = u.hostname.toLowerCase();
    const matched = KNOWN_TLD_SUFFIXES.find(
      (s) => hostOnly.endsWith(s) && hostOnly.length > s.length
    );
    if (matched && (URL_TLD_OPTIONS as readonly string[]).includes(matched)) {
      tld = matched as (typeof URL_TLD_OPTIONS)[number];
      const baseHost = u.hostname.slice(0, u.hostname.length - matched.length);
      domain = u.port ? `${baseHost}:${u.port}` : baseHost;
    } else if (matched) {
      // Known suffix but not in selector → Other / Custom
      tld = "other";
      customTld = matched;
      const baseHost = u.hostname.slice(0, u.hostname.length - matched.length);
      domain = u.port ? `${baseHost}:${u.port}` : baseHost;
    } else if (hostnameHasTld(u.hostname)) {
      tld = "other";
      const lastDot = u.hostname.lastIndexOf(".");
      customTld = u.hostname.slice(lastDot);
      domain = u.port
        ? `${u.hostname.slice(0, lastDot)}:${u.port}`
        : u.hostname.slice(0, lastDot);
    }

    if (pathRest) domain = `${domain}${pathRest}`;

    return { protocol, domain, tld, customTld };
  } catch {
    return null;
  }
}

export function validateScanUrl(url: string): string | null {
  const trimmed = trim(url);
  if (!trimmed) return "Please enter a website URL.";

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return "Please enter a valid URL (e.g. https://example.com)";
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "URL must start with http:// or https://";
  }

  // Reject embedded credentials (user:pass@host)
  if (parsed.username || parsed.password) {
    return "URLs with embedded credentials are not allowed.";
  }

  const host = parsed.hostname;
  if (!host) {
    return "URL is missing a valid hostname.";
  }

  // Basic hostname sanity (labels, no spaces)
  if (/\s/.test(host) || host.startsWith(".") || host.endsWith(".")) {
    return "Please enter a valid hostname.";
  }

  return null;
}

/**
 * When the user pastes into the domain field, absorb an accidental full URL
 * into builder state without losing path/query.
 */
export function ingestDomainPaste(
  builder: BuilderState,
  pasted: string
): BuilderState {
  const t = trim(pasted);
  if (!t) return { ...builder, domain: "" };

  if (/^https?:\/\//i.test(t) || /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(t)) {
    const parsed = parseIntoBuilder(t);
    if (parsed) return parsed;
  }

  const stripped = stripScheme(t);
  return {
    ...builder,
    protocol: stripped.protocol ?? builder.protocol,
    domain: stripped.rest,
  };
}

export function switchMode(
  parts: SmartUrlParts,
  next: UrlInputMode
): SmartUrlParts {
  if (parts.mode === next) return parts;
  const canonical = composeCanonical(parts);

  if (next === "custom") {
    return {
      mode: "custom",
      builder: parts.builder,
      customUrl: canonical || parts.customUrl,
    };
  }

  // custom → builder
  const parsed = parseIntoBuilder(parts.customUrl || canonical);
  return {
    mode: "builder",
    builder: parsed ?? { ...parts.builder },
    customUrl: parts.customUrl || canonical,
  };
}

export function partsFromCanonical(url: string): SmartUrlParts {
  const trimmed = trim(url);
  if (!trimmed) {
    return { mode: "builder", builder: { ...DEFAULT_BUILDER }, customUrl: "" };
  }
  const parsed = parseIntoBuilder(trimmed);
  if (parsed) {
    return { mode: "builder", builder: parsed, customUrl: trimmed };
  }
  return {
    mode: "custom",
    builder: { ...DEFAULT_BUILDER },
    customUrl: trimmed,
  };
}
