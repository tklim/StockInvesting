import { v } from "convex/values";
import { internalAction } from "./_generated/server";
import { api, internal } from "./_generated/api";

declare const process: {
  env: Record<string, string | undefined>;
};

type OpenAIResponsesResult = {
  output?: Array<{
    type?: string;
    role?: string;
    content?: Array<{
      type?: string;
      text?: string;
    }>;
  }>;
  output_text?: string;
};

type OpenAIChatCompletionsResult = {
  choices?: Array<{
    message?: {
      content?: string;
    };
  }>;
};

type AiResearchReport = {
  summary: string;
  bullPoints: string[];
  bearPoints: string[];
  thesisPoints: string[];
  watchItems: string[];
  signalScore?: number;
  signalRationale?: string;
};

type InvestmentThesis = {
  summary: string;
  thesisPoints: string[];
  watchItems: string[];
};

type AiNote = {
  title: string;
  body: string;
  tag: string;
};

type ProviderRoute = "primary" | "fallback";

type LlmProviderConfig = {
  route: ProviderRoute;
  apiKey: string;
  baseUrl: string;
  model: string;
};

const providerRequestTimeoutMs = 90_000;

const normalizeTicker = (ticker: string) => ticker.trim().toUpperCase();

export const responsesUrl = (baseUrl: string) => {
  const normalized = baseUrl.trim().replace(/\/+$/, "");
  return normalized.endsWith("/responses") ? normalized : `${normalized}/responses`;
};

export const chatCompletionsUrl = (baseUrl: string) => {
  const normalized = baseUrl.trim().replace(/\/+$/, "");
  return normalized.endsWith("/chat/completions")
    ? normalized
    : `${normalized}/chat/completions`;
};

const providerName = (baseUrl: string) =>
  baseUrl.includes("openrouter.ai")
    ? "OpenRouter"
    : baseUrl.includes("openai.com")
      ? "OpenAI"
      : "OpenAI-compatible";

const usesResponsesApi = (baseUrl: string) =>
  baseUrl.includes("openrouter.ai") || baseUrl.includes("openai.com");

const configuredProviders = (): LlmProviderConfig[] => {
  const primaryApiKey = process.env.OPENAI_API_KEY?.trim();
  const primaryBaseUrl =
    process.env.OPENAI_BASE_URL?.trim() || "https://api.openai.com/v1";
  const primaryModel = process.env.OPENAI_MODEL?.trim() || "gpt-5-mini";
  const fallbackApiKey = process.env.OPENAI_FALLBACK_API_KEY?.trim();
  const providers: LlmProviderConfig[] = [];

  if (primaryApiKey) {
    providers.push({
      route: "primary",
      apiKey: primaryApiKey,
      baseUrl: primaryBaseUrl,
      model: primaryModel,
    });
  }
  if (fallbackApiKey) {
    providers.push({
      route: "fallback",
      apiKey: fallbackApiKey,
      baseUrl:
        process.env.OPENAI_FALLBACK_BASE_URL?.trim() || primaryBaseUrl,
      model: process.env.OPENAI_FALLBACK_MODEL?.trim() || primaryModel,
    });
  }

  return providers;
};

export const extractResponseText = (response: OpenAIResponsesResult) => {
  const messageText = response.output
    ?.filter(
      (item) =>
        item.type === "message" ||
        item.role === "assistant" ||
        (!item.type && !item.role),
    )
    .flatMap((item) => item.content ?? [])
    .filter(
      (content) =>
        typeof content.text === "string" &&
        (!content.type || content.type === "output_text"),
    )
    .map((content) => content.text?.trim() ?? "")
    .filter(Boolean)
    .join("\n")
    .trim();

  if (messageText) return messageText;

  if (typeof response.output_text === "string" && response.output_text.trim()) {
    return response.output_text.trim();
  }

  const text = response.output
    ?.flatMap((item) => item.content ?? [])
    .filter((content) => content.type !== "reasoning_text")
    .map((content) => content.text ?? "")
    .join("\n")
    .trim();

  if (!text) {
    throw new Error("The LLM returned an empty research report.");
  }

  return text;
};

const parseJsonObjectCandidates = (text: string) => {
  const candidates: string[] = [];
  for (let start = text.indexOf("{"); start >= 0; start = text.indexOf("{", start + 1)) {
    let depth = 0;
    let inString = false;
    let escaped = false;

    for (let index = start; index < text.length; index += 1) {
      const character = text[index];
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (character === "\\") {
          escaped = true;
        } else if (character === '"') {
          inString = false;
        }
        continue;
      }

      if (character === '"') {
        inString = true;
      } else if (character === "{") {
        depth += 1;
      } else if (character === "}") {
        depth -= 1;
        if (depth === 0) {
          candidates.push(text.slice(start, index + 1));
          break;
        }
      }
    }
  }
  return candidates;
};

const parseJsonObject = <T>(
  text: string,
  isExpectedShape: (value: unknown) => value is T,
  errorMessage: string,
): T => {
  const normalizedText = text
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/, "")
    .trim();

  const candidates = [normalizedText, ...parseJsonObjectCandidates(normalizedText)];
  let lastError: unknown;
  for (const candidate of candidates) {
    try {
      const parsed: unknown = JSON.parse(candidate);
      if (isExpectedShape(parsed)) {
        return parsed;
      }
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error(errorMessage);
};

export const parseAiReport = (text: string): AiResearchReport => {
  const parsed = parseJsonObject<Partial<AiResearchReport>>(
    text,
    (value): value is Partial<AiResearchReport> =>
      Boolean(value) &&
      typeof value === "object" &&
      typeof (value as Partial<AiResearchReport>).summary === "string" &&
      Array.isArray((value as Partial<AiResearchReport>).bullPoints) &&
      Array.isArray((value as Partial<AiResearchReport>).bearPoints) &&
      Array.isArray((value as Partial<AiResearchReport>).thesisPoints) &&
      Array.isArray((value as Partial<AiResearchReport>).watchItems),
    "The LLM response did not contain a complete JSON research report.",
  );

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
    signalScore:
      typeof parsed.signalScore === "number" && Number.isFinite(parsed.signalScore)
        ? Math.min(100, Math.max(0, parsed.signalScore))
        : undefined,
    signalRationale:
      typeof parsed.signalRationale === "string"
        ? parsed.signalRationale.trim().slice(0, 240)
        : undefined,
  };
};

const cleanStringList = (value: unknown, maxItems: number, maxLength = 240) =>
  Array.isArray(value)
    ? value
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim().slice(0, maxLength))
        .filter(Boolean)
        .slice(0, maxItems)
    : [];

export const parseInvestmentThesis = (text: string): InvestmentThesis => {
  const parsed = parseJsonObject<Partial<InvestmentThesis>>(
    text,
    (value): value is Partial<InvestmentThesis> =>
      Boolean(value) &&
      typeof value === "object" &&
      typeof (value as Partial<InvestmentThesis>).summary === "string" &&
      Array.isArray((value as Partial<InvestmentThesis>).thesisPoints) &&
      Array.isArray((value as Partial<InvestmentThesis>).watchItems),
    "The LLM response did not contain a complete JSON investment thesis.",
  );
  const thesisPoints = cleanStringList(parsed.thesisPoints, 4);
  const watchItems = cleanStringList(parsed.watchItems, 4);
  const summary = parsed.summary?.trim().slice(0, 1_200) ?? "";
  if (!summary || thesisPoints.length !== 4 || watchItems.length !== 4) {
    throw new Error("The LLM returned an incomplete investment thesis.");
  }
  return { summary, thesisPoints, watchItems };
};

const allowedNoteTags = new Set([
  "AI Note",
  "News",
  "Financials",
  "Risk",
  "Follow-up",
  "Thesis",
]);

export const parseAiNotes = (text: string): AiNote[] => {
  const parsed = parseJsonObject<{ notes?: unknown }>(
    text,
    (value): value is { notes?: unknown } =>
      Boolean(value) && typeof value === "object" && Array.isArray((value as { notes?: unknown }).notes),
    "The LLM response did not contain JSON AI notes.",
  );
  const notes = (parsed.notes as unknown[])
    .map((note) => {
      const candidate = note as Partial<AiNote>;
      const tag = typeof candidate.tag === "string" ? candidate.tag.trim().slice(0, 40) : "";
      return {
        title: typeof candidate.title === "string" ? candidate.title.trim().slice(0, 120) : "",
        body: typeof candidate.body === "string" ? candidate.body.trim().slice(0, 520) : "",
        tag: allowedNoteTags.has(tag) ? tag : "AI Note",
      };
    })
    .filter((note) => note.title && note.body);
  const titles = new Set<string>();
  const uniqueNotes = notes.filter((note) => {
    const title = note.title.toLocaleLowerCase();
    if (titles.has(title)) return false;
    titles.add(title);
    return true;
  });
  if (uniqueNotes.length !== 5) {
    throw new Error("The LLM returned an incomplete AI notes set.");
  }
  return uniqueNotes;
};

const sanitizeProviderError = (value: string) =>
  value
    .replace(/Bearer\s+[^\s,"'}]+/gi, "Bearer [redacted]")
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, "[redacted]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 400);

const providerErrorDetail = async (response: Response) => {
  try {
    const raw = await response.text();
    if (!raw.trim()) return "";

    try {
      const parsed = JSON.parse(raw) as {
        error?: { message?: unknown; code?: unknown; type?: unknown } | string;
        detail?: unknown;
        message?: unknown;
      };
      const detail =
        typeof parsed.error === "string"
          ? parsed.error
          : typeof parsed.error?.message === "string"
            ? parsed.error.message
            : typeof parsed.detail === "string"
              ? parsed.detail
              : typeof parsed.message === "string"
                ? parsed.message
                : raw;
      return sanitizeProviderError(detail);
    } catch {
      return sanitizeProviderError(raw);
    }
  } catch {
    return "";
  }
};

const researchInstructions =
  "You are a skeptical equity research analyst. Use only the supplied data and never invent metrics, events, or certainty. Return valid JSON only with keys: summary, bullPoints, bearPoints, thesisPoints, watchItems, signalScore, signalRationale. The summary must be exactly 2 concise sentences that state the current setup and the central tension. Each list must contain exactly 3 concise, non-duplicative strings. Bull and bear points should cite a supplied fact or clearly label an inference. Thesis points should express testable drivers, not recommendations. Watch items must be measurable validation or invalidation signals and include a threshold, date, filing, or event when the supplied data supports one. signalScore must be a number from 0 (bearish) to 100 (bullish), with 50 neutral, for a six-month general research outlook; signalRationale must be one concise sentence grounded in supplied evidence. Explicitly say when important evidence is unavailable. Do not include markdown fences, personalized investment advice, price predictions, or hidden reasoning.";

const thesisInstructions =
  "You are an investment thesis assistant. Use only the supplied report and supporting data. Return valid JSON only with keys: summary, thesisPoints, watchItems. The summary should be 2-3 concise sentences. thesisPoints must contain exactly 4 concise, testable drivers or risks. watchItems must contain exactly 4 concise validation or invalidation signals. Do not include markdown fences or hidden reasoning.";

const notesInstructions =
  "You are an investing research chief-of-staff. Think carefully about the supplied company profile, latest news, existing notes, fresh AI report, fresh thesis, financial report, and snapshots. Return valid JSON only with key notes. notes must contain exactly 5 objects with title, body, tag. Make each note practical, specific, non-duplicative, and useful for an investor's next action. Prefer concrete follow-up checks, thesis validation questions, financial watchpoints, and risk triggers over generic summaries. Use tags only from: AI Note, News, Financials, Risk, Follow-up, Thesis. Do not include markdown fences or hidden reasoning.";

const requestStructuredResponse = async <T>(
  provider: LlmProviderConfig,
  instructions: string,
  promptPayload: unknown,
  parse: (text: string) => T,
) => {
  const useResponses = usesResponsesApi(provider.baseUrl);
  let response: Response;
  try {
    response = await fetch(
      useResponses ? responsesUrl(provider.baseUrl) : chatCompletionsUrl(provider.baseUrl),
      {
      method: "POST",
      headers: {
        Authorization: `Bearer ${provider.apiKey}`,
        "Content-Type": "application/json",
      },
      signal: AbortSignal.timeout(providerRequestTimeoutMs),
      body: JSON.stringify(
        useResponses
          ? {
              model: provider.model,
              input: [
                {
                  type: "message",
                  role: "system",
                  content: [{ type: "input_text", text: instructions }],
                },
                {
                  type: "message",
                  role: "user",
                  content: [{ type: "input_text", text: JSON.stringify(promptPayload) }],
                },
              ],
            }
          : {
              model: provider.model,
              messages: [
                { role: "system", content: instructions },
                { role: "user", content: JSON.stringify(promptPayload) },
              ],
              temperature: 0.25,
              max_tokens: 1_400,
            },
      ),
      },
    );
  } catch (error) {
    if (
      error instanceof Error &&
      (error.name === "TimeoutError" || error.name === "AbortError")
    ) {
      throw new Error(
        `${providerName(provider.baseUrl)} timed out after ${providerRequestTimeoutMs / 1_000} seconds.`,
      );
    }
    throw new Error(`${providerName(provider.baseUrl)} could not be reached.`);
  }

  if (!response.ok) {
    const detail = await providerErrorDetail(response);
    throw new Error(
      `${providerName(provider.baseUrl)} returned HTTP ${response.status}${
        detail ? `: ${detail}` : "."
      }`,
    );
  }

  if (useResponses) {
    const data = (await response.json()) as OpenAIResponsesResult;
    return parse(extractResponseText(data));
  }
  const data = (await response.json()) as OpenAIChatCompletionsResult;
  const text = data.choices?.[0]?.message?.content?.trim();
  if (!text) {
    throw new Error(`${providerName(provider.baseUrl)} returned an empty chat completion.`);
  }
  return parse(text);
};

const requestResearchReport = (provider: LlmProviderConfig, promptPayload: unknown) =>
  requestStructuredResponse(provider, researchInstructions, promptPayload, parseAiReport);

const requestInvestmentThesis = (provider: LlmProviderConfig, promptPayload: unknown) =>
  requestStructuredResponse(provider, thesisInstructions, promptPayload, parseInvestmentThesis);

const requestAiNotes = (provider: LlmProviderConfig, promptPayload: unknown) =>
  requestStructuredResponse(provider, notesInstructions, promptPayload, parseAiNotes);

const testProviderConnection = async (provider: LlmProviderConfig) => {
  try {
    const useResponses = usesResponsesApi(provider.baseUrl);
    const response = await fetch(
      useResponses ? responsesUrl(provider.baseUrl) : chatCompletionsUrl(provider.baseUrl),
      {
      method: "POST",
      headers: {
        Authorization: `Bearer ${provider.apiKey}`,
        "Content-Type": "application/json",
      },
      signal: AbortSignal.timeout(providerRequestTimeoutMs),
      body: JSON.stringify(
        useResponses
          ? {
              model: provider.model,
              input: "Reply with exactly OK.",
              max_output_tokens: 16,
            }
          : {
              model: provider.model,
              messages: [{ role: "user", content: "Reply with exactly OK." }],
              max_tokens: 16,
            },
      ),
      },
    );
    if (!response.ok) {
      const detail = await providerErrorDetail(response);
      return {
        ok: false,
        error: `HTTP ${response.status}${detail ? `: ${detail}` : ""}`,
      };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "Connection failed" };
  }
};

export const testProviders = internalAction({
  args: {},
  returns: v.array(
    v.object({
      route: v.union(v.literal("primary"), v.literal("fallback")),
      configured: v.boolean(),
      provider: v.string(),
      model: v.string(),
      ok: v.boolean(),
      error: v.optional(v.string()),
    }),
  ),
  handler: async () => {
    const providers = configuredProviders();
    const results = [];
    for (const route of ["primary", "fallback"] as const) {
      const provider = providers.find((item) => item.route === route);
      if (!provider) {
        results.push({
          route,
          configured: false,
          provider: "Not configured",
          model: "",
          ok: false,
          error: "No API key configured",
        });
        continue;
      }
      const result = await testProviderConnection(provider);
      results.push({
        route,
        configured: true,
        provider: providerName(provider.baseUrl),
        model: provider.model,
        ...result,
      });
    }
    return results;
  },
});

const providerLabel = (provider: LlmProviderConfig) =>
  `${providerName(provider.baseUrl)}${provider.route === "fallback" ? " (fallback)" : ""}`;

const requestWithFallback = async <T>(
  providers: LlmProviderConfig[],
  stage: string,
  request: (provider: LlmProviderConfig) => Promise<T>,
) => {
  const failures: string[] = [];
  for (const provider of providers) {
    try {
      return { value: await request(provider), provider };
    } catch (error) {
      failures.push(
        `${provider.route}: ${error instanceof Error ? error.message : "Provider failed."}`,
      );
    }
  }
  throw new Error(`${stage} generation failed. ${failures.join(" ")}`);
};

const workflowStageValidator = v.object({
  stage: v.union(v.literal("report"), v.literal("thesis"), v.literal("notes")),
  status: v.union(v.literal("completed"), v.literal("failed"), v.literal("skipped")),
  provider: v.optional(v.string()),
  model: v.optional(v.string()),
  generatedAt: v.optional(v.number()),
  createdNotes: v.optional(v.number()),
  replacedNotes: v.optional(v.number()),
  error: v.optional(v.string()),
});

type WorkflowStage = {
  stage: "report" | "thesis" | "notes";
  status: "completed" | "failed" | "skipped";
  provider?: string;
  model?: string;
  generatedAt?: number;
  createdNotes?: number;
  replacedNotes?: number;
  error?: string;
};

type WorkflowResult = {
  ticker: string;
  status: "complete" | "partial" | "failed";
  stages: WorkflowStage[];
};

export const generateReport = internalAction({
  args: { ticker: v.string() },
  returns: v.object({
    ticker: v.string(),
    status: v.union(v.literal("complete"), v.literal("partial"), v.literal("failed")),
    stages: v.array(workflowStageValidator),
  }),
  handler: async (ctx, args): Promise<WorkflowResult> => {
    const providers = configuredProviders();
    if (!providers.length) {
      throw new Error(
        "No LLM provider is configured. Add a primary or fallback API key in the local admin settings.",
      );
    }

    const ticker = normalizeTicker(args.ticker);
    const bundle = await ctx.runQuery(api.stocks.researchBundle, { ticker });
    if (!bundle.stock) {
      throw new Error(`No stock data found for ${ticker}. Sync the ticker first.`);
    }

    const researchContext = {
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
    const stages: WorkflowStage[] = [];

    let report: AiResearchReport;
    let reportProvider: LlmProviderConfig;
    try {
      const result = await requestWithFallback(providers, "LLM report", (provider) =>
        requestResearchReport(provider, researchContext),
      );
      report = result.value;
      reportProvider = result.provider;
    } catch (error) {
      stages.push({
        stage: "report",
        status: "failed",
        error: sanitizeProviderError(error instanceof Error ? error.message : "Report generation failed."),
      });
      stages.push({ stage: "thesis", status: "skipped" });
      stages.push({ stage: "notes", status: "skipped" });
      return { ticker, status: "failed", stages };
    }

    const reportGeneratedAt = Date.now();
    await ctx.runMutation(internal.stocks.upsertAiReport, {
      ticker,
      summary: report.summary,
      bullPoints: report.bullPoints,
      bearPoints: report.bearPoints,
      thesisPoints: report.thesisPoints,
      watchItems: report.watchItems,
      signalScore: report.signalScore,
      signalRationale: report.signalRationale,
      provider: providerLabel(reportProvider),
      model: reportProvider.model,
      generatedAt: reportGeneratedAt,
    });
    stages.push({
      stage: "report",
      status: "completed",
      provider: providerLabel(reportProvider),
      model: reportProvider.model,
      generatedAt: reportGeneratedAt,
    });

    let thesis: InvestmentThesis;
    let thesisProvider: LlmProviderConfig;
    try {
      const result = await requestWithFallback(providers, "Investment thesis", (provider) =>
        requestInvestmentThesis(provider, { ...researchContext, aiReport: report }),
      );
      thesis = result.value;
      thesisProvider = result.provider;
    } catch (error) {
      stages.push({
        stage: "thesis",
        status: "failed",
        error: sanitizeProviderError(error instanceof Error ? error.message : "Thesis generation failed."),
      });
      stages.push({ stage: "notes", status: "skipped" });
      return { ticker, status: "partial", stages };
    }

    const thesisGeneratedAt = Date.now();
    await ctx.runMutation(internal.stocks.saveInvestmentThesis, {
      ticker,
      summary: thesis.summary,
      thesisPoints: thesis.thesisPoints,
      watchItems: thesis.watchItems,
      source: providerLabel(thesisProvider),
      updatedAt: thesisGeneratedAt,
    });
    stages.push({
      stage: "thesis",
      status: "completed",
      provider: providerLabel(thesisProvider),
      model: thesisProvider.model,
      generatedAt: thesisGeneratedAt,
    });

    try {
      const result = await requestWithFallback(providers, "AI notes", (provider) =>
        requestAiNotes(provider, {
          ...researchContext,
          aiReport: report,
          investmentThesis: thesis,
          financialReport: bundle.financialReport,
          snapshots: bundle.snapshots?.slice(0, 5) ?? [],
        }),
      );
      const noteReplacement = await ctx.runMutation(internal.stocks.replaceAdminGeneratedNotes, {
        ticker,
        notes: result.value,
      });
      stages.push({
        stage: "notes",
        status: "completed",
        provider: providerLabel(result.provider),
        model: result.provider.model,
        generatedAt: Date.now(),
        createdNotes: noteReplacement.createdCount,
        replacedNotes: noteReplacement.replacedCount,
      });
      return { ticker, status: "complete", stages };
    } catch (error) {
      stages.push({
        stage: "notes",
        status: "failed",
        error: sanitizeProviderError(error instanceof Error ? error.message : "AI notes generation failed."),
      });
      return { ticker, status: "partial", stages };
    }
  },
});
