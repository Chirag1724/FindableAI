import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Bot, Search, ShieldCheck } from "lucide-react";
import { LighthouseGauge } from "@/components/LighthouseGauge";

describe("LighthouseGauge", () => {
  it("renders the engine label and animated score value", () => {
    render(
      <LighthouseGauge
        label="ChatGPT"
        engineKey="chatgpt"
        score={92}
        icon={Bot}
        accentColorClass="text-emerald-400"
      />
    );

    expect(screen.getByText("ChatGPT")).toBeInTheDocument();
    expect(screen.getByText("92")).toBeInTheDocument();
    expect(screen.getByTestId("lighthouse-gauge-chatgpt")).toBeInTheDocument();
  });

  it("renders 'Good' tier badge for scores >= 90", () => {
    render(
      <LighthouseGauge
        label="ChatGPT"
        engineKey="chatgpt"
        score={95}
        icon={Bot}
        accentColorClass="text-emerald-400"
      />
    );

    expect(screen.getByText("Good")).toBeInTheDocument();
  });

  it("renders 'Needs Improvement' tier badge for scores between 50 and 89", () => {
    render(
      <LighthouseGauge
        label="Perplexity"
        engineKey="perplexity"
        score={64}
        icon={Search}
        accentColorClass="text-amber-400"
      />
    );

    expect(screen.getByText("Needs Improvement")).toBeInTheDocument();
  });

  it("renders 'Poor' tier badge for scores < 50", () => {
    render(
      <LighthouseGauge
        label="Claude"
        engineKey="claude"
        score={42}
        icon={ShieldCheck}
        accentColorClass="text-rose-400"
      />
    );

    expect(screen.getByText("Poor")).toBeInTheDocument();
  });

  it("renders criteria breakdown items when criteria prop is passed", () => {
    const criteria = {
      bot_access: { score: 100, detail: "All bots allowed" },
      schema_coverage: { score: 85, detail: "Valid JSON-LD" },
    };

    render(
      <LighthouseGauge
        label="ChatGPT"
        engineKey="chatgpt"
        score={92}
        icon={Bot}
        accentColorClass="text-emerald-400"
        criteria={criteria}
      />
    );

    expect(screen.getByText("Bot Access")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("Schema Coverage")).toBeInTheDocument();
    expect(screen.getByText("85%")).toBeInTheDocument();
  });
});
