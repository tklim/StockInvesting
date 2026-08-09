import { describe, expect, it } from "vitest";
import {
  extractResponseText,
  chatCompletionsUrl,
  parseAiNotes,
  parseAiReport,
  parseInvestmentThesis,
  responsesUrl,
} from "./aiResearch";

const reportJson = JSON.stringify({
  summary: "Balanced outlook.",
  bullPoints: ["Demand", "Margins", "Balance sheet"],
  bearPoints: ["Valuation", "Competition", "Cyclicality"],
  thesisPoints: ["Execution", "Growth", "Cash flow"],
  watchItems: ["Revenue", "Margins", "Guidance"],
  signalScore: 62,
  signalRationale: "Growth is solid but valuation limits upside.",
});

const thesisJson = JSON.stringify({
  summary: "The setup depends on sustained demand and disciplined execution.",
  thesisPoints: ["Demand", "Execution", "Margins", "Valuation"],
  watchItems: ["Revenue", "Guidance", "Margins", "Competition"],
});

const notesJson = JSON.stringify({
  notes: [
    { title: "Demand checkpoint", body: "Compare the next revenue result with guidance.", tag: "Follow-up" },
    { title: "Margin risk", body: "Track gross-margin direction at earnings.", tag: "Risk" },
    { title: "Thesis validation", body: "Confirm the key driver in the next filing.", tag: "Thesis" },
    { title: "News review", body: "Reassess material company headlines.", tag: "News" },
    { title: "Financial watchpoint", body: "Review cash flow and balance-sheet changes.", tag: "Financials" },
  ],
});

describe("AI research response handling", () => {
  it("selects the assistant output and ignores GPT-OSS reasoning text", () => {
    const text = extractResponseText({
      output: [
        {
          type: "reasoning",
          content: [{ type: "reasoning_text", text: "We need to prepare JSON." }],
        },
        {
          type: "message",
          role: "assistant",
          content: [{ type: "output_text", text: reportJson }],
        },
      ],
    });

    expect(text).toBe(reportJson);
  });

  it("recovers a complete report from reasoning followed by fenced JSON", () => {
    const report = parseAiReport(`We need to assemble the requested fields.\n\n\`\`\`json\n${reportJson}\n\`\`\``);

    expect(report.summary).toBe("Balanced outlook.");
    expect(report.signalScore).toBe(62);
    expect(report.bullPoints).toHaveLength(3);
  });

  it("handles braces inside JSON strings while locating the report", () => {
    const withBraces = reportJson.replace("Balanced outlook.", "Balanced {but uncertain} outlook.");
    const report = parseAiReport(`Analysis first. ${withBraces} End.`);

    expect(report.summary).toBe("Balanced {but uncertain} outlook.");
  });

  it("recovers a thesis from prose-wrapped fenced JSON", () => {
    const thesis = parseInvestmentThesis(`Reasoning omitted.\n\`\`\`json\n${thesisJson}\n\`\`\``);

    expect(thesis.thesisPoints).toHaveLength(4);
    expect(thesis.watchItems).toHaveLength(4);
  });

  it("recovers exactly five practical notes from a response shape with reasoning", () => {
    const notes = parseAiNotes(`I will create the requested notes.\n${notesJson}\nDone.`);

    expect(notes).toHaveLength(5);
    expect(notes[0].tag).toBe("Follow-up");
  });

  it("rejects incomplete generated note sets", () => {
    expect(() => parseAiNotes(JSON.stringify({ notes: [] }))).toThrow("incomplete AI notes");
  });

  it("rejects prose that has no complete report", () => {
    expect(() => parseAiReport("We need to prepare a report.")).toThrow();
  });

  it("builds a Responses API endpoint from a provider base URL", () => {
    expect(responsesUrl("https://openrouter.ai/api/v1/"))
      .toBe("https://openrouter.ai/api/v1/responses");
  });

  it("builds a Chat Completions endpoint for a custom OpenAI-compatible provider", () => {
    expect(chatCompletionsUrl("https://llm.example.test/v1/chat/completions/"))
      .toBe("https://llm.example.test/v1/chat/completions");
  });
});
