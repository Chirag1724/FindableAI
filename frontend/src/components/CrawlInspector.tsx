"use client";

import { useState } from "react";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
  BarChart,
  Bar,
} from "recharts";
import {
  Code2,
  Activity,
  Layers,
  CheckCircle2,
  FileCode,
  Terminal,
  ChevronRight,
  Database,
} from "lucide-react";

interface RouteData {
  id: string;
  name: string;
  page: string;
  chunks: number;
  latency: number;
  tokens: number;
  integrity: string;
  schema: string;
  nodes: {
    tag: string;
    class: string;
    chunks: string;
    tokens: number;
    status: string;
    line: string;
    selector: string;
    preview: string;
  }[];
}

const ROUTES_DATA: RouteData[] = [
  {
    id: "all",
    name: "All Routes",
    page: "Whole Site",
    chunks: 148,
    latency: 140,
    tokens: 4820,
    integrity: "99.2%",
    schema: "TechArticle, Schema.org/SoftwareApp",
    nodes: [
      {
        tag: "article",
        class: "docs-content",
        chunks: "42 chunks",
        tokens: 1240,
        status: "Semantic Root",
        line: "L12",
        selector: "article.docs-content",
        preview: "Comprehensive API reference for machine discoverability extraction and indexing.",
      },
      {
        tag: "section",
        class: "api-parameters",
        chunks: "18 chunks",
        tokens: 680,
        status: "Schema Verified",
        line: "L48",
        selector: "article.docs-content > section.api-spec > table.parameters",
        preview: "POST /v1/audits: rate limits 1,000 req/min for Enterprise tier with 99.9% uptime SLA.",
      },
      {
        tag: "table",
        class: "pricing-matrix",
        chunks: "8 chunks",
        tokens: 420,
        status: "CSS Anchored",
        line: "L86",
        selector: "main > section.pricing > div.grid > table.pricing-matrix",
        preview: "Pro Tier: $49/mo, 50,000 queries, 5 team seats, continuous monitoring.",
      },
      {
        tag: "script",
        class: "ld+json",
        chunks: "JSON-LD",
        tokens: 310,
        status: "Microdata",
        line: "L112",
        selector: "head > script[type='application/ld+json']",
        preview: '{"@context":"https://schema.org","@type":"SoftwareApplication","name":"FindableAI"}',
      },
    ],
  },
  {
    id: "home",
    name: "/",
    page: "/",
    chunks: 38,
    latency: 140,
    tokens: 1180,
    integrity: "99.4%",
    schema: "WebSite, Organization",
    nodes: [
      {
        tag: "header",
        class: "hero-section",
        chunks: "12 chunks",
        tokens: 380,
        status: "Semantic Root",
        line: "L18",
        selector: "main > header.hero-section",
        preview: "Discoverability, engineered with precision. Audit answer engine citation rates.",
      },
      {
        tag: "div",
        class: "feature-grid",
        chunks: "16 chunks",
        tokens: 520,
        status: "CSS Anchored",
        line: "L64",
        selector: "main > section#features > div.feature-grid",
        preview: "Headless crawlers extract semantic trees while preserving precise CSS selector paths.",
      },
    ],
  },
  {
    id: "docs",
    name: "/docs",
    page: "/docs",
    chunks: 44,
    latency: 190,
    tokens: 1540,
    integrity: "99.8%",
    schema: "TechArticle",
    nodes: [
      {
        tag: "article",
        class: "docs-content",
        chunks: "42 chunks",
        tokens: 1240,
        status: "Semantic Root",
        line: "L12",
        selector: "article.docs-content",
        preview: "Comprehensive API reference for machine discoverability extraction and indexing.",
      },
      {
        tag: "section",
        class: "api-parameters",
        chunks: "18 chunks",
        tokens: 680,
        status: "Schema Verified",
        line: "L48",
        selector: "article.docs-content > section.api-spec > table.parameters",
        preview: "POST /v1/audits: rate limits 1,000 req/min for Enterprise tier with 99.9% uptime SLA.",
      },
    ],
  },
  {
    id: "pricing",
    name: "/pricing",
    page: "/pricing",
    chunks: 28,
    latency: 110,
    tokens: 920,
    integrity: "98.9%",
    schema: "OfferCatalog, PriceSpecification",
    nodes: [
      {
        tag: "table",
        class: "pricing-matrix",
        chunks: "8 chunks",
        tokens: 420,
        status: "CSS Anchored",
        line: "L86",
        selector: "main > section.pricing > div.grid > table.pricing-matrix",
        preview: "Pro Tier: $49/mo, 50,000 queries, 5 team seats, continuous monitoring.",
      },
      {
        tag: "ul",
        class: "tier-features",
        chunks: "14 chunks",
        tokens: 380,
        status: "Schema Verified",
        line: "L142",
        selector: "section.pricing > div.tier-cards > ul.tier-features",
        preview: "Enterprise: custom SLA, dedicated crawler IPs, SSO SAML 2.0, audit logs.",
      },
    ],
  },
  {
    id: "security",
    name: "/security",
    page: "/security",
    chunks: 16,
    latency: 95,
    tokens: 640,
    integrity: "100%",
    schema: "SecurityPolicy",
    nodes: [
      {
        tag: "section",
        class: "compliance-trust",
        chunks: "10 chunks",
        tokens: 390,
        status: "Semantic Root",
        line: "L24",
        selector: "main > section.compliance-trust",
        preview: "SOC2 Type II certified, ISO 27001 compliant, GDPR & CCPA privacy verified.",
      },
      {
        tag: "script",
        class: "ld+json",
        chunks: "JSON-LD",
        tokens: 250,
        status: "Microdata",
        line: "L88",
        selector: "head > script[type='application/ld+json']",
        preview: '{"@context":"https://schema.org","@type":"SecurityPolicy","certified":"SOC2-Type-II"}',
      },
    ],
  },
];

const ROUTE_CHART_SERIES = [
  { route: "/", label: "Home", latency: 140, chunks: 38, tokens: 1180 },
  { route: "/docs", label: "Docs", latency: 190, chunks: 44, tokens: 1540 },
  { route: "/pricing", label: "Pricing", latency: 110, chunks: 28, tokens: 920 },
  { route: "/api", label: "API", latency: 160, chunks: 22, tokens: 740 },
  { route: "/security", label: "Security", latency: 95, chunks: 16, tokens: 640 },
];

export function CrawlInspector() {
  const [selectedRouteId, setSelectedRouteId] = useState<string>("all");
  const [selectedNodeIndex, setSelectedNodeIndex] = useState<number>(1);
  const [chartMetric, setChartMetric] = useState<"latency" | "chunks">("latency");

  const currentRoute =
    ROUTES_DATA.find((r) => r.id === selectedRouteId) || ROUTES_DATA[0];
  const activeNode =
    currentRoute.nodes[selectedNodeIndex] || currentRoute.nodes[0];

  return (
    <div className="rounded-xl bg-surface shadow-border overflow-hidden text-left">
      {/* 1. Header Toolbar with Live Status & Route Switcher */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-4 sm:p-5 border-b border-white/[0.08] bg-surface-secondary/40">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-mono text-xs font-semibold text-white tracking-wide">
              HEADLESS CHROMIUM v124
            </span>
          </div>
          <span className="hidden sm:inline text-white/[0.2]">&bull;</span>
          <span className="hidden sm:inline font-mono text-[11px] text-text-muted">
            DOM Extraction Engine Active
          </span>
        </div>

        {/* Route Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 lg:pb-0 scrollbar-none">
          {ROUTES_DATA.map((r) => (
            <button
              key={r.id}
              onClick={() => {
                setSelectedRouteId(r.id);
                setSelectedNodeIndex(0);
              }}
              className={`px-2.5 py-1 rounded-md text-[11px] font-mono tracking-tight transition-all duration-150 shrink-0 ${
                selectedRouteId === r.id
                  ? "bg-white text-black font-semibold shadow-sm"
                  : "bg-surface-secondary text-text-muted hover:text-white hover:bg-white/[0.06]"
              }`}
            >
              {r.name}
            </button>
          ))}
        </div>
      </div>

      {/* 2. Four Telemetry Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/[0.08]">
        {[
          {
            label: "Pages Crawled",
            value: selectedRouteId === "all" ? "12" : "1",
            sub: "100% reachable",
            icon: GlobeIcon,
          },
          {
            label: "DOM Chunks",
            value: String(currentRoute.chunks),
            sub: "CSS path anchored",
            icon: Layers,
          },
          {
            label: "Stream Latency",
            value: `${currentRoute.latency} ms`,
            sub: "Average per route",
            icon: Activity,
          },
          {
            label: "Tree Integrity",
            value: currentRoute.integrity,
            sub: "Zero DOM loss",
            icon: CheckCircle2,
          },
        ].map((stat) => (
          <div key={stat.label} className="p-4 sm:p-5 bg-surface">
            <div className="flex items-center justify-between text-text-muted mb-1">
              <span className="text-[10px] uppercase font-mono tracking-wider">
                {stat.label}
              </span>
              <stat.icon className="h-3.5 w-3.5 text-text-muted opacity-60" />
            </div>
            <p className="text-xl sm:text-2xl font-semibold text-white font-mono">
              {stat.value}
            </p>
            <p className="text-[11px] text-emerald-400 font-mono mt-0.5">
              {stat.sub}
            </p>
          </div>
        ))}
      </div>

      {/* 3. Two-Column Visual Inspection Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-px bg-white/[0.08]">
        {/* Left Column: Parsed DOM Hierarchy Tree (7 cols) */}
        <div className="lg:col-span-7 p-5 sm:p-6 bg-surface flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <Code2 className="h-4 w-4 text-sky-400" />
                <span className="font-mono text-xs font-semibold text-white tracking-wide uppercase">
                  Parsed DOM Node Hierarchy
                </span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-950/50 text-sky-400 ring-1 ring-inset ring-sky-800">
                {currentRoute.nodes.length} Verified Nodes
              </span>
            </div>

            {/* Tree Nodes List */}
            <div className="space-y-2 mt-3.5 font-mono text-xs">
              {currentRoute.nodes.map((node, idx) => {
                const isSelected = idx === selectedNodeIndex;
                return (
                  <button
                    key={idx}
                    onClick={() => setSelectedNodeIndex(idx)}
                    className={`w-full text-left p-3 rounded-lg transition-all duration-150 flex items-center justify-between gap-3 ${
                      isSelected
                        ? "bg-surface-secondary ring-1 ring-emerald-500/40 shadow-sm"
                        : "bg-surface-secondary/50 hover:bg-surface-secondary hover:ring-1 hover:ring-white/10"
                    }`}
                  >
                    <div className="flex items-center gap-2.5 truncate">
                      <span className="text-text-muted text-[10px] w-6 shrink-0">
                        {node.line}
                      </span>
                      <span className="text-sky-400 font-medium">
                        &lt;{node.tag}
                      </span>
                      <span className="text-violet-400 truncate">
                        .{node.class}&gt;
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                          isSelected
                            ? "bg-emerald-950/60 text-emerald-400 ring-1 ring-inset ring-emerald-700"
                            : "bg-surface text-text-muted ring-1 ring-inset ring-white/[0.08]"
                        }`}
                      >
                        {node.status}
                      </span>
                      <span className="text-text-muted text-[10px] hidden sm:inline">
                        {node.chunks}
                      </span>
                      <ChevronRight
                        className={`h-3.5 w-3.5 transition-transform ${
                          isSelected ? "text-emerald-400 translate-x-0.5" : "text-text-muted opacity-40"
                        }`}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Node Detail Card */}
          {activeNode && (
            <div className="p-3.5 rounded-lg bg-surface-secondary/70 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-emerald-400 font-medium flex items-center gap-1.5">
                  <Database className="h-3 w-3" />
                  Extracted Semantic Text Content
                </span>
                <span className="text-text-muted">{activeNode.tokens} Tokens</span>
              </div>
              <p className="text-xs text-text-primary leading-relaxed font-sans bg-black/30 p-2.5 rounded border border-white/[0.04]">
                &quot;{activeNode.preview}&quot;
              </p>
            </div>
          )}
        </div>

        {/* Right Column: Interactive Latency / Chunks Visual Graph (5 cols) */}
        <div className="lg:col-span-5 p-5 sm:p-6 bg-surface flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
              <span className="font-mono text-xs font-semibold text-white tracking-wide uppercase">
                Extraction Metrics
              </span>
              <div className="flex items-center gap-1 bg-surface-secondary p-0.5 rounded-md">
                <button
                  onClick={() => setChartMetric("latency")}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                    chartMetric === "latency"
                      ? "bg-white text-black font-semibold"
                      : "text-text-muted hover:text-white"
                  }`}
                >
                  Latency (ms)
                </button>
                <button
                  onClick={() => setChartMetric("chunks")}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                    chartMetric === "chunks"
                      ? "bg-white text-black font-semibold"
                      : "text-text-muted hover:text-white"
                  }`}
                >
                  DOM Chunks
                </button>
              </div>
            </div>

            {/* Recharts Area / Bar Visual Graph */}
            <div className="h-48 w-full mt-4">
              <ResponsiveContainer width="100%" height="100%">
                {chartMetric === "latency" ? (
                  <AreaChart
                    data={ROUTE_CHART_SERIES}
                    margin={{ top: 10, right: 10, left: -25, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="crawlLatencyGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="label"
                      tick={{ fill: "#A1A1A1", fontSize: 10, fontFamily: "monospace" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "#666666", fontSize: 9, fontFamily: "monospace" }}
                      axisLine={false}
                      tickLine={false}
                      domain={[0, 220]}
                    />
                    <RechartsTooltip
                      content={({ active, payload }) => {
                        if (!active || !payload || !payload.length) return null;
                        const d = payload[0].payload as {
                          route: string;
                          label: string;
                          latency: number;
                          chunks: number;
                          tokens: number;
                        };
                        return (
                          <div className="rounded-lg bg-surface-secondary px-3 py-2 text-xs shadow-xl border border-white/[0.1] font-mono">
                            <p className="font-semibold text-white">{d.route}</p>
                            <p className="text-emerald-400 text-[11px] mt-0.5">
                              Latency: {d.latency}ms
                            </p>
                            <p className="text-text-muted text-[11px]">
                              Extracted: {d.chunks} chunks ({d.tokens} tokens)
                            </p>
                          </div>
                        );
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="latency"
                      stroke="#10b981"
                      strokeWidth={2}
                      fill="url(#crawlLatencyGrad)"
                    />
                  </AreaChart>
                ) : (
                  <BarChart
                    data={ROUTE_CHART_SERIES}
                    margin={{ top: 10, right: 10, left: -25, bottom: 0 }}
                  >
                    <XAxis
                      dataKey="label"
                      tick={{ fill: "#A1A1A1", fontSize: 10, fontFamily: "monospace" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "#666666", fontSize: 9, fontFamily: "monospace" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <RechartsTooltip
                      content={({ active, payload }) => {
                        if (!active || !payload || !payload.length) return null;
                        const d = payload[0].payload as {
                          route: string;
                          chunks: number;
                          tokens: number;
                        };
                        return (
                          <div className="rounded-lg bg-surface-secondary px-3 py-2 text-xs shadow-xl border border-white/[0.1] font-mono">
                            <p className="font-semibold text-white">{d.route}</p>
                            <p className="text-sky-400 text-[11px] mt-0.5">
                              Chunks: {d.chunks} units
                            </p>
                            <p className="text-text-muted text-[11px]">
                              Token Load: {d.tokens} tokens
                            </p>
                          </div>
                        );
                      }}
                    />
                    <Bar dataKey="chunks" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>

          {/* Microdata / Schema Indicator */}
          <div className="p-3 rounded-lg bg-surface-secondary/40 border border-white/[0.06] space-y-1 font-mono text-[11px]">
            <div className="flex items-center justify-between text-text-muted">
              <span className="text-violet-400 flex items-center gap-1.5 font-medium">
                <FileCode className="h-3.5 w-3.5" />
                Schema.org Microdata
              </span>
              <span className="text-emerald-400 text-[10px]">Valid JSON-LD</span>
            </div>
            <p className="text-text-primary text-[10px] truncate">
              {currentRoute.schema}
            </p>
          </div>
        </div>
      </div>

      {/* 4. Bottom Live Terminal Telemetry Stream */}
      <div className="p-3.5 bg-background border-t border-white/[0.08] font-mono text-[11px] text-text-muted flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-2 truncate min-w-0">
          <Terminal className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
          <span className="text-emerald-400 font-semibold shrink-0">CSS Selector:</span>
          <span className="text-text-primary truncate">{activeNode.selector}</span>
        </div>
        <div className="flex items-center gap-3 shrink-0 text-[10px]">
          <span className="text-text-muted">{activeNode.line}</span>
          <span className="text-white/[0.2]">&bull;</span>
          <span className="text-emerald-400 font-medium">Verified Semantic Anchor</span>
        </div>
      </div>
    </div>
  );
}

function GlobeIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}
