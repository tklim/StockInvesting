import { v } from "convex/values";
import { action } from "./_generated/server";
import { api, internal } from "./_generated/api";

declare const process: {
  env: Record<string, string | undefined>;
};

type OpenAIResponsesResult = {
  output?: Array<{
    content?: Array<{
      type?: string;
      text?: string;
    }>;
  }>;
  output_text?: string;
};

type AiResearchReport = {
  summary: string;
  bullPoints: string[];
  bearPoints: string[];
  thesisPoints: string[];
  watchItems: string[];
};

const normalizeTicker = (ticker: string) => ticker.trim().toUpperCase();

const extractResponseText = (response: OpenAIResponsesResult) => {
  if (typeof response.output_text === "string" && response.output_text.trim()) {
    return response.output_text.trim();
  }

  const text = response.output
    ?.flatMap((item) => item.content ?? [])
    .map((content) => content.text ?? "")
    .join("\n")
    .trim();

  if (!text) {
    throw new Error("The LLM returned an empty research report.");
  }

  return text;
};

const parseAiReport = (text: string): AiResearchReport => {
  const normalizedText = text
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/, "")
    .trim();
  const parsed = JSON.parse(normalizedText) as Partial<AiResearchReport>;

  return {
    summary: typeof parsed.summary === "string" ? parsed.summary : "",
    bullPoints: Array.isArray(parsed.bullPoints)
      ? parsed.bullPoints.filter((item): item is string => typeof item === "string").slice(0, 3)
      : [],
    bearPoints: Array.isArray(parsed.bearPoints)
      ? parsed.bearPoints.filter((item): item is string => typeof item === "string").slice(0, 3)
      : [],
    thesisPoints: Array.isArray(parsed.thesisPoints)
      ? parsed.thesisPoints.filter((item): item is string => typeof item === "string").slice(0, 3)
      : [],
    watchItems: Array.isArray(parsed.watchItems)
      ? parsed.watchItems.filter((item): item is string => typeof item === "string").slice(0, 3)
      : [],
  };
};

export const generateReport = action({
  args: { ticker: v.string() },
  handler: async (ctx, args) => {
    const apiKey = process.env.OPENAI_API_KEY;
    const baseUrl = process.env.OPENAI_BASE_URL || "https://api.openai.com/v1";
    const model = process.env.OPENAI_MODEL || "gpt-5-mini";
    if (!apiKey) {
      throw new Error(
        "OPENAI_API_KEY is not configured. Set OPENAI_API_KEY to generate an LLM research report."
      );
    }

    const ticker = normalizeTicker(args.ticker);
    const bundle = await ctx.runQuery(api.stocks.researchBundle, { ticker });
    if (!bundle.stock) {
      throw new Error(`No stock data found for ${ticker}. Sync the ticker first.`);
    }

    const promptPayload = {
      stock: {
        ticker: bundle.stock.ticker,
        companyName: bundle.stock.companyName,
        exchange: bundle.stock.exchange,
        sector: bundle.stock.sector,
        price: bundle.stock.price,
        changePercent: bundle.stock.changePercent,
        marketCap: bundle.stock.marketCap,
        peRatio: bundle.stock.peRatio,
        revenueTtm: bundle.stock.revenueTtm,
        epsTtm: bundle.stock.epsTtm,
        dividendYield: bundle.stock.dividendYield,
      },
      latestNews: bundle.news.map((item) => ({
        headline: item.headline,
        source: item.source,
        publishedAt: item.publishedAt,
      })),
      notes: bundle.notes.map((item) => ({
        title: item.title,
        body: item.body,
        tag: item.tag,
      })),
      liveResearchItems: bundle.researchItems.map((item) => ({
        kind: item.kind,
        title: item.title,
        body: item.body,
        status: item.status,
      })),
    };

    const response = await fetch(`${baseUrl}/responses`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        input: [
          {
            role: "system",
            content: [
              {
                type: "input_text",
                text:
                  "You are an equity research assistant. Produce a concise investing brief using only the supplied data. Return valid JSON with keys: summary, bullPoints, bearPoints, thesisPoints, watchItems. Each list should have exactly 3 short items. Be balanced, specific, and avoid hype.",
              },
            ],
          },
          {
            role: "user",
            content: [
              {
                type: "input_text",
                text: JSON.stringify(promptPayload),
              },
            ],
          },
        ],
      }),
    });

    if (!response.ok) {
      throw new Error(`LLM report generation failed with ${response.status}.`);
    }

    const data = (await response.json()) as OpenAIResponsesResult;
    const report = parseAiReport(extractResponseText(data));
    const generatedAt = Date.now();

    await ctx.runMutation(internal.stocks.upsertAiReport, {
      ticker,
      summary: report.summary,
      bullPoints: report.bullPoints,
      bearPoints: report.bearPoints,
      thesisPoints: report.thesisPoints,
      watchItems: report.watchItems,
      provider: baseUrl.includes("openai.com") ? "OpenAI" : "OpenAI-compatible",
      model,
      generatedAt,
    });

    return {
      ticker,
      provider: baseUrl.includes("openai.com") ? "OpenAI" : "OpenAI-compatible",
      model,
      generatedAt,
    };
  },
});
