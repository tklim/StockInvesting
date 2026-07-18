import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import type { IncomingMessage, ServerResponse } from "node:http";

type LocalAiBridgeRequest = {
  ticker: string;
  asOf?: string;
  stock: {
    ticker: string;
    companyName: string;
    exchange: string;
    sector: string;
    price: number;
    changePercent: number;
    marketCap: string;
    peRatio: string;
    revenueTtm: string;
    epsTtm: string;
    dividendYield: string;
  };
  news: Array<{
    headline: string;
    source: string;
    publishedAt: number;
  }>;
  notes: Array<{
    title: string;
    body: string;
    tag: string;
  }>;
  researchItems: Array<{
    kind: string;
    title: string;
    body: string;
    status?: string;
  }>;
  aiReport?: {
    summary?: string;
    bullPoints?: string[];
    bearPoints?: string[];
    thesisPoints?: string[];
    watchItems?: string[];
    provider?: string;
    model?: string;
    generatedAt?: number;
  };
  investmentThesis?: {
    summary?: string;
    thesisPoints?: string[];
    watchItems?: string[];
    source?: string;
    updatedAt?: number;
  };
  financialReport?: unknown;
  snapshots?: unknown[];
};

const parseJsonBody = async (request: NodeJS.ReadableStream) => {
  const chunks: Uint8Array[] = [];
  for await (const chunk of request) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }

  const body = Buffer.concat(chunks).toString("utf8");
  return JSON.parse(body) as LocalAiBridgeRequest;
};

const normalizeResponseText = (text: string) =>
  text
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();

const parseStructuredReport = (text: string) => {
  const parsed = JSON.parse(normalizeResponseText(text)) as {
    summary?: string;
    bullPoints?: string[];
    bearPoints?: string[];
    thesisPoints?: string[];
    watchItems?: string[];
  };

  const cleanPointList = (items?: string[]) =>
    Array.isArray(items)
      ? items
          .filter((item): item is string => typeof item === "string")
          .map((item) => item.trim())
          .filter(Boolean)
          .slice(0, 3)
      : [];
  const report = {
    summary: typeof parsed.summary === "string" ? parsed.summary.trim() : "",
    bullPoints: Array.isArray(parsed.bullPoints)
      ? cleanPointList(parsed.bullPoints)
      : [],
    bearPoints: cleanPointList(parsed.bearPoints),
    thesisPoints: cleanPointList(parsed.thesisPoints),
    watchItems: cleanPointList(parsed.watchItems),
  };

  if (
    !report.summary ||
    !report.bullPoints.length ||
    !report.bearPoints.length ||
    !report.watchItems.length
  ) {
    throw new Error("The local LLM returned an incomplete research brief.");
  }

  return report;
};

const parseStructuredThesis = (text: string) => {
  const parsed = JSON.parse(normalizeResponseText(text)) as {
    summary?: string;
    thesisPoints?: string[];
    watchItems?: string[];
  };

  return {
    summary: typeof parsed.summary === "string" ? parsed.summary : "",
    thesisPoints: Array.isArray(parsed.thesisPoints)
      ? parsed.thesisPoints.filter((item): item is string => typeof item === "string").slice(0, 4)
      : [],
    watchItems: Array.isArray(parsed.watchItems)
      ? parsed.watchItems.filter((item): item is string => typeof item === "string").slice(0, 4)
      : [],
  };
};

const cleanString = (value: unknown, maxLength: number) =>
  typeof value === "string" ? value.trim().slice(0, maxLength) : "";

const chatCompletionsUrl = (baseUrl: string) =>
  baseUrl.replace(/\/$/, "").endsWith("/chat/completions")
    ? baseUrl
    : `${baseUrl.replace(/\/$/, "")}/chat/completions`;

const parseStructuredNotes = (text: string) => {
  const parsed = JSON.parse(normalizeResponseText(text)) as {
    notes?: Array<{
      title?: unknown;
      body?: unknown;
      tag?: unknown;
    }>;
  };

  const notes = Array.isArray(parsed.notes) ? parsed.notes : [];
  return {
    notes: notes
      .map((note) => ({
        title: cleanString(note.title, 120),
        body: cleanString(note.body, 520),
        tag: cleanString(note.tag, 40) || "AI Note",
      }))
      .filter((note) => note.title && note.body)
      .slice(0, 6),
  };
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [
      react(),
      {
        name: "local-ai-bridge",
        configureServer(server) {
          const handleLocalLlmRequest = async (
            req: IncomingMessage,
            res: ServerResponse<IncomingMessage>,
            mode: "report" | "thesis" | "notes"
          ) => {
            const baseUrl =
              env.LOCAL_LLM_ENDPOINT ||
              env.LOCAL_LLM_BASE_URL ||
              "https://aivie-exchange-tnt.sains.com.my:11443/v1";
            const apiKey = env.LOCAL_LLM_API_KEY_OVERRIDE || env.LOCAL_LLM_API_KEY;
            const model = env.LOCAL_LLM_MODEL_OVERRIDE || env.LOCAL_LLM_MODEL || "si-gpt-oss-120b";

            if (!apiKey) {
              res.statusCode = 500;
              res.setHeader("Content-Type", "text/plain");
              res.end("LOCAL_LLM_API_KEY is not configured.");
              return;
            }

            try {
              const payload = await parseJsonBody(req);
              const llmResponse = await fetch(chatCompletionsUrl(baseUrl), {
                method: "POST",
                headers: {
                  Authorization: `Bearer ${apiKey}`,
                  "Content-Type": "application/json",
                },
                body: JSON.stringify({
                  model,
                  messages: [
                    {
                      role: "system",
                      content:
                        mode === "report"
                          ? "You are a skeptical equity research analyst. Use only the supplied data and never invent metrics, events, or certainty. Return valid JSON only with keys: summary, bullPoints, bearPoints, thesisPoints, watchItems. The summary must be exactly 2 concise sentences that state the current setup and the central tension. Each list must contain exactly 3 concise, non-duplicative strings. Bull and bear points should cite a specific supplied fact or clearly label an inference. Thesis points should express testable drivers, not recommendations. Watch items must be measurable validation or invalidation signals and include a threshold, date, filing, or event when the supplied data supports one. Explicitly say when important evidence is unavailable. Do not include markdown fences, investment advice, price predictions, or hidden reasoning."
                          : mode === "thesis"
                            ? "You are an investment thesis assistant. Return valid JSON only with keys: summary, thesisPoints, watchItems. The summary should be 2-3 sentences. thesisPoints should have exactly 4 concise points. watchItems should have exactly 4 concise validation or invalidation signals. Do not include markdown fences. Do not include hidden reasoning."
                            : "You are an investing research chief-of-staff. Think carefully about the supplied company profile, latest news, existing notes, AI report, saved thesis, financial report, and snapshots. Return valid JSON only with key notes. notes must contain exactly 5 objects with title, body, tag. Make each note practical, specific, non-duplicative, and useful for an investor's next action. Prefer concrete follow-up checks, thesis validation questions, financial watchpoints, and risk triggers over generic summaries. Use tags from: AI Note, News, Financials, Risk, Follow-up, Thesis. Do not include markdown fences. Do not include hidden reasoning.",
                    },
                    {
                      role: "user",
                      content: JSON.stringify(payload),
                    },
                  ],
                  max_tokens: mode === "notes" ? 1400 : 900,
                  temperature: mode === "notes" ? 0.25 : 0.3,
                }),
              });

              const data = (await llmResponse.json()) as {
                error?: { message?: string };
                choices?: Array<{
                  message?: {
                    content?: string;
                  };
                }>;
                model?: string;
              };

              if (!llmResponse.ok || data.error?.message) {
                res.statusCode = 502;
                res.setHeader("Content-Type", "text/plain");
                res.end(data.error?.message || "Local LLM bridge request failed.");
                return;
              }

              const content = data.choices?.[0]?.message?.content;
              if (!content) {
                res.statusCode = 502;
                res.setHeader("Content-Type", "text/plain");
                res.end("The local LLM returned empty content.");
                return;
              }

              const parsed =
                mode === "report"
                  ? parseStructuredReport(content)
                  : mode === "thesis"
                    ? parseStructuredThesis(content)
                    : parseStructuredNotes(content);

              res.statusCode = 200;
              res.setHeader("Content-Type", "application/json");
              res.end(
                JSON.stringify({
                  ticker: payload.ticker,
                  ...parsed,
                  provider: "Local bridge",
                  model: data.model || model,
                  source:
                    mode === "report"
                      ? "AI research report"
                      : mode === "thesis"
                        ? "AI thesis proposal"
                        : "AI notes proposal",
                  generatedAt: Date.now(),
                })
              );
            } catch (error) {
              res.statusCode = 500;
              res.setHeader("Content-Type", "text/plain");
              res.end(
                error instanceof Error
                  ? error.message
                  : "The local AI bridge failed unexpectedly."
              );
            }
          };

          server.middlewares.use("/local-ai/report", async (req, res) => {
            if (req.method !== "POST") {
              res.statusCode = 405;
              res.setHeader("Content-Type", "text/plain");
              res.end("Method not allowed");
              return;
            }
            await handleLocalLlmRequest(req, res, "report");
          });

          server.middlewares.use("/local-ai/thesis", async (req, res) => {
            if (req.method !== "POST") {
              res.statusCode = 405;
              res.setHeader("Content-Type", "text/plain");
              res.end("Method not allowed");
              return;
            }

            await handleLocalLlmRequest(req, res, "thesis");
          });

          server.middlewares.use("/local-ai/notes", async (req, res) => {
            if (req.method !== "POST") {
              res.statusCode = 405;
              res.setHeader("Content-Type", "text/plain");
              res.end("Method not allowed");
              return;
            }

            await handleLocalLlmRequest(req, res, "notes");
          });
        },
      },
    ],
  };
});
