import { v } from "convex/values";
import { action } from "./_generated/server";
import { api, internal } from "./_generated/api";
import type { Doc } from "./_generated/dataModel";

declare const process: {
  env: Record<string, string | undefined>;
};

type FinnhubQuote = {
  c?: number;
  d?: number;
  dp?: number;
  pc?: number;
  t?: number;
};

type MarketQuote = {
  c: number;
  d: number;
  dp: number;
  pc?: number;
  t?: number;
};

type AlphaVantageDaily = {
  "Time Series (Daily)"?: Record<
    string,
    {
      "4. close"?: string;
    }
  >;
  Note?: string;
  "Error Message"?: string;
  Information?: string;
};

type AlphaVantageOverview = {
  Name?: string;
  Exchange?: string;
  Sector?: string;
  MarketCapitalization?: string;
  PERatio?: string;
  RevenueTTM?: string;
  EPS?: string;
  DividendYield?: string;
  ProfitMargin?: string;
  OperatingMarginTTM?: string;
  ReturnOnEquityTTM?: string;
  PriceToBookRatio?: string;
  EVToRevenue?: string;
  EVToEBITDA?: string;
  Beta?: string;
  AnalystTargetPrice?: string;
  FiscalYearEnd?: string;
  LatestQuarter?: string;
  Currency?: string;
  Note?: string;
  Information?: string;
  "Error Message"?: string;
};

type AlphaVantageStatementReport = {
  fiscalDateEnding?: string;
  totalRevenue?: string;
  grossProfit?: string;
  operatingIncome?: string;
  netIncome?: string;
  dilutedEPS?: string;
  operatingCashflow?: string;
  capitalExpenditures?: string;
  totalAssets?: string;
  totalLiabilities?: string;
  totalShareholderEquity?: string;
};

type AlphaVantageStatementResponse = {
  annualReports?: AlphaVantageStatementReport[];
  quarterlyReports?: AlphaVantageStatementReport[];
  Note?: string;
  Information?: string;
  "Error Message"?: string;
};

type FmpStatement = {
  date?: string;
  reportedCurrency?: string;
  calendarYear?: string;
  period?: string;
  revenue?: number;
  grossProfit?: number;
  operatingIncome?: number;
  netIncome?: number;
  epsdiluted?: number;
  epsDiluted?: number;
  operatingCashFlow?: number;
  operatingCashflow?: number;
  capitalExpenditure?: number;
  capitalExpenditures?: number;
  freeCashFlow?: number;
  totalAssets?: number;
  totalLiabilities?: number;
  totalStockholdersEquity?: number;
  totalShareholderEquity?: number;
};

type FmpRatio = {
  netProfitMarginTTM?: number;
  operatingProfitMarginTTM?: number;
  returnOnEquityTTM?: number;
  priceToBookRatioTTM?: number;
};

type FmpKeyMetric = {
  evToSalesTTM?: number;
  evToRevenueTTM?: number;
  enterpriseValueMultipleTTM?: number;
};

type SecTickerEntry = {
  cik_str: number;
  ticker: string;
  title: string;
};

type SecFact = {
  start?: string;
  end: string;
  val: number;
  accn: string;
  fy?: number;
  fp?: string;
  form: string;
  filed: string;
  frame?: string;
};

type SecCompanyFacts = {
  cik: number;
  entityName: string;
  facts: Record<
    string,
    Record<string, { units: Record<string, SecFact[]> }>
  >;
};

type TwelveDataTimeSeries = {
  values?: Array<{
    close?: string;
  }>;
  status?: string;
  code?: number;
  message?: string;
};

type TwelveDataQuote = {
  close?: string;
  previous_close?: string;
  change?: string;
  percent_change?: string;
  timestamp?: number;
};

type FinnhubProfile = {
  name?: string;
  ticker?: string;
  exchange?: string;
  finnhubIndustry?: string;
  logo?: string;
  marketCapitalization?: number;
};

type FinnhubNewsItem = {
  headline?: string;
  source?: string;
  url?: string;
  datetime?: number;
};

type FinnhubSymbolSearch = {
  count?: number;
  result?: Array<{
    description?: string;
    displaySymbol?: string;
    symbol?: string;
    type?: string;
  }>;
};

const finnhubBaseUrl = "https://finnhub.io/api/v1";

type DataSourceLogger = (event: {
  service: string;
  operation: string;
  status: "success" | "error" | "fallback";
  provider: string;
  fallbackProvider?: string;
  ticker?: string;
  message?: string;
  requestUrl?: string;
  requestedAt?: number;
}) => Promise<void>;

type AlphaVantageKeyLabel =
  | "Alpha Vantage Primary"
  | "Alpha Vantage Secondary"
  | "Alpha Vantage Tertiary";

type AlphaVantageKeySlot = {
  apiKey: string;
  label: AlphaVantageKeyLabel;
  count: number;
  lastMessage?: string;
  lastRequestedAt?: number;
  lastCalledAt?: number;
  nextAllowedAt: number;
};

const alphaVantageDailyFreeLimit = 25;
const alphaVantagePerKeySpacingMs = 60_000;
const alphaVantageGlobalSpacingMs = 5_000;

const alphaVantagePrimaryLabel: AlphaVantageKeyLabel = "Alpha Vantage Primary";
const alphaVantageSecondaryLabel: AlphaVantageKeyLabel = "Alpha Vantage Secondary";
const alphaVantageTertiaryLabel: AlphaVantageKeyLabel = "Alpha Vantage Tertiary";
const alphaVantageKeyPriority: Record<AlphaVantageKeyLabel, number> = {
  [alphaVantagePrimaryLabel]: 0,
  [alphaVantageSecondaryLabel]: 1,
  [alphaVantageTertiaryLabel]: 2,
};

class AlphaVantageDailyLimitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AlphaVantageDailyLimitError";
  }
}

const isAlphaVantageDailyLimitMessage = (message?: string) =>
  Boolean(
    message &&
      (message.includes("standard API rate limit is 25 requests per day") ||
        message.includes("daily rate limits") ||
        message.includes("25 requests per day"))
  );

const toAlphaVantageError = (message: string) =>
  isAlphaVantageDailyLimitMessage(message)
    ? new AlphaVantageDailyLimitError(message)
    : new Error(message);

const redactApiUrl = (url: URL) => {
  const redacted = new URL(url.toString());
  for (const key of ["apikey", "token"]) {
    if (redacted.searchParams.has(key)) {
      const value = redacted.searchParams.get(key) ?? "";
      redacted.searchParams.set(
        key,
        value.length > 4 ? `redacted-${value.slice(-4)}` : "redacted"
      );
    }
  }
  return redacted.toString();
};

const orderAlphaVantageKeysByUsage = (
  primaryApiKey: string | undefined,
  secondaryApiKey: string | undefined,
  tertiaryApiKey: string | undefined,
  usageByService: Map<
    string,
    {
      count?: number;
      lastMessage?: string;
      lastRequestedAt?: number;
      lastCalledAt?: number;
    } | null
  >
) => {
  const slots: AlphaVantageKeySlot[] = [];
  const seenKeys = new Set<string>();

  const addSlot = (apiKey: string | undefined, label: AlphaVantageKeyLabel) => {
    if (!apiKey || seenKeys.has(apiKey)) {
      return;
    }
    seenKeys.add(apiKey);
    const usage = usageByService.get(label);
    const lastUsedAt = usage?.lastRequestedAt ?? usage?.lastCalledAt;
    slots.push({
      apiKey,
      label,
      count: usage?.count ?? 0,
      lastMessage: usage?.lastMessage,
      lastRequestedAt: usage?.lastRequestedAt,
      lastCalledAt: usage?.lastCalledAt,
      nextAllowedAt: lastUsedAt ? lastUsedAt + alphaVantagePerKeySpacingMs : 0,
    });
  };

  addSlot(primaryApiKey, alphaVantagePrimaryLabel);
  addSlot(secondaryApiKey, alphaVantageSecondaryLabel);
  addSlot(tertiaryApiKey, alphaVantageTertiaryLabel);

  return slots.sort((left, right) => {
    const leftLimited =
      left.count >= alphaVantageDailyFreeLimit ||
      isAlphaVantageDailyLimitMessage(left.lastMessage);
    const rightLimited =
      right.count >= alphaVantageDailyFreeLimit ||
      isAlphaVantageDailyLimitMessage(right.lastMessage);

    if (leftLimited !== rightLimited) {
      return leftLimited ? 1 : -1;
    }

    if (left.nextAllowedAt !== right.nextAllowedAt) {
      return left.nextAllowedAt - right.nextAllowedAt;
    }

    if (left.count !== right.count) {
      return left.count - right.count;
    }

    return alphaVantageKeyPriority[left.label] - alphaVantageKeyPriority[right.label];
  });
};

const normalizeTicker = (ticker: string) => ticker.trim().toUpperCase();

const formatMarketCap = (marketCapInMillions?: number) => {
  if (!marketCapInMillions || marketCapInMillions <= 0) {
    return "N/A";
  }

  const dollars = marketCapInMillions * 1_000_000;
  if (dollars >= 1_000_000_000_000) {
    return `${(dollars / 1_000_000_000_000).toFixed(2)}T`;
  }

  if (dollars >= 1_000_000_000) {
    return `${(dollars / 1_000_000_000).toFixed(2)}B`;
  }

  return `${(dollars / 1_000_000).toFixed(2)}M`;
};

const formatLargeDollarValue = (rawValue?: string) => {
  if (!rawValue || rawValue === "None") {
    return "N/A";
  }

  const numeric = Number(rawValue);
  if (!Number.isFinite(numeric)) {
    return "N/A";
  }

  const absolute = Math.abs(numeric);
  const prefix = numeric < 0 ? "-" : "";

  if (absolute >= 1_000_000_000_000) {
    return `${prefix}${(absolute / 1_000_000_000_000).toFixed(2)}T`;
  }

  if (absolute >= 1_000_000_000) {
    return `${prefix}${(absolute / 1_000_000_000).toFixed(2)}B`;
  }

  if (absolute >= 1_000_000) {
    return `${prefix}${(absolute / 1_000_000).toFixed(2)}M`;
  }

  return `${prefix}${absolute.toFixed(2)}`;
};

const formatRatio = (rawValue?: string) => {
  if (!rawValue || rawValue === "None") {
    return "N/A";
  }

  const numeric = Number(rawValue);
  return Number.isFinite(numeric) ? numeric.toFixed(2) : "N/A";
};

const formatPercentValue = (rawValue?: string) => {
  if (!rawValue || rawValue === "None") {
    return "N/A";
  }

  const numeric = Number(rawValue);
  if (!Number.isFinite(numeric)) {
    return "N/A";
  }

  const normalized = numeric <= 1 ? numeric * 100 : numeric;
  return `${normalized.toFixed(2)}%`;
};

const formatCurrencyValue = (rawValue?: string) => {
  if (!rawValue || rawValue === "None") {
    return "N/A";
  }

  const numeric = Number(rawValue);
  return Number.isFinite(numeric) ? `$${numeric.toFixed(2)}` : "N/A";
};

const formatSignedPercent = (value: number) =>
  `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;

const positiveHeadlinePattern =
  /(growth|beat|beats|surge|strong|upgrade|raises|record|expands|wins|rally|demand)/i;
const riskHeadlinePattern =
  /(risk|antitrust|probe|lawsuit|restriction|delay|cut|miss|competition|warning|down|fall)/i;
const companyNewsAliases: Record<string, string[]> = {
  AAPL: ["apple", "iphone", "ipad", "mac", "app store"],
  AMZN: ["amazon", "aws", "prime"],
  GOOGL: ["google", "alphabet", "youtube", "gemini"],
  META: ["meta", "facebook", "instagram", "whatsapp"],
  MSFT: ["microsoft", "azure", "windows", "copilot"],
  NVDA: ["nvidia", "geforce", "cuda", "blackwell"],
  ORCL: ["oracle", "oci"],
  PLTR: ["palantir"],
  TSLA: ["tesla", "cybertruck"],
};
const genericCompanyTokens = new Set([
  "company",
  "corporation",
  "corp",
  "inc",
  "incorporated",
  "limited",
  "ltd",
  "plc",
  "group",
  "holdings",
  "technology",
  "technologies",
]);
const normalizeNewsText = (value: string) =>
  value
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9$]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
const containsNewsTerm = (normalizedHeadline: string, term: string) =>
  ` ${normalizedHeadline} `.includes(` ${normalizeNewsText(term)} `);
const qualifyCompanyNews = (input: {
  ticker: string;
  companyName: string;
  news: FinnhubNewsItem[];
}) => {
  const normalizedCompanyName = normalizeNewsText(input.companyName);
  const companyTokens = normalizedCompanyName
    .split(" ")
    .filter((token) => token.length >= 4 && !genericCompanyTokens.has(token));
  const aliases = Array.from(
    new Set([
      normalizedCompanyName,
      ...companyTokens,
      ...(companyNewsAliases[input.ticker] ?? []),
    ])
  ).filter(Boolean);
  const seen = new Set<string>();
  const qualified = input.news
    .filter((item): item is FinnhubNewsItem & { headline: string } =>
      Boolean(item.headline?.trim())
    )
    .map((item) => {
      const normalizedHeadline = normalizeNewsText(item.headline);
      let relevanceScore = 0;
      if (
        input.ticker.length > 1 &&
        containsNewsTerm(normalizedHeadline, input.ticker)
      ) {
        relevanceScore += 100;
      }
      if (
        normalizedCompanyName.length >= 4 &&
        containsNewsTerm(normalizedHeadline, normalizedCompanyName)
      ) {
        relevanceScore += 90;
      }
      const matchingAliases = aliases.filter((alias) =>
        containsNewsTerm(normalizedHeadline, alias)
      );
      relevanceScore += Math.min(matchingAliases.length, 2) * 65;
      return { item, normalizedHeadline, relevanceScore };
    })
    .filter(({ normalizedHeadline, relevanceScore }) => {
      if (relevanceScore < 60 || seen.has(normalizedHeadline)) return false;
      seen.add(normalizedHeadline);
      return true;
    })
    .sort(
      (left, right) =>
        (right.item.datetime ?? 0) - (left.item.datetime ?? 0) ||
        right.relevanceScore - left.relevanceScore
    );
  const accepted = qualified.slice(0, 5).map(({ item }) => item);

  return {
    accepted,
    filteredCount: Math.max(0, input.news.length - qualified.length),
  };
};
const sleep = (durationMs: number) =>
  new Promise((resolve) => setTimeout(resolve, durationMs));

let alphaVantageGlobalNextAllowedAt = 0;

const chooseAlphaVantageKey = (keySlots: AlphaVantageKeySlot[]) =>
  keySlots
    .filter(
      (slot) =>
        slot.count < alphaVantageDailyFreeLimit &&
        !isAlphaVantageDailyLimitMessage(slot.lastMessage)
    )
    .sort((left, right) => {
      if (left.nextAllowedAt !== right.nextAllowedAt) {
        return left.nextAllowedAt - right.nextAllowedAt;
      }
      if (left.count !== right.count) {
        return left.count - right.count;
      }
      return alphaVantageKeyPriority[left.label] - alphaVantageKeyPriority[right.label];
    })[0];

const waitForAlphaVantageWindow = async (keySlot: AlphaVantageKeySlot) => {
  const waitMs = Math.max(
    alphaVantageGlobalNextAllowedAt - Date.now(),
    keySlot.nextAllowedAt - Date.now(),
    0
  );
  if (waitMs > 0) {
    await sleep(waitMs);
  }

  const requestedAt = Date.now();
  alphaVantageGlobalNextAllowedAt = requestedAt + alphaVantageGlobalSpacingMs;
  keySlot.lastRequestedAt = requestedAt;
  keySlot.lastCalledAt = requestedAt;
  keySlot.nextAllowedAt = requestedAt + alphaVantagePerKeySpacingMs;
  keySlot.count += 1;
  return requestedAt;
};

const isoDate = (offsetDays: number) => {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + offsetDays);
  return date.toISOString().slice(0, 10);
};

const fetchFinnhub = async <T>(
  path: string,
  params: Record<string, string>,
  apiKey: string,
  logEvent?: DataSourceLogger
) => {
  const url = new URL(`${finnhubBaseUrl}${path}`);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  url.searchParams.set("token", apiKey);

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Finnhub ${path} failed with ${response.status}`);
    }

    await logEvent?.({
      service: "Finnhub",
      operation: path,
      status: "success",
      provider: "Finnhub",
      ticker: params.symbol,
    });

    return (await response.json()) as T;
  } catch (error) {
    await logEvent?.({
      service: "Finnhub",
      operation: path,
      status: "error",
      provider: "Finnhub",
      ticker: params.symbol,
      message: error instanceof Error ? error.message : "Finnhub request failed.",
    });
    throw error;
  }
};

const fetchAlphaVantageDaily = async (
  symbol: string,
  keySlot: AlphaVantageKeySlot,
  logEvent?: DataSourceLogger
) => {
  const requestedAt = await waitForAlphaVantageWindow(keySlot);

  const url = new URL("https://www.alphavantage.co/query");
  url.searchParams.set("function", "TIME_SERIES_DAILY");
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("outputsize", "full");
  url.searchParams.set("apikey", keySlot.apiKey);
  const requestUrl = redactApiUrl(url);

  let data: AlphaVantageDaily;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Alpha Vantage daily history failed with ${response.status}`);
    }

    data = (await response.json()) as AlphaVantageDaily;
    if (data["Error Message"]) {
      throw new Error(data["Error Message"]);
    }

    if (data.Note || data.Information) {
      throw toAlphaVantageError(
        data.Note || data.Information || "Alpha Vantage is unavailable."
      );
    }

    await logEvent?.({
      service: keySlot.label,
      operation: "TIME_SERIES_DAILY",
      status: "success",
      provider: "Alpha Vantage",
      ticker: symbol,
      requestUrl,
      requestedAt,
    });
  } catch (error) {
    await logEvent?.({
      service: keySlot.label,
      operation: "TIME_SERIES_DAILY",
      status: "error",
      provider: "Alpha Vantage",
      ticker: symbol,
      message: error instanceof Error ? error.message : "Alpha Vantage daily history failed.",
      requestUrl,
      requestedAt,
    });
    throw error;
  }

  const entries = Object.entries(data["Time Series (Daily)"] ?? {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, item]) => Number(item["4. close"]))
    .filter((point) => Number.isFinite(point));

  return entries.slice(-365);
};

const fetchAlphaVantageJson = async <T>(
  symbol: string,
  functionName: string,
  keySlot: AlphaVantageKeySlot,
  logEvent?: DataSourceLogger
) => {
  const requestedAt = await waitForAlphaVantageWindow(keySlot);

  const url = new URL("https://www.alphavantage.co/query");
  url.searchParams.set("function", functionName);
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("apikey", keySlot.apiKey);
  const requestUrl = redactApiUrl(url);

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Alpha Vantage ${functionName} failed with ${response.status}`);
    }

    const data = (await response.json()) as T & {
      Note?: string;
      Information?: string;
      "Error Message"?: string;
    };

    if (data["Error Message"]) {
      throw new Error(data["Error Message"]);
    }

    if (data.Note || data.Information) {
      const message = data.Note || data.Information || "Alpha Vantage is unavailable.";
      if (message.includes("1 request per second")) {
        alphaVantageGlobalNextAllowedAt = Math.max(
          alphaVantageGlobalNextAllowedAt,
          Date.now() + alphaVantageGlobalSpacingMs
        );
      }
      throw toAlphaVantageError(message);
    }

    await logEvent?.({
      service: keySlot.label,
      operation: functionName,
      status: "success",
      provider: "Alpha Vantage",
      ticker: symbol,
      requestUrl,
      requestedAt,
    });

    return data;
  } catch (error) {
    await logEvent?.({
      service: keySlot.label,
      operation: functionName,
      status: "error",
      provider: "Alpha Vantage",
      ticker: symbol,
      message: error instanceof Error ? error.message : `Alpha Vantage ${functionName} failed.`,
      requestUrl,
      requestedAt,
    });
    throw error;
  }
};

const fetchAlphaVantageJsonWithRetry = async <T>(
  symbol: string,
  functionName: string,
  keySlot: AlphaVantageKeySlot,
  logEvent?: DataSourceLogger,
  attempts = 3
) => {
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await fetchAlphaVantageJson<T>(
        symbol,
        functionName,
        keySlot,
        logEvent
      );
    } catch (error) {
      lastError = error;
      if (error instanceof AlphaVantageDailyLimitError) {
        throw error;
      }
      if (attempt < attempts - 1) {
        await sleep(6_000);
      }
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error(`Alpha Vantage ${functionName} failed.`);
};

const fetchAlphaVantageJsonWithRotation = async <T>(
  symbol: string,
  functionName: string,
  keySlots: AlphaVantageKeySlot[],
  logEvent?: DataSourceLogger
) => {
  let lastError: unknown;
  let previousKeySlot: AlphaVantageKeySlot | undefined;

  for (let attempt = 0; attempt < keySlots.length; attempt += 1) {
    const keySlot = chooseAlphaVantageKey(keySlots);
    if (!keySlot) {
      break;
    }

    try {
      if (previousKeySlot) {
        await logEvent?.({
          service: keySlot.label,
          operation: `${functionName}_rotation`,
          status: "fallback",
          provider: previousKeySlot.label,
          fallbackProvider: keySlot.label,
          ticker: symbol,
          message: `${previousKeySlot.label} reached the daily Alpha Vantage limit; trying ${keySlot.label}.`,
        });
      }

      const data = await fetchAlphaVantageJsonWithRetry<T>(
        symbol,
        functionName,
        keySlot,
        logEvent
      );

      return {
        data,
        usedSecondaryKey: keySlot.label !== alphaVantagePrimaryLabel,
      };
    } catch (error) {
      lastError = error;
      previousKeySlot = keySlot;
      if (error instanceof AlphaVantageDailyLimitError) {
        keySlot.lastMessage = error.message;
        keySlot.count = alphaVantageDailyFreeLimit;
      } else {
        throw error;
      }
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error(`Unable to load ${functionName} from Alpha Vantage.`);
};

const fetchTwelveDataDaily = async (
  symbol: string,
  apiKey: string,
  logEvent?: DataSourceLogger
) => {
  const url = new URL("https://api.twelvedata.com/time_series");
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("interval", "1day");
  url.searchParams.set("outputsize", "365");
  url.searchParams.set("apikey", apiKey);

  let data: TwelveDataTimeSeries;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Twelve Data daily history failed with ${response.status}`);
    }

    data = (await response.json()) as TwelveDataTimeSeries;
    if (data.status === "error" || data.code || data.message) {
      throw new Error(data.message || "Twelve Data is unavailable.");
    }

    await logEvent?.({
      service: "Twelve Data",
      operation: "time_series",
      status: "success",
      provider: "Twelve Data",
      ticker: symbol,
    });
  } catch (error) {
    await logEvent?.({
      service: "Twelve Data",
      operation: "time_series",
      status: "error",
      provider: "Twelve Data",
      ticker: symbol,
      message: error instanceof Error ? error.message : "Twelve Data time series failed.",
    });
    throw error;
  }

  const entries = (data.values ?? [])
    .slice()
    .reverse()
    .map((item) => Number(item.close))
    .filter((point) => Number.isFinite(point));

  return entries.slice(-365);
};

const fetchTwelveDataQuote = async (
  symbol: string,
  apiKey: string,
  logEvent?: DataSourceLogger
) => {
  const url = new URL("https://api.twelvedata.com/quote");
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("apikey", apiKey);

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Twelve Data quote failed with ${response.status}`);
    }

    const data = (await response.json()) as TwelveDataQuote & {
      status?: string;
      code?: number;
      message?: string;
    };

    if (data.status === "error" || data.code || data.message) {
      throw new Error(data.message || "Twelve Data quote is unavailable.");
    }

    await logEvent?.({
      service: "Twelve Data",
      operation: "quote",
      status: "success",
      provider: "Twelve Data",
      ticker: symbol,
    });

    return data;
  } catch (error) {
    await logEvent?.({
      service: "Twelve Data",
      operation: "quote",
      status: "error",
      provider: "Twelve Data",
      ticker: symbol,
      message: error instanceof Error ? error.message : "Twelve Data quote failed.",
    });
    throw error;
  }
};

const fetchQuoteWithFallback = async (
  symbol: string,
  finnhubApiKey: string,
  twelveDataApiKey?: string,
  logEvent?: DataSourceLogger
): Promise<MarketQuote> => {
  try {
    const quote = await fetchFinnhub<FinnhubQuote>("/quote", { symbol }, finnhubApiKey, logEvent);
    if (quote.c && quote.c > 0) {
      return {
        c: quote.c,
        d: quote.d ?? quote.c - (quote.pc ?? quote.c),
        dp:
          quote.dp ?? (quote.pc ? ((quote.c - quote.pc) / quote.pc) * 100 : 0),
        pc: quote.pc,
        t: quote.t,
      };
    }
  } catch {
    // Fall through to Twelve Data.
  }

  if (!twelveDataApiKey) {
    throw new Error(`Unable to fetch a valid quote for ${symbol}.`);
  }

  await logEvent?.({
    service: "Quote Fallback",
    operation: "quote",
    status: "fallback",
    provider: "Finnhub",
    fallbackProvider: "Twelve Data",
    ticker: symbol,
    message: "Finnhub quote was unavailable; using Twelve Data.",
  });
  const twelveDataQuote = await fetchTwelveDataQuote(symbol, twelveDataApiKey, logEvent);
  const close = Number(twelveDataQuote.close);
  const previousClose = Number(twelveDataQuote.previous_close);
  const change = Number(twelveDataQuote.change);
  const changePercent = Number(twelveDataQuote.percent_change);

  if (!Number.isFinite(close) || close <= 0) {
    throw new Error(`Twelve Data did not return a valid quote for ${symbol}.`);
  }

  return {
    c: close,
    d: Number.isFinite(change) ? change : close - previousClose,
    dp:
      Number.isFinite(changePercent) ? changePercent : previousClose
        ? ((close - previousClose) / previousClose) * 100
        : 0,
    pc: Number.isFinite(previousClose) ? previousClose : undefined,
    t: twelveDataQuote.timestamp,
  } satisfies FinnhubQuote;
};

const fetchChartHistory = async (
  symbol: string,
  alphaVantageKeySlots: AlphaVantageKeySlot[],
  twelveDataApiKey?: string,
  logEvent?: DataSourceLogger
) => {
  let lastAlphaVantageKeySlot: AlphaVantageKeySlot | undefined;
  for (let attempt = 0; attempt < alphaVantageKeySlots.length; attempt += 1) {
    const alphaVantageKeySlot = chooseAlphaVantageKey(alphaVantageKeySlots);
    if (!alphaVantageKeySlot) {
      break;
    }
    lastAlphaVantageKeySlot = alphaVantageKeySlot;
    try {
      const alphaVantageHistory = await fetchAlphaVantageDaily(
        symbol,
        alphaVantageKeySlot,
        logEvent
      );
      if (alphaVantageHistory.length) {
        return alphaVantageHistory;
      }
    } catch (error) {
      if (error instanceof AlphaVantageDailyLimitError) {
        alphaVantageKeySlot.lastMessage = error.message;
        alphaVantageKeySlot.count = alphaVantageDailyFreeLimit;
      } else {
        break;
      }
    }
  }

  if (twelveDataApiKey) {
    try {
      await logEvent?.({
        service: "Chart Fallback",
        operation: "time_series",
        status: "fallback",
        provider: lastAlphaVantageKeySlot?.label ?? "Primary chart provider",
        fallbackProvider: "Twelve Data",
        ticker: symbol,
        message: lastAlphaVantageKeySlot
          ? `${lastAlphaVantageKeySlot.label} chart history unavailable; trying Twelve Data.`
          : "Using Twelve Data as the configured chart provider.",
      });
      const twelveDataHistory = await fetchTwelveDataDaily(symbol, twelveDataApiKey, logEvent);
      if (twelveDataHistory.length) {
        return twelveDataHistory;
      }
    } catch {
      // Ignore fallback provider errors and return undefined below.
    }
  }

  return undefined;
};

const toFinancialPeriod = (
  incomeStatement?: AlphaVantageStatementReport,
  balanceSheet?: AlphaVantageStatementReport,
  cashFlow?: AlphaVantageStatementReport,
  currency = "USD"
) => {
  const operatingCashflow = cashFlow?.operatingCashflow;
  const capitalExpenditures = cashFlow?.capitalExpenditures;
  const freeCashFlowValue =
    Number(operatingCashflow) - Math.abs(Number(capitalExpenditures));

  return {
    fiscalDateEnding:
      incomeStatement?.fiscalDateEnding ||
      balanceSheet?.fiscalDateEnding ||
      cashFlow?.fiscalDateEnding ||
      "N/A",
    currency,
    normalized: normalizedFinancialValues({
      totalRevenue: finiteNumber(incomeStatement?.totalRevenue),
      grossProfit: finiteNumber(incomeStatement?.grossProfit),
      operatingIncome: finiteNumber(incomeStatement?.operatingIncome),
      netIncome: finiteNumber(incomeStatement?.netIncome),
      dilutedEps: finiteNumber(incomeStatement?.dilutedEPS),
      operatingCashflow: finiteNumber(operatingCashflow),
      capitalExpenditures: finiteNumber(capitalExpenditures),
      freeCashFlow: Number.isFinite(freeCashFlowValue) ? freeCashFlowValue : undefined,
      totalAssets: finiteNumber(balanceSheet?.totalAssets),
      totalLiabilities: finiteNumber(balanceSheet?.totalLiabilities),
      totalShareholderEquity: finiteNumber(balanceSheet?.totalShareholderEquity),
    }),
    totalRevenue: formatLargeDollarValue(incomeStatement?.totalRevenue),
    grossProfit: formatLargeDollarValue(incomeStatement?.grossProfit),
    operatingIncome: formatLargeDollarValue(incomeStatement?.operatingIncome),
    netIncome: formatLargeDollarValue(incomeStatement?.netIncome),
    dilutedEps: formatRatio(incomeStatement?.dilutedEPS),
    operatingCashflow: formatLargeDollarValue(operatingCashflow),
    capitalExpenditures: formatLargeDollarValue(capitalExpenditures),
    freeCashFlow: Number.isFinite(freeCashFlowValue)
      ? formatLargeDollarValue(String(freeCashFlowValue))
      : "N/A",
    totalAssets: formatLargeDollarValue(balanceSheet?.totalAssets),
    totalLiabilities: formatLargeDollarValue(balanceSheet?.totalLiabilities),
    totalShareholderEquity: formatLargeDollarValue(
      balanceSheet?.totalShareholderEquity
    ),
  };
};

const fmpValue = (value?: number | string) =>
  value === undefined || value === null ? undefined : String(value);

type NumericFinancialValues = {
  totalRevenue?: number;
  grossProfit?: number;
  operatingIncome?: number;
  netIncome?: number;
  dilutedEps?: number;
  operatingCashflow?: number;
  capitalExpenditures?: number;
  freeCashFlow?: number;
  totalAssets?: number;
  totalLiabilities?: number;
  totalShareholderEquity?: number;
};

const finiteNumber = (value?: number | string) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const normalizedFinancialValues = (values: NumericFinancialValues) =>
  Object.fromEntries(
    Object.entries(values).filter((entry): entry is [string, number] =>
      Number.isFinite(entry[1])
    )
  ) as NumericFinancialValues;

const byFiscalDate = <T extends { fiscalDateEnding?: string }>(items: T[]) =>
  new Map(
    items
      .filter((item) => Boolean(item.fiscalDateEnding))
      .map((item) => [item.fiscalDateEnding as string, item])
  );

const byFmpDate = <T extends { date?: string }>(items: T[]) =>
  new Map(
    items.filter((item) => Boolean(item.date)).map((item) => [item.date as string, item])
  );

const toFmpFinancialPeriod = (
  incomeStatement?: FmpStatement,
  balanceSheet?: FmpStatement,
  cashFlow?: FmpStatement
) => {
  const operatingCashflow = cashFlow?.operatingCashFlow ?? cashFlow?.operatingCashflow;
  const capitalExpenditures =
    cashFlow?.capitalExpenditure ?? cashFlow?.capitalExpenditures;
  const freeCashFlowValue =
    cashFlow?.freeCashFlow ??
    Number(operatingCashflow) - Math.abs(Number(capitalExpenditures));

  return {
    fiscalDateEnding:
      incomeStatement?.date || balanceSheet?.date || cashFlow?.date || "N/A",
    currency: incomeStatement?.reportedCurrency || "USD",
    normalized: normalizedFinancialValues({
      totalRevenue: finiteNumber(incomeStatement?.revenue),
      grossProfit: finiteNumber(incomeStatement?.grossProfit),
      operatingIncome: finiteNumber(incomeStatement?.operatingIncome),
      netIncome: finiteNumber(incomeStatement?.netIncome),
      dilutedEps: finiteNumber(incomeStatement?.epsdiluted ?? incomeStatement?.epsDiluted),
      operatingCashflow: finiteNumber(operatingCashflow),
      capitalExpenditures: finiteNumber(capitalExpenditures),
      freeCashFlow: Number.isFinite(freeCashFlowValue) ? freeCashFlowValue : undefined,
      totalAssets: finiteNumber(balanceSheet?.totalAssets),
      totalLiabilities: finiteNumber(balanceSheet?.totalLiabilities),
      totalShareholderEquity: finiteNumber(
        balanceSheet?.totalStockholdersEquity ?? balanceSheet?.totalShareholderEquity
      ),
    }),
    totalRevenue: formatLargeDollarValue(fmpValue(incomeStatement?.revenue)),
    grossProfit: formatLargeDollarValue(fmpValue(incomeStatement?.grossProfit)),
    operatingIncome: formatLargeDollarValue(fmpValue(incomeStatement?.operatingIncome)),
    netIncome: formatLargeDollarValue(fmpValue(incomeStatement?.netIncome)),
    dilutedEps: formatRatio(fmpValue(incomeStatement?.epsdiluted ?? incomeStatement?.epsDiluted)),
    operatingCashflow: formatLargeDollarValue(fmpValue(operatingCashflow)),
    capitalExpenditures: formatLargeDollarValue(fmpValue(capitalExpenditures)),
    freeCashFlow: Number.isFinite(freeCashFlowValue)
      ? formatLargeDollarValue(String(freeCashFlowValue))
      : "N/A",
    totalAssets: formatLargeDollarValue(fmpValue(balanceSheet?.totalAssets)),
    totalLiabilities: formatLargeDollarValue(fmpValue(balanceSheet?.totalLiabilities)),
    totalShareholderEquity: formatLargeDollarValue(
      fmpValue(balanceSheet?.totalStockholdersEquity ?? balanceSheet?.totalShareholderEquity)
    ),
  };
};

const buildFmpFinancialReport = (
  incomeStatement: FmpStatement[],
  balanceSheet: FmpStatement[],
  cashFlow: FmpStatement[],
  ratios: FmpRatio[] = [],
  keyMetrics: FmpKeyMetric[] = []
) => {
  const quarterlyIncome = incomeStatement.filter((item) => item.period !== "FY").slice(0, 4);
  const annualIncome = incomeStatement.filter((item) => item.period === "FY").slice(0, 4);
  const quarterlyBalance = balanceSheet.filter((item) => item.period !== "FY");
  const annualBalance = balanceSheet.filter((item) => item.period === "FY");
  const quarterlyCash = cashFlow.filter((item) => item.period !== "FY");
  const annualCash = cashFlow.filter((item) => item.period === "FY");
  const quarterlyBalanceByDate = byFmpDate(quarterlyBalance);
  const annualBalanceByDate = byFmpDate(annualBalance);
  const quarterlyCashByDate = byFmpDate(quarterlyCash);
  const annualCashByDate = byFmpDate(annualCash);

  const quarterly = quarterlyIncome.map((item) =>
    toFmpFinancialPeriod(
      item,
      item.date ? quarterlyBalanceByDate.get(item.date) : undefined,
      item.date ? quarterlyCashByDate.get(item.date) : undefined
    )
  );
  const annual = annualIncome.map((item) =>
    toFmpFinancialPeriod(
      item,
      item.date ? annualBalanceByDate.get(item.date) : undefined,
      item.date ? annualCashByDate.get(item.date) : undefined
    )
  );

  if (!quarterly.length && !annual.length) {
    return undefined;
  }

  const latestIncome = incomeStatement[0];
  const latestRatio = ratios[0];
  const latestMetric = keyMetrics[0];

  return {
    source: "Financial Modeling Prep",
    numericVersion: 1,
    currency: latestIncome?.reportedCurrency || "USD",
    fiscalYearEnd: latestIncome?.calendarYear || "N/A",
    latestQuarter: latestIncome?.date || "N/A",
    profitMargin: formatPercentValue(fmpValue(latestRatio?.netProfitMarginTTM)),
    operatingMarginTtm: formatPercentValue(fmpValue(latestRatio?.operatingProfitMarginTTM)),
    returnOnEquityTtm: formatPercentValue(fmpValue(latestRatio?.returnOnEquityTTM)),
    priceToBookRatio: formatRatio(fmpValue(latestRatio?.priceToBookRatioTTM)),
    evToRevenue: formatRatio(
      fmpValue(latestMetric?.evToRevenueTTM ?? latestMetric?.evToSalesTTM)
    ),
    evToEbitda: formatRatio(fmpValue(latestMetric?.enterpriseValueMultipleTTM)),
    beta: "N/A",
    analystTargetPrice: "N/A",
    quarterly,
    annual,
    updatedAt: Date.now(),
  };
};

const buildFinancialReport = (
  overview: AlphaVantageOverview,
  incomeStatement: AlphaVantageStatementResponse,
  balanceSheet: AlphaVantageStatementResponse,
  cashFlow: AlphaVantageStatementResponse
) => {
  const quarterlyBalanceByDate = byFiscalDate(balanceSheet.quarterlyReports ?? []);
  const quarterlyCashByDate = byFiscalDate(cashFlow.quarterlyReports ?? []);
  const annualBalanceByDate = byFiscalDate(balanceSheet.annualReports ?? []);
  const annualCashByDate = byFiscalDate(cashFlow.annualReports ?? []);
  const quarterly = (incomeStatement.quarterlyReports ?? [])
    .slice(0, 4)
    .map((item) =>
      toFinancialPeriod(
        item,
        item.fiscalDateEnding
          ? quarterlyBalanceByDate.get(item.fiscalDateEnding)
          : undefined,
        item.fiscalDateEnding ? quarterlyCashByDate.get(item.fiscalDateEnding) : undefined,
        overview.Currency || "USD"
      )
    );

  const annual = (incomeStatement.annualReports ?? [])
    .slice(0, 4)
    .map((item) =>
      toFinancialPeriod(
        item,
        item.fiscalDateEnding ? annualBalanceByDate.get(item.fiscalDateEnding) : undefined,
        item.fiscalDateEnding ? annualCashByDate.get(item.fiscalDateEnding) : undefined,
        overview.Currency || "USD"
      )
    );

  if (!quarterly.length && !annual.length) {
    return undefined;
  }

  return {
    source: "Alpha Vantage",
    numericVersion: 1,
    currency: overview.Currency || "USD",
    fiscalYearEnd: overview.FiscalYearEnd || "N/A",
    latestQuarter: overview.LatestQuarter || "N/A",
    profitMargin: formatPercentValue(overview.ProfitMargin),
    operatingMarginTtm: formatPercentValue(overview.OperatingMarginTTM),
    returnOnEquityTtm: formatPercentValue(overview.ReturnOnEquityTTM),
    priceToBookRatio: formatRatio(overview.PriceToBookRatio),
    evToRevenue: formatRatio(overview.EVToRevenue),
    evToEbitda: formatRatio(overview.EVToEBITDA),
    beta: formatRatio(overview.Beta),
    analystTargetPrice: formatCurrencyValue(overview.AnalystTargetPrice),
    quarterly,
    annual,
    updatedAt: Date.now(),
  };
};

const secConceptAliases = {
  revenue: [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "Revenues",
  ],
  grossProfit: ["GrossProfit"],
  operatingIncome: ["OperatingIncomeLoss"],
  netIncome: ["NetIncomeLoss", "ProfitLoss"],
  dilutedEps: ["EarningsPerShareDiluted"],
  operatingCashflow: ["NetCashProvidedByUsedInOperatingActivities"],
  capitalExpenditures: [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForAdditionsToPropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
  ],
  totalAssets: ["Assets"],
  totalLiabilities: ["Liabilities"],
  totalShareholderEquity: [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
  ],
} as const;

const secHeaders = () => ({
  "User-Agent": process.env.SEC_USER_AGENT || "StockInvesting/0.1 local-research",
  Accept: "application/json",
});

const fetchSecJson = async <T>(
  url: string,
  operation: string,
  ticker: string,
  logEvent?: DataSourceLogger
) => {
  try {
    const response = await fetch(url, { headers: secHeaders() });
    if (!response.ok) {
      throw new Error(`SEC EDGAR ${operation} failed with ${response.status}.`);
    }
    await logEvent?.({
      service: "SEC EDGAR",
      operation,
      status: "success",
      provider: "SEC EDGAR",
      ticker,
    });
    return (await response.json()) as T;
  } catch (error) {
    await logEvent?.({
      service: "SEC EDGAR",
      operation,
      status: "error",
      provider: "SEC EDGAR",
      ticker,
      message: error instanceof Error ? error.message : "SEC EDGAR request failed.",
    });
    throw error;
  }
};

const secFactsForConcept = (
  companyFacts: SecCompanyFacts,
  aliases: readonly string[],
  unit: "USD" | "USD/shares"
) => {
  const taxonomy = companyFacts.facts["us-gaap"] ?? {};
  const combined = aliases.flatMap((concept) => taxonomy[concept]?.units?.[unit] ?? []);
  return combined.filter(
    (fact, index, all) =>
      all.findIndex(
        (candidate) =>
          candidate.accn === fact.accn &&
          candidate.end === fact.end &&
          candidate.val === fact.val
      ) === index
  );
};

const latestSecFactForPeriod = (
  facts: SecFact[],
  end: string,
  forms: Set<string>,
  accessionNumber?: string
) =>
  facts
    .filter(
      (fact) =>
        fact.end === end &&
        forms.has(fact.form) &&
        (!accessionNumber || fact.accn === accessionNumber)
    )
    .sort((left, right) => right.filed.localeCompare(left.filed))[0] ??
  facts
    .filter((fact) => fact.end === end && forms.has(fact.form))
    .sort((left, right) => right.filed.localeCompare(left.filed))[0];

const secFilingUrl = (cik: number, accessionNumber: string) =>
  `https://www.sec.gov/Archives/edgar/data/${cik}/${accessionNumber.replace(/-/g, "")}/`;

const latestSecFactsByPeriodEnd = (facts: SecFact[], limit: number) => {
  const byEnd = new Map<string, SecFact>();
  for (const fact of facts) {
    const current = byEnd.get(fact.end);
    if (!current || fact.filed > current.filed) {
      byEnd.set(fact.end, fact);
    }
  }
  return Array.from(byEnd.values())
    .sort((left, right) => right.end.localeCompare(left.end))
    .slice(0, limit);
};

type NormalizedPeriodRecord = {
  fiscalDateEnding: string;
  currency: string;
  derived?: boolean;
  derivation?: string;
  filedAt?: string;
  accessionNumber?: string;
  sourceUrl?: string;
  normalized: NumericFinancialValues;
  totalRevenue: string;
  grossProfit: string;
  operatingIncome: string;
  netIncome: string;
  dilutedEps: string;
  operatingCashflow: string;
  capitalExpenditures: string;
  freeCashFlow: string;
  totalAssets: string;
  totalLiabilities: string;
  totalShareholderEquity: string;
};

const deriveFiscalFourthQuarters = (
  annual: NormalizedPeriodRecord[],
  reportedQuarterly: NormalizedPeriodRecord[]
) => {
  const durationFields = [
    "totalRevenue",
    "grossProfit",
    "operatingIncome",
    "netIncome",
    "operatingCashflow",
    "capitalExpenditures",
    "freeCashFlow",
  ] as const;
  const derived: NormalizedPeriodRecord[] = [];

  for (let index = 0; index < annual.length - 1; index += 1) {
    const annualPeriod = annual[index];
    const previousAnnualEnd = annual[index + 1].fiscalDateEnding;
    const fiscalQuarters = reportedQuarterly
      .filter(
        (quarter) =>
          quarter.fiscalDateEnding > previousAnnualEnd &&
          quarter.fiscalDateEnding < annualPeriod.fiscalDateEnding
      )
      .sort((left, right) => left.fiscalDateEnding.localeCompare(right.fiscalDateEnding));
    if (fiscalQuarters.length !== 3 || !annualPeriod.normalized) continue;

    const normalized: NumericFinancialValues = {};
    for (const field of durationFields) {
      const annualValue = annualPeriod.normalized[field];
      const quarterValues = fiscalQuarters.map((quarter) => quarter.normalized?.[field]);
      if (
        annualValue !== undefined &&
        quarterValues.every((value): value is number => value !== undefined)
      ) {
        normalized[field] =
          annualValue - quarterValues.reduce((sum, value) => sum + value, 0);
      }
    }
    normalized.totalAssets = annualPeriod.normalized.totalAssets;
    normalized.totalLiabilities = annualPeriod.normalized.totalLiabilities;
    normalized.totalShareholderEquity =
      annualPeriod.normalized.totalShareholderEquity;
    const compact = normalizedFinancialValues(normalized);
    // Revenue is the seed fact and is sufficient to establish the missing Q4.
    // Keep independently unavailable fields as N/A instead of dropping the row.
    if (compact.totalRevenue === undefined) continue;
    const displayMoney = (field: keyof NumericFinancialValues) =>
      compact[field] === undefined
        ? "N/A"
        : formatLargeDollarValue(String(compact[field]));

    derived.push({
      fiscalDateEnding: annualPeriod.fiscalDateEnding,
      currency: annualPeriod.currency,
      derived: true,
      derivation: "Annual filing minus the three reported fiscal quarters",
      filedAt: annualPeriod.filedAt,
      accessionNumber: annualPeriod.accessionNumber,
      sourceUrl: annualPeriod.sourceUrl,
      normalized: compact,
      totalRevenue: displayMoney("totalRevenue"),
      grossProfit: displayMoney("grossProfit"),
      operatingIncome: displayMoney("operatingIncome"),
      netIncome: displayMoney("netIncome"),
      dilutedEps:
        compact.dilutedEps === undefined ? "N/A" : formatRatio(String(compact.dilutedEps)),
      operatingCashflow: displayMoney("operatingCashflow"),
      capitalExpenditures: displayMoney("capitalExpenditures"),
      freeCashFlow: displayMoney("freeCashFlow"),
      totalAssets: displayMoney("totalAssets"),
      totalLiabilities: displayMoney("totalLiabilities"),
      totalShareholderEquity: displayMoney("totalShareholderEquity"),
    });
  }

  return [...reportedQuarterly, ...derived]
    .sort((left, right) => right.fiscalDateEnding.localeCompare(left.fiscalDateEnding))
    .slice(0, 8);
};

const buildSecFinancialReport = (companyFacts: SecCompanyFacts) => {
  const revenueFacts = secFactsForConcept(
    companyFacts,
    secConceptAliases.revenue,
    "USD"
  );
  const annualSeeds = latestSecFactsByPeriodEnd(
    revenueFacts.filter((fact) => fact.form === "10-K" && fact.fp === "FY"),
    4
  );
  const quarterlySeeds = latestSecFactsByPeriodEnd(
    revenueFacts.filter(
      (fact) =>
        fact.form === "10-Q" &&
        Boolean(fact.frame?.match(/^CY\d{4}Q[1-4]$/))
    ),
    12
  );

  const buildPeriod = (seed: SecFact) => {
    const forms = new Set([seed.form]);
    const findInstantUsd = (aliases: readonly string[]) =>
      latestSecFactForPeriod(
        secFactsForConcept(companyFacts, aliases, "USD"),
        seed.end,
        forms,
        seed.accn
      );
    const findDurationFact = (aliases: readonly string[], unit: "USD" | "USD/shares") => {
      const facts = secFactsForConcept(companyFacts, aliases, unit);
      const matchingFrame = seed.frame
        ? facts.filter((fact) => fact.frame === seed.frame)
        : facts;
      return latestSecFactForPeriod(
        matchingFrame,
        seed.end,
        forms,
        seed.accn
      );
    };
    const operatingCashflow = findDurationFact(
      secConceptAliases.operatingCashflow,
      "USD"
    )?.val;
    const capitalExpenditures = findDurationFact(
      secConceptAliases.capitalExpenditures,
      "USD"
    )?.val;
    const freeCashFlow =
      operatingCashflow !== undefined && capitalExpenditures !== undefined
        ? operatingCashflow - Math.abs(capitalExpenditures)
        : undefined;
    const sourceUrl = secFilingUrl(companyFacts.cik, seed.accn);

    return {
      fiscalDateEnding: seed.end,
      currency: "USD",
      filedAt: seed.filed,
      accessionNumber: seed.accn,
      sourceUrl,
      normalized: normalizedFinancialValues({
        totalRevenue: seed.val,
        grossProfit: findDurationFact(secConceptAliases.grossProfit, "USD")?.val,
        operatingIncome: findDurationFact(secConceptAliases.operatingIncome, "USD")?.val,
        netIncome: findDurationFact(secConceptAliases.netIncome, "USD")?.val,
        dilutedEps: findDurationFact(secConceptAliases.dilutedEps, "USD/shares")?.val,
        operatingCashflow,
        capitalExpenditures,
        freeCashFlow,
        totalAssets: findInstantUsd(secConceptAliases.totalAssets)?.val,
        totalLiabilities: findInstantUsd(secConceptAliases.totalLiabilities)?.val,
        totalShareholderEquity: findInstantUsd(
          secConceptAliases.totalShareholderEquity
        )?.val,
      }),
      totalRevenue: formatLargeDollarValue(String(seed.val)),
      grossProfit: formatLargeDollarValue(
        fmpValue(findDurationFact(secConceptAliases.grossProfit, "USD")?.val)
      ),
      operatingIncome: formatLargeDollarValue(
        fmpValue(findDurationFact(secConceptAliases.operatingIncome, "USD")?.val)
      ),
      netIncome: formatLargeDollarValue(
        fmpValue(findDurationFact(secConceptAliases.netIncome, "USD")?.val)
      ),
      dilutedEps: formatRatio(
        fmpValue(
          findDurationFact(secConceptAliases.dilutedEps, "USD/shares")?.val
        )
      ),
      operatingCashflow: formatLargeDollarValue(fmpValue(operatingCashflow)),
      capitalExpenditures: formatLargeDollarValue(fmpValue(capitalExpenditures)),
      freeCashFlow: formatLargeDollarValue(fmpValue(freeCashFlow)),
      totalAssets: formatLargeDollarValue(
        fmpValue(findInstantUsd(secConceptAliases.totalAssets)?.val)
      ),
      totalLiabilities: formatLargeDollarValue(
        fmpValue(findInstantUsd(secConceptAliases.totalLiabilities)?.val)
      ),
      totalShareholderEquity: formatLargeDollarValue(
        fmpValue(findInstantUsd(secConceptAliases.totalShareholderEquity)?.val)
      ),
    };
  };

  const reportedQuarterly = quarterlySeeds.map(buildPeriod);
  const annual = annualSeeds.map(buildPeriod);
  const quarterly = deriveFiscalFourthQuarters(annual, reportedQuarterly);
  if (!quarterly.length && !annual.length) {
    return undefined;
  }
  const latest = quarterlySeeds[0] ?? annualSeeds[0];
  const latestAnnual = annual[0];
  const parseFormatted = (value?: string) => {
    if (!value || value === "N/A") return undefined;
    const multiplier = value.endsWith("T")
      ? 1e12
      : value.endsWith("B")
        ? 1e9
        : value.endsWith("M")
          ? 1e6
          : 1;
    const parsed = Number(value.replace(/[TBM]/, ""));
    return Number.isFinite(parsed) ? parsed * multiplier : undefined;
  };
  const revenue = parseFormatted(latestAnnual?.totalRevenue);
  const netIncome = parseFormatted(latestAnnual?.netIncome);
  const operatingIncome = parseFormatted(latestAnnual?.operatingIncome);
  const equity = parseFormatted(latestAnnual?.totalShareholderEquity);
  const sourceUrl = latest ? secFilingUrl(companyFacts.cik, latest.accn) : undefined;
  const warnings: string[] = [];
  if (quarterly.length < 4) {
    warnings.push("SEC Company Facts returned fewer than four discrete quarterly periods.");
  }
  const incompleteCorePeriods = [...quarterly, ...annual].filter((period) =>
    [period.totalRevenue, period.netIncome, period.totalAssets].some(
      (value) => value === "N/A"
    )
  ).length;
  if (incompleteCorePeriods) {
    warnings.push(
      `${incompleteCorePeriods} filing period${incompleteCorePeriods === 1 ? " is" : "s are"} missing one or more core SEC facts.`
    );
  }
  const missingDiscreteCashFlow = quarterly.filter(
    (period) => period.operatingCashflow === "N/A" || period.capitalExpenditures === "N/A"
  ).length;
  if (missingDiscreteCashFlow) {
    warnings.push(
      `${missingDiscreteCashFlow} quarter${missingDiscreteCashFlow === 1 ? " is" : "s are"} missing discrete SEC cash-flow facts; cumulative year-to-date values were not substituted.`
    );
  }
  const derivedQuarterCount = quarterly.filter((period) => period.derived).length;
  if (derivedQuarterCount) {
    warnings.push(
      `${derivedQuarterCount} fiscal Q4 period${derivedQuarterCount === 1 ? " was" : "s were"} derived from annual results minus Q1-Q3.`
    );
  }
  for (const period of [...quarterly, ...annual]) {
    const assets = period.normalized?.totalAssets;
    const liabilities = period.normalized?.totalLiabilities;
    const equity = period.normalized?.totalShareholderEquity;
    if (assets && liabilities !== undefined && equity !== undefined) {
      const residual = Math.abs(assets - liabilities - equity) / Math.abs(assets);
      if (residual > 0.02) {
        warnings.push(
          `${period.fiscalDateEnding} balance sheet differs from assets = liabilities + equity by ${(residual * 100).toFixed(1)}%.`
        );
      }
    }
  }
  for (let index = 0; index < quarterly.length - 1; index += 1) {
    const current = quarterly[index];
    const previous = quarterly[index + 1];
    const currentRevenue = current.normalized?.totalRevenue;
    const previousRevenue = previous.normalized?.totalRevenue;
    if (currentRevenue !== undefined && previousRevenue && previousRevenue > 0) {
      const growth = currentRevenue / previousRevenue - 1;
      if (growth > 1.5 || growth < -0.7) {
        warnings.push(
          `${current.fiscalDateEnding} revenue changed ${(growth * 100).toFixed(1)}% from the preceding stored quarter; review period comparability.`
        );
      }
    }
  }

  return {
    source: "SEC EDGAR",
    numericVersion: 1,
    sourceUrl,
    filedAt: latest?.filed,
    accessionNumber: latest?.accn,
    validationStatus: warnings.length ? ("partial" as const) : ("verified" as const),
    warnings,
    currency: "USD",
    fiscalYearEnd: annualSeeds[0]?.end ?? "N/A",
    latestQuarter: quarterlySeeds[0]?.end ?? annualSeeds[0]?.end ?? "N/A",
    profitMargin:
      revenue && netIncome !== undefined
        ? formatPercentValue(String(netIncome / revenue))
        : "N/A",
    operatingMarginTtm:
      revenue && operatingIncome !== undefined
        ? formatPercentValue(String(operatingIncome / revenue))
        : "N/A",
    returnOnEquityTtm:
      equity && netIncome !== undefined
        ? formatPercentValue(String(netIncome / equity))
        : "N/A",
    priceToBookRatio: "N/A",
    evToRevenue: "N/A",
    evToEbitda: "N/A",
    beta: "N/A",
    analystTargetPrice: "N/A",
    quarterly,
    annual,
    updatedAt: Date.now(),
  };
};

const fetchSecFinancialReport = async (
  ticker: string,
  fmpApiKey?: string,
  logEvent?: DataSourceLogger
) => {
  let cikValue: number | undefined;
  try {
    const tickerMap = await fetchSecJson<Record<string, SecTickerEntry>>(
      "https://www.sec.gov/files/company_tickers.json",
      "ticker_map",
      ticker,
      logEvent
    );
    cikValue = Object.values(tickerMap).find(
      (candidate) => candidate.ticker.toUpperCase() === ticker
    )?.cik_str;
  } catch {
    if (fmpApiKey) {
      const profiles = await fetchFmpJson<Array<{ cik?: string }>>(
        ticker,
        "profile",
        fmpApiKey,
        logEvent
      );
      const parsedCik = Number(profiles[0]?.cik);
      cikValue = Number.isFinite(parsedCik) ? parsedCik : undefined;
    }
  }
  if (!cikValue) {
    throw new Error(`SEC EDGAR did not find a CIK for ${ticker}.`);
  }
  const cik = String(cikValue).padStart(10, "0");
  const companyFacts = await fetchSecJson<SecCompanyFacts>(
    `https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`,
    "company_facts",
    ticker,
    logEvent
  );
  const report = buildSecFinancialReport(companyFacts);
  if (!report) {
    throw new Error(`SEC EDGAR did not return usable statement facts for ${ticker}.`);
  }
  return report;
};

const fetchFmpJson = async <T>(
  symbol: string,
  path: string,
  apiKey: string,
  logEvent?: DataSourceLogger,
  params: Record<string, string> = {}
) => {
  const url = new URL(`https://financialmodelingprep.com/stable/${path}`);
  url.searchParams.set("symbol", symbol);
  Object.entries(params).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });
  url.searchParams.set("apikey", apiKey);

  try {
    const response = await fetch(url);
    const data = (await response.json()) as T & {
      Error?: string;
      error?: string;
      message?: string;
    };

    if (!response.ok || data.Error || data.error || data.message) {
      throw new Error(
        data.Error || data.error || data.message || `FMP ${path} failed with ${response.status}.`
      );
    }

    await logEvent?.({
      service: "Financial Modeling Prep",
      operation: path,
      status: "success",
      provider: "Financial Modeling Prep",
      ticker: symbol,
    });

    return data;
  } catch (error) {
    await logEvent?.({
      service: "Financial Modeling Prep",
      operation: path,
      status: "error",
      provider: "Financial Modeling Prep",
      ticker: symbol,
      message: error instanceof Error ? error.message : `FMP ${path} failed.`,
    });
    throw error;
  }
};

const fetchFmpFinancialReport = async (
  symbol: string,
  apiKey: string,
  logEvent?: DataSourceLogger
) => {
  const [
    annualIncomeStatement,
    annualBalanceSheet,
    annualCashFlow,
    quarterlyIncomeStatement,
    quarterlyBalanceSheet,
    quarterlyCashFlow,
    ratios,
    keyMetrics,
  ] = await Promise.all([
    fetchFmpJson<FmpStatement[]>(symbol, "income-statement", apiKey, logEvent),
    fetchFmpJson<FmpStatement[]>(symbol, "balance-sheet-statement", apiKey, logEvent),
    fetchFmpJson<FmpStatement[]>(symbol, "cash-flow-statement", apiKey, logEvent),
    fetchFmpJson<FmpStatement[]>(symbol, "income-statement", apiKey, logEvent, {
      period: "quarter",
    }).catch(() => []),
    fetchFmpJson<FmpStatement[]>(symbol, "balance-sheet-statement", apiKey, logEvent, {
      period: "quarter",
    }).catch(() => []),
    fetchFmpJson<FmpStatement[]>(symbol, "cash-flow-statement", apiKey, logEvent, {
      period: "quarter",
    }).catch(() => []),
    fetchFmpJson<FmpRatio[]>(symbol, "ratios-ttm", apiKey, logEvent).catch(() => []),
    fetchFmpJson<FmpKeyMetric[]>(symbol, "key-metrics-ttm", apiKey, logEvent).catch(() => []),
  ]);

  const financialReport = buildFmpFinancialReport(
    [...quarterlyIncomeStatement, ...annualIncomeStatement],
    [...quarterlyBalanceSheet, ...annualBalanceSheet],
    [...quarterlyCashFlow, ...annualCashFlow],
    ratios,
    keyMetrics
  );

  if (!financialReport) {
    throw new Error(`Financial Modeling Prep did not return statement data for ${symbol}.`);
  }

  return financialReport;
};

const fetchAlphaVantageFinancialsWithRotation = async (
  symbol: string,
  keySlots: AlphaVantageKeySlot[],
  logEvent?: DataSourceLogger
) => {
  let usedSecondaryKey = false;

  if (!keySlots.length) {
    return undefined;
  }

  const overviewResult = await fetchAlphaVantageJsonWithRotation<AlphaVantageOverview>(
    symbol,
    "OVERVIEW",
    keySlots,
    logEvent
  );
  usedSecondaryKey = usedSecondaryKey || overviewResult.usedSecondaryKey;

  const incomeStatementResult = await fetchAlphaVantageJsonWithRotation<AlphaVantageStatementResponse>(
    symbol,
    "INCOME_STATEMENT",
    keySlots,
    logEvent
  );
  usedSecondaryKey = usedSecondaryKey || incomeStatementResult.usedSecondaryKey;

  const balanceSheetResult = await fetchAlphaVantageJsonWithRotation<AlphaVantageStatementResponse>(
    symbol,
    "BALANCE_SHEET",
    keySlots,
    logEvent
  );
  usedSecondaryKey = usedSecondaryKey || balanceSheetResult.usedSecondaryKey;

  const cashFlowResult = await fetchAlphaVantageJsonWithRotation<AlphaVantageStatementResponse>(
    symbol,
    "CASH_FLOW",
    keySlots,
    logEvent
  );
  usedSecondaryKey = usedSecondaryKey || cashFlowResult.usedSecondaryKey;

  return {
    overview: overviewResult.data,
    incomeStatement: incomeStatementResult.data,
    balanceSheet: balanceSheetResult.data,
    cashFlow: cashFlowResult.data,
    usedSecondaryKey,
  };
};

const buildLiveSummary = (input: {
  companyName: string;
  sector: string;
  price: number;
  changePercent: number;
  marketCap: string;
  headlines: string[];
}) => {
  const direction =
    input.changePercent >= 0 ? "trading higher today" : "trading lower today";
  const headlineSummary = input.headlines.length
    ? `Recent coverage highlights ${input.headlines.slice(0, 2).join("; ")}.`
    : "Recent news flow is limited, so filings and earnings materials matter more here.";

  return `${input.companyName} is ${direction} at $${input.price.toFixed(2)} (${formatSignedPercent(
    input.changePercent
  )}), with a market cap of ${input.marketCap} in the ${input.sector.toLowerCase()} sector. ${headlineSummary} Use this brief as a live starting point, then validate with company filings and earnings commentary.`;
};

const buildLiveResearchItems = (input: {
  companyName: string;
  sector: string;
  changePercent: number;
  headlines: string[];
}) => {
  const positiveHeadline = input.headlines.find((headline) =>
    positiveHeadlinePattern.test(headline)
  );
  const riskHeadline = input.headlines.find((headline) =>
    riskHeadlinePattern.test(headline)
  );

  return [
    {
      kind: "strength" as const,
      title: positiveHeadline ? "Positive news flow" : "Live market momentum",
      body: positiveHeadline
        ? positiveHeadline
        : `${input.companyName} is showing ${input.changePercent >= 0 ? "positive" : "mixed"} recent momentum inside the ${input.sector.toLowerCase()} sector.`,
    },
    {
      kind: "risk" as const,
      title: riskHeadline ? "Headline risk to monitor" : "Need deeper fundamental validation",
      body: riskHeadline
        ? riskHeadline
        : "Price action and top headlines are useful, but they should be checked against earnings, guidance, valuation, and filings.",
    },
    {
      kind: "thesis" as const,
      title: "Check whether current news supports the core thesis",
      body: `Use the latest ${input.companyName} headlines, earnings commentary, and sector context to decide whether the recent move reflects durable fundamentals.`,
      status: "open" as const,
    },
  ];
};

export const syncFinancials = action({
  args: { ticker: v.string() },
  handler: async (ctx, args): Promise<{
    ticker: string;
    source: string;
    updatedAt: number;
    usedSecondaryAlphaKey: boolean;
    persisted: boolean;
    quarterlyPeriods: number;
    derivedQuarterlyPeriods: number;
  }> => {
    const ticker = normalizeTicker(args.ticker);
    const fmpApiKey = process.env.FMP_API_KEY;
    const dateKey = new Date().toISOString().slice(0, 10);
    let logQueue = Promise.resolve();
    const logEvent: DataSourceLogger = async (event) => {
      logQueue = logQueue
        .catch(() => undefined)
        .then(() =>
          ctx.runMutation(internal.dataSources.recordInternalEvent, {
            ...event,
            calledAt: Date.now(),
          })
        )
        .then(
          () => undefined,
          (error) => console.warn("Unable to record data source event", error)
        );
      await logQueue;
    };
    const usageRows: Array<{
      service: string;
      usage: {
        count?: number;
        lastMessage?: string;
        lastRequestedAt?: number;
        lastCalledAt?: number;
      } | null;
    }> = await ctx.runQuery(internal.dataSources.usageForServices, {
      dateKey,
      services: [
        alphaVantagePrimaryLabel,
        alphaVantageSecondaryLabel,
        alphaVantageTertiaryLabel,
      ],
    });
    const alphaKeys = orderAlphaVantageKeysByUsage(
      process.env.ALPHAVANTAGE_API_KEY,
      process.env.ALPHAVANTAGE_API_KEY_SECONDARY,
      process.env.ALPHAVANTAGE_API_KEY_TERTIARY,
      new Map(usageRows.map((row) => [row.service, row.usage]))
    );
    let financialReport: ReturnType<typeof buildFinancialReport>;
    let usedSecondaryAlphaKey = false;

    try {
      financialReport = await fetchSecFinancialReport(ticker, fmpApiKey, logEvent);
    } catch (error) {
      if (fmpApiKey || alphaKeys.length) {
        await logEvent({
          service: "Financials Fallback",
          operation: "financials",
          status: "fallback",
          provider: "SEC EDGAR",
          fallbackProvider: fmpApiKey ? "Financial Modeling Prep" : "Alpha Vantage",
          ticker,
          message:
            error instanceof Error
              ? error.message
              : "SEC EDGAR financial sync failed; trying a normalized provider.",
        });
      }
    }

    if (!financialReport && fmpApiKey) {
      try {
        financialReport = await fetchFmpFinancialReport(ticker, fmpApiKey, logEvent);
      } catch (error) {
        if (alphaKeys.length) {
          await logEvent({
            service: "Financials Fallback",
            operation: "financials",
            status: "fallback",
            provider: "Financial Modeling Prep",
            fallbackProvider: "Alpha Vantage",
            ticker,
            message:
              error instanceof Error
                ? error.message
                : "FMP financial sync failed; trying Alpha Vantage.",
          });
        }
      }
    }

    if (!financialReport && alphaKeys.length) {
      const result = await fetchAlphaVantageFinancialsWithRotation(
        ticker,
        alphaKeys,
        logEvent
      );
      usedSecondaryAlphaKey = Boolean(result?.usedSecondaryKey);
      if (result) {
        financialReport = buildFinancialReport(
          result.overview,
          result.incomeStatement,
          result.balanceSheet,
          result.cashFlow
        );
      }
    }

    if (!financialReport) {
      throw new Error(
        "Financial statements are unavailable from the configured Convex providers."
      );
    }

    const persistenceResult: {
      saved: boolean;
    } = await ctx.runMutation(internal.stocks.upsertFinancialReport, {
      ticker,
      financialReport,
    });

    return {
      ticker,
      source: financialReport.source,
      updatedAt: financialReport.updatedAt,
      usedSecondaryAlphaKey,
      persisted: persistenceResult.saved,
      quarterlyPeriods: financialReport.quarterly.length,
      derivedQuarterlyPeriods: financialReport.quarterly.filter(
        (period) => "derived" in period && period.derived
      ).length,
    };
  },
});

export const syncTicker = action({
  args: { ticker: v.string() },
  handler: async (ctx, args): Promise<{
    ticker: string;
    companyName: string;
    price: number;
    change: number;
    changePercent: number;
    hasChartData: boolean;
    usingCachedFinancials: boolean;
    refreshedFinancials: boolean;
    financialSource: string | null;
    preservedStoredFinancials: boolean;
    usedSecondaryAlphaKey: boolean;
    relevantNewsCount: number;
    filteredNewsCount: number;
    syncedAt: number;
  }> => {
    const apiKey = process.env.FINNHUB_API_KEY;
    const alphaVantageApiKey = process.env.ALPHAVANTAGE_API_KEY;
    const alphaVantageSecondaryApiKey = process.env.ALPHAVANTAGE_API_KEY_SECONDARY;
    const alphaVantageTertiaryApiKey = process.env.ALPHAVANTAGE_API_KEY_TERTIARY;
    const twelveDataApiKey = process.env.TWELVEDATA_API_KEY;
    const fmpApiKey = process.env.FMP_API_KEY;
    if (!apiKey) {
      throw new Error(
        "FINNHUB_API_KEY is not configured. Run `npx convex env set FINNHUB_API_KEY <your-key>`."
      );
    }

    const ticker = normalizeTicker(args.ticker);
    let dataSourceLogQueue = Promise.resolve();
    const logEvent: DataSourceLogger = async (event) => {
      dataSourceLogQueue = dataSourceLogQueue
        .catch(() => undefined)
        .then(() =>
          ctx.runMutation(internal.dataSources.recordInternalEvent, {
            ...event,
            calledAt: Date.now(),
          })
        )
        .then(
          () => undefined,
          (error) => {
            console.warn("Unable to record data source event", error);
          }
        );
      await dataSourceLogQueue;
    };
    const [existingStock, existingFinancialReport]: [
      Doc<"stocks"> | null,
      Doc<"financialReports"> | null,
    ] = await Promise.all([
      ctx.runQuery(api.stocks.getByTicker, { ticker }),
      ctx.runQuery(api.stocks.getFinancialReportByTicker, { ticker }),
    ]);
    const todayKey = new Date().toISOString().slice(0, 10);
    const alphaUsageRows: Array<{
      service: string;
      usage: {
        count?: number;
        lastMessage?: string;
        lastRequestedAt?: number;
        lastCalledAt?: number;
      } | null;
    }> = await ctx.runQuery(internal.dataSources.usageForServices, {
      dateKey: todayKey,
      services: [
        alphaVantagePrimaryLabel,
        alphaVantageSecondaryLabel,
        alphaVantageTertiaryLabel,
      ],
    });
    const orderedAlphaVantageKeys = orderAlphaVantageKeysByUsage(
      alphaVantageApiKey,
      alphaVantageSecondaryApiKey,
      alphaVantageTertiaryApiKey,
      new Map(alphaUsageRows.map((row) => [row.service, row.usage]))
    );
    const financialReportRequest = (async () => {
      try {
        return {
          financialReport: await fetchSecFinancialReport(ticker, fmpApiKey, logEvent),
          overview: undefined,
          usedSecondaryAlphaKey: false,
        };
      } catch (error) {
        if (fmpApiKey || orderedAlphaVantageKeys.length) {
          await logEvent({
            service: "Financials Fallback",
            operation: "financials",
            status: "fallback",
            provider: "SEC EDGAR",
            fallbackProvider: fmpApiKey ? "Financial Modeling Prep" : "Alpha Vantage",
            ticker,
            message:
              error instanceof Error
                ? error.message
                : "SEC EDGAR financial sync failed; trying a normalized provider.",
          });
        }
      }

      if (fmpApiKey) {
        try {
          return {
            financialReport: await fetchFmpFinancialReport(ticker, fmpApiKey, logEvent),
            overview: undefined,
            usedSecondaryAlphaKey: false,
          };
        } catch (error) {
          if (orderedAlphaVantageKeys.length) {
            await logEvent({
              service: "Financials Fallback",
              operation: "financials",
              status: "fallback",
              provider: "Financial Modeling Prep",
              fallbackProvider: "Alpha Vantage",
              ticker,
              message:
                error instanceof Error
                  ? error.message
                  : "FMP financial sync failed; trying Alpha Vantage.",
            });
          }
        }
      }

      if (!orderedAlphaVantageKeys.length) {
        return undefined;
      }

      const alphaVantageFinancials = await fetchAlphaVantageFinancialsWithRotation(
        ticker,
        orderedAlphaVantageKeys,
        logEvent
      );
      const overview = alphaVantageFinancials?.overview;
      const incomeStatement = alphaVantageFinancials?.incomeStatement;
      const balanceSheet = alphaVantageFinancials?.balanceSheet;
      const cashFlow = alphaVantageFinancials?.cashFlow;
      const financialReport =
        overview && incomeStatement && balanceSheet && cashFlow
          ? buildFinancialReport(overview, incomeStatement, balanceSheet, cashFlow)
          : undefined;

      return {
        financialReport,
        overview,
        usedSecondaryAlphaKey: Boolean(alphaVantageFinancials?.usedSecondaryKey),
      };
    })().catch(() => undefined);

    const [quote, profile, news, chartHistory, financialResult] = await Promise.all([
      fetchQuoteWithFallback(ticker, apiKey, twelveDataApiKey, logEvent),
      fetchFinnhub<FinnhubProfile>("/stock/profile2", { symbol: ticker }, apiKey, logEvent),
      fetchFinnhub<FinnhubNewsItem[]>(
        "/company-news",
        {
          symbol: ticker,
          from: isoDate(-14),
          to: isoDate(0),
        },
        apiKey,
        logEvent
      ),
      fetchChartHistory(
        ticker,
        twelveDataApiKey ? [] : orderedAlphaVantageKeys,
        twelveDataApiKey,
        logEvent
      ),
      financialReportRequest,
    ]);

    const companyName = profile.name || ticker;
    const sector = profile.finnhubIndustry || "Unknown";
    const change = quote.d;
    const changePercent = quote.dp;
    const updatedAt = quote.t ? quote.t * 1000 : Date.now();
    const chartPoints = chartHistory?.length ? chartHistory : undefined;
    const financialReport = financialResult?.financialReport;
    const overview = financialResult?.overview;
    const qualifiedNews = qualifyCompanyNews({ ticker, companyName, news });
    const headlines = qualifiedNews.accepted.map((item) => item.headline);
    await logEvent({
      service: "News Quality Gate",
      operation: "news_filter",
      status: "success",
      provider: "Finnhub",
      ticker,
      message: `${qualifiedNews.accepted.length} company-relevant headline${
        qualifiedNews.accepted.length === 1 ? "" : "s"
      } accepted; ${qualifiedNews.filteredCount} unrelated or duplicate headline${
        qualifiedNews.filteredCount === 1 ? "" : "s"
      } filtered.`,
    });
    const summary = buildLiveSummary({
      companyName,
      sector,
      price: quote.c,
      changePercent,
      marketCap:
        formatLargeDollarValue(overview?.MarketCapitalization) !== "N/A"
          ? formatLargeDollarValue(overview?.MarketCapitalization)
          : existingStock?.marketCap ?? formatMarketCap(profile.marketCapitalization),
      headlines,
    });
    const researchItems = buildLiveResearchItems({
      companyName,
      sector,
      changePercent,
      headlines,
    });

    const financialPersistenceResult: { saved: boolean } | undefined = financialReport
      ? await ctx.runMutation(internal.stocks.upsertFinancialReport, {
          ticker,
          financialReport,
        })
      : undefined;

    await ctx.runMutation(internal.stocks.upsertMarketData, {
      stock: {
        ticker,
        companyName,
        exchange: profile.exchange || "US",
        sector,
        logoUrl: profile.logo || undefined,
        price: quote.c,
        change,
        changePercent,
        marketCap:
          formatLargeDollarValue(overview?.MarketCapitalization) !== "N/A"
            ? formatLargeDollarValue(overview?.MarketCapitalization)
            : existingStock?.marketCap ?? formatMarketCap(profile.marketCapitalization),
        peRatio:
          formatRatio(overview?.PERatio) !== "N/A"
            ? formatRatio(overview?.PERatio)
            : existingStock?.peRatio ?? "N/A",
        revenueTtm:
          formatLargeDollarValue(overview?.RevenueTTM) !== "N/A"
            ? formatLargeDollarValue(overview?.RevenueTTM)
            : existingStock?.revenueTtm ?? "N/A",
        epsTtm:
          formatRatio(overview?.EPS) !== "N/A"
            ? formatRatio(overview?.EPS)
            : existingStock?.epsTtm ?? "N/A",
        dividendYield:
          formatPercentValue(overview?.DividendYield) !== "N/A"
            ? formatPercentValue(overview?.DividendYield)
            : existingStock?.dividendYield ?? "N/A",
        summary,
        chartPoints,
        updatedAt,
      },
      news: qualifiedNews.accepted
        .map((item) => ({
          headline: item.headline,
          source: item.source || "Finnhub",
          url: item.url || undefined,
          publishedAt: item.datetime ? item.datetime * 1000 : Date.now(),
        })),
      researchItems,
      snapshot: {
        ticker,
        companyName,
        exchange: profile.exchange || "US",
        sector,
        price: quote.c,
        change,
        changePercent,
        marketCap:
          formatLargeDollarValue(overview?.MarketCapitalization) !== "N/A"
            ? formatLargeDollarValue(overview?.MarketCapitalization)
            : existingStock?.marketCap ?? formatMarketCap(profile.marketCapitalization),
        peRatio:
          formatRatio(overview?.PERatio) !== "N/A"
            ? formatRatio(overview?.PERatio)
            : existingStock?.peRatio ?? "N/A",
        revenueTtm:
          formatLargeDollarValue(overview?.RevenueTTM) !== "N/A"
            ? formatLargeDollarValue(overview?.RevenueTTM)
            : existingStock?.revenueTtm ?? "N/A",
        epsTtm:
          formatRatio(overview?.EPS) !== "N/A"
            ? formatRatio(overview?.EPS)
            : existingStock?.epsTtm ?? "N/A",
        dividendYield:
          formatPercentValue(overview?.DividendYield) !== "N/A"
            ? formatPercentValue(overview?.DividendYield)
            : existingStock?.dividendYield ?? "N/A",
        summary,
        syncedAt: updatedAt,
      },
    });

    return {
      ticker,
      companyName,
      price: quote.c,
      change,
      changePercent,
      hasChartData: Boolean(chartPoints?.length),
      usingCachedFinancials:
        (!financialReport || financialPersistenceResult?.saved === false) &&
        Boolean(existingFinancialReport),
      refreshedFinancials: financialPersistenceResult?.saved === true,
      financialSource: financialReport?.source ?? existingFinancialReport?.source ?? null,
      preservedStoredFinancials:
        Boolean(financialReport) && financialPersistenceResult?.saved === false,
      usedSecondaryAlphaKey: Boolean(financialResult?.usedSecondaryAlphaKey),
      relevantNewsCount: qualifiedNews.accepted.length,
      filteredNewsCount: qualifiedNews.filteredCount,
      syncedAt: Date.now(),
    };
  },
});

export const searchSymbols = action({
  args: { query: v.string() },
  handler: async (ctx, args) => {
    const apiKey = process.env.FINNHUB_API_KEY;
    if (!apiKey) {
      throw new Error(
        "FINNHUB_API_KEY is not configured. Run `npx convex env set FINNHUB_API_KEY <your-key>`."
      );
    }

    const query = args.query.trim();
    if (query.length < 2) {
      return [];
    }

    const data = await fetchFinnhub<FinnhubSymbolSearch>(
      "/search",
      { q: query },
      apiKey,
      async (event) => {
        await ctx.runMutation(internal.dataSources.recordInternalEvent, {
          ...event,
          operation: "symbol_search",
          calledAt: Date.now(),
        });
      }
    );

    return (data.result ?? [])
      .filter((item) => item.symbol && item.description)
      .slice(0, 6)
      .map((item) => ({
        symbol: normalizeTicker(item.symbol ?? ""),
        displaySymbol: item.displaySymbol || item.symbol || "",
        description: item.description || item.symbol || "",
        type: item.type || "Common Stock",
      }));
  },
});
