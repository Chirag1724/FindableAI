import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IntentMatrix } from "@/components/IntentMatrix";
import type { IntentEvaluation } from "@/types/scan";

// --- Fixtures ---

function makeIntent(overrides: Partial<IntentEvaluation> & { intent_id: string }): IntentEvaluation {
  return {
    intent_id: overrides.intent_id,
    query: overrides.query ?? "Default query?",
    category: overrides.category ?? "availability",
    status: overrides.status ?? "SUPPORTED",
    reasoning: overrides.reasoning ?? "Evidence found.",
    evidence: overrides.evidence ?? [],
    confidence: overrides.confidence ?? 0.9,
    difficulty: overrides.difficulty,
  };
}

const INTENTS: IntentEvaluation[] = [
  makeIntent({
    intent_id: "int_1",
    query: "Does it offer vegan options?",
    category: "pricing",
    status: "SUPPORTED",
    confidence: 0.94,
  }),
  makeIntent({
    intent_id: "int_2",
    query: "What are the opening hours on weekends?",
    category: "availability",
    status: "CONTRADICTED",
    confidence: 0.88,
  }),
  makeIntent({
    intent_id: "int_3",
    query: "Is there parking available?",
    category: "local",
    status: "UNKNOWN",
    confidence: 0.4,
  }),
];

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    writable: true,
    configurable: true,
  });
});

afterEach(() => vi.restoreAllMocks());

// --- Empty state ---

describe("IntentMatrix - empty state", () => {
  it("renders empty state when intents array is empty", () => {
    render(<IntentMatrix intents={[]} />);
    expect(screen.getByText("No intent evaluations")).toBeInTheDocument();
  });
});

// --- Rendering ---

describe("IntentMatrix - rendering", () => {
  it("renders all intent rows", () => {
    render(<IntentMatrix intents={INTENTS} />);
    expect(screen.getByTestId("intent-row-int_1")).toBeInTheDocument();
    expect(screen.getByTestId("intent-row-int_2")).toBeInTheDocument();
    expect(screen.getByTestId("intent-row-int_3")).toBeInTheDocument();
  });

  it("renders query text in rows", () => {
    render(<IntentMatrix intents={INTENTS} />);
    expect(screen.getByText("Does it offer vegan options?")).toBeInTheDocument();
    expect(screen.getByText("What are the opening hours on weekends?")).toBeInTheDocument();
  });

  it("renders status badges in each row", () => {
    render(<IntentMatrix intents={INTENTS} />);
    // Use getAllByText since 'Supported' appears in both summary chips and the badge
    expect(screen.getAllByText("Supported").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Contradicted").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(1);
  });

  it("renders column headers", () => {
    render(<IntentMatrix intents={INTENTS} />);
    expect(screen.getByText("Query")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Conf.")).toBeInTheDocument();
    expect(screen.getByText("Category")).toBeInTheDocument();
  });
});

// --- Search filter ---

describe("IntentMatrix - search filter", () => {
  it("filters rows by query text", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const searchInput = screen.getByRole("searchbox");
    await userEvent.type(searchInput, "vegan");
    expect(screen.getByText("Does it offer vegan options?")).toBeInTheDocument();
    expect(screen.queryByText("What are the opening hours on weekends?")).not.toBeInTheDocument();
  });

  it("shows 'no results' text when nothing matches", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    await userEvent.type(screen.getByRole("searchbox"), "xyzxyzxyz");
    expect(screen.getByText(/No intents match/i)).toBeInTheDocument();
  });

  it("shows all rows when search is cleared", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const input = screen.getByRole("searchbox");
    await userEvent.type(input, "vegan");
    await userEvent.clear(input);
    expect(screen.getAllByRole("row")).toHaveLength(INTENTS.length + 1); // +1 for thead
  });
});

// --- Status filter buttons ---

describe("IntentMatrix - status filter", () => {
  it("filter button toggles aria-pressed", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const filterGroup = screen.getByRole("group", { name: /filter by status/i });
    const supportedBtn = within(filterGroup).getByText("Supported");
    expect(supportedBtn).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(supportedBtn);
    expect(supportedBtn).toHaveAttribute("aria-pressed", "true");
  });

  it("filters to only SUPPORTED rows when Supported is toggled", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const filterGroup = screen.getByRole("group", { name: /filter by status/i });
    await userEvent.click(within(filterGroup).getByText("Supported"));
    expect(screen.getByTestId("intent-row-int_1")).toBeInTheDocument();
    expect(screen.queryByTestId("intent-row-int_2")).not.toBeInTheDocument();
    expect(screen.queryByTestId("intent-row-int_3")).not.toBeInTheDocument();
  });

  it("de-toggles filter when clicked again", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const filterGroup = screen.getByRole("group", { name: /filter by status/i });
    const btn = within(filterGroup).getByText("Supported");
    await userEvent.click(btn);
    await userEvent.click(btn);
    // All rows visible again
    expect(screen.getAllByTestId(/intent-row/)).toHaveLength(INTENTS.length);
  });
});

// --- Sorting ---

describe("IntentMatrix - sorting", () => {
  it("column header button changes aria-sort on click", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const queryHeader = screen.getByRole("columnheader", { name: /query/i });
    // Default is not the active sort col, so aria-sort should be "none"
    expect(queryHeader).toHaveAttribute("aria-sort", "none");
    await userEvent.click(within(queryHeader).getByRole("button"));
    expect(queryHeader).toHaveAttribute("aria-sort", "ascending");
  });

  it("clicking the active sort column toggles asc/desc", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const confHeader = screen.getByRole("columnheader", { name: /conf/i });
    await userEvent.click(within(confHeader).getByRole("button"));
    expect(confHeader).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(within(confHeader).getByRole("button"));
    expect(confHeader).toHaveAttribute("aria-sort", "descending");
  });
});

// --- Row expansion ---

describe("IntentMatrix - row expansion", () => {
  it("clicking a row expands it (aria-expanded becomes true)", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const row = screen.getByTestId("intent-row-int_1");
    expect(row).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
  });

  it("clicking an expanded row collapses it", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const row = screen.getByTestId("intent-row-int_1");
    await userEvent.click(row);
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "false");
  });

  it("pressing Enter on a row expands it", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const row = screen.getByTestId("intent-row-int_1");
    row.focus();
    await userEvent.keyboard("{Enter}");
    expect(row).toHaveAttribute("aria-expanded", "true");
  });

  it("pressing Space on a row expands it", async () => {
    render(<IntentMatrix intents={INTENTS} />);
    const row = screen.getByTestId("intent-row-int_1");
    row.focus();
    await userEvent.keyboard(" ");
    expect(row).toHaveAttribute("aria-expanded", "true");
  });

  it("expanded row shows reasoning text", async () => {
    const intents = [
      makeIntent({ intent_id: "int_r", query: "Any query?", reasoning: "My special reasoning text." }),
    ];
    render(<IntentMatrix intents={intents} />);
    await userEvent.click(screen.getByTestId("intent-row-int_r"));
    expect(screen.getByText("My special reasoning text.")).toBeInTheDocument();
  });
});