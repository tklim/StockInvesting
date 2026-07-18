import {
  BarChart3,
  Bell,
  BriefcaseBusiness,
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  ExternalLink,
  FileText,
  Filter,
  Globe2,
  LineChart,
  Moon,
  MoreHorizontal,
  RefreshCw,
  Search,
  Settings,
  Sparkles,
  Star,
  Sun,
  TrendingUp,
  TriangleAlert,
} from "lucide-react";
import {
  Component,
  Fragment,
  useEffect,
  useMemo,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { useAction, useMutation, useQuery } from "convex/react";
import { api } from "../convex/_generated/api";
import type { Id } from "../convex/_generated/dataModel";
import {
  chartSeriesByTicker,
  demoBundle,
  researchBundles,
  ResearchBundle,
  ResearchItem,
  searchableStocks,
  StockSummary,
} from "./mockData";

type AppProps = {
  convexEnabled: boolean;
};

type ConvexRuntimeGuardProps = {
  children: ReactNode;
};

type ConvexRuntimeGuardState = {
  errorMessage: string | null;
};

type ShellProps = {
  bundle: ResearchBundle;
  activeView: AppView;
  compareEntries: CompareEntry[];
  compareTickers: string[];
  dataSourceHealth?: DataSourceHealth;
  selectedList: string;
  listNames: string[];
  listSummaries: ListSummary[];
  portfolioItems: PortfolioItem[];
  searchQuery: string;
  selectedTicker: string;
  selectedListName: string;
  onViewChange: (view: AppView) => void;
  onCompareTickersChange: (tickers: string[]) => void;
  onOpenCompare: (tickers?: string[]) => void;
  onUpdatePortfolioPosition: (input: PortfolioPositionInput) => Promise<void>;
  onSelectedListChange: (listName: string) => void;
  onSelectedListNameChange: (listName: string) => void;
  onCreateList?: (name: string) => Promise<void>;
  onRenameList?: (currentName: string, nextName: string) => Promise<void>;
  onDeleteList?: (name: string, fallbackListName?: string) => Promise<void>;
  searchResults: StockSummary[];
  finnhubResults?: FinnhubSearchResult[];
  finnhubSearchStatus?: "idle" | "searching" | "success" | "error";
  finnhubSearchMessage?: string;
  onSearchChange: (value: string) => void;
  onSearchFinnhub?: (query: string) => Promise<void>;
  onImportFinnhubSymbol?: (symbol: string) => Promise<void>;
  onSelectTicker: (ticker: string) => void;
  onSaveToggle: () => void;
  onSyncMarketData?: () => Promise<void>;
  onSyncFinancials?: () => Promise<void>;
  onGenerateAiReport?: () => Promise<void>;
  onCreateNote?: (input: NoteInput) => Promise<void>;
  onDeleteNote?: (input: NoteDeleteInput) => Promise<void>;
  onGenerateAiNotes?: () => Promise<void>;
  onProposeInvestmentThesis?: () => Promise<void>;
  onSaveInvestmentThesis?: (input: {
    summary: string;
    thesisPoints: string[];
    watchItems: string[];
  }) => Promise<void>;
  syncStatus?: "idle" | "syncing" | "success" | "error";
  syncMessage?: string;
  aiReportStatus?: "idle" | "generating" | "success" | "error";
  aiReportMessage?: string;
  noteStatus?: NoteStatus;
  noteMessage?: string;
  thesisStatus?: "idle" | "proposing" | "saving" | "success" | "error";
  thesisMessage?: string;
};

type AppView =
  | "research"
  | "watchlist"
  | "portfolio"
  | "compare"
  | "data-health"
  | "screener";
type ResearchTab = "Overview" | "Financials" | "News" | "Filings" | "Notes";

type PortfolioItem = {
  ticker: string;
  listName: string;
  shares?: number;
  averageCost?: number;
  targetAllocation?: number;
  positionNotes?: string;
  updatedAt?: number;
  savedAt: number;
  stock: ResearchBundle["stock"] | null;
};

type PortfolioPositionInput = {
  ticker: string;
  shares: number;
  averageCost: number;
  targetAllocation: number;
  positionNotes: string;
  listName?: string;
};

type NoteInput = {
  ticker: string;
  title: string;
  body: string;
  tag: string;
};

type NoteDeleteInput = {
  noteId?: string;
  ticker: string;
  title: string;
  createdAt: number;
};

type NoteStatus = "idle" | "saving" | "deleting" | "generating" | "success" | "error";

type ListSummary = {
  name: string;
  count: number;
};

type CompareEntry = {
  ticker: string;
  stock: ResearchBundle["stock"] | null;
  aiReport?: ResearchBundle["aiReport"] | null;
  investmentThesis?: ResearchBundle["investmentThesis"] | null;
  financialReport?: ResearchBundle["financialReport"] | null;
  latestSnapshot?: NonNullable<ResearchBundle["snapshots"]>[number] | null;
  performanceSinceFirstSnapshot: number | null;
  snapshotCount: number;
};

type ScreenerPreset =
  | "All"
  | "Momentum"
  | "Mega Cap"
  | "Reasonable P/E"
  | "Dividend"
  | "With Positions"
  | "Needs Research";

type FinnhubSearchResult = {
  symbol: string;
  displaySymbol: string;
  description: string;
  type: string;
};

type DataSourceStatus = "success" | "error" | "fallback";

type DataSourceEventInput = {
  service: string;
  operation: string;
  status: DataSourceStatus;
  provider: string;
  fallbackProvider?: string;
  ticker?: string;
  message?: string;
  requestUrl?: string;
  requestedAt?: number;
  calledAt?: number;
};

type DataSourceHealth = {
  dateKey: string;
  usage: Array<{
    service: string;
    dateKey: string;
    count: number;
    successCount: number;
    errorCount: number;
    fallbackCount: number;
    lastStatus: DataSourceStatus;
    lastProvider: string;
    lastFallbackProvider?: string;
    lastMessage?: string;
    lastRequestUrl?: string;
    lastRequestedAt?: number;
    lastCalledAt: number;
  }>;
  events: Array<{
    service: string;
    operation: string;
    status: DataSourceStatus;
    provider: string;
    fallbackProvider?: string;
    ticker?: string;
    message?: string;
    requestUrl?: string;
    requestedAt?: number;
    dateKey: string;
    calledAt: number;
  }>;
};

const navItems: Array<{
  label: string;
  icon: typeof Search;
  view?: AppView;
  tab?: ResearchTab;
}> = [
  { label: "Research", icon: Search, view: "research" },
  { label: "Watchlist", icon: Star, view: "watchlist" },
  { label: "Portfolio", icon: BriefcaseBusiness, view: "portfolio" },
  { label: "Compare", icon: BarChart3, view: "compare" },
  { label: "Data Health", icon: Settings, view: "data-health" },
  { label: "Screener", icon: Filter, view: "screener" },
  { label: "Markets", icon: Globe2 },
  { label: "Calendar", icon: CalendarDays },
  { label: "Alerts", icon: Bell },
  { label: "Notes", icon: FileText, tab: "Notes" },
];

const defaultListNames = [
  "AI Leaders",
  "Semiconductors",
  "Long Term Core",
  "Dividend Growth",
];

const twelveDataClientKey = import.meta.env.VITE_TWELVE_DATA_API_KEY as
  | string
  | undefined;

let clientDataSourceRecorder: (event: DataSourceEventInput) => void = () => undefined;
let clientDataSourceEventQueue = Promise.resolve();

function emitClientDataSourceEvent(event: DataSourceEventInput) {
  clientDataSourceRecorder({
    ...event,
    calledAt: event.calledAt ?? Date.now(),
  });
}

function getTodayDateKey() {
  return new Date().toISOString().slice(0, 10);
}


const marketIndexes = [
  ["S&P 500", "5,308.15", "+0.41%", "up"],
  ["NASDAQ", "16,742.39", "+0.67%", "up"],
  ["DOW 30", "38,686.32", "-0.12%", "down"],
];

const researchTabs: ResearchTab[] = [
  "Overview",
  "Financials",
  "News",
  "Filings",
  "Notes",
];

async function fetchChartHistoryFromClientProviders(
  symbol: string
) {
  if (twelveDataClientKey) {
    try {
      const url = new URL("https://api.twelvedata.com/time_series");
      url.searchParams.set("symbol", symbol);
      url.searchParams.set("interval", "1day");
      url.searchParams.set("outputsize", "365");
      url.searchParams.set("apikey", twelveDataClientKey);

      const response = await fetch(url);
      const data = (await response.json()) as {
        values?: Array<{ close?: string }>;
        status?: string;
        code?: number;
        message?: string;
      };

      if (!response.ok || data.status === "error" || data.code || data.message) {
        throw new Error("Twelve Data unavailable");
      }

      emitClientDataSourceEvent({
        service: "Twelve Data",
        operation: "client_time_series",
        status: "success",
        provider: "Twelve Data",
        ticker: symbol,
      });

      const points = (data.values ?? [])
        .slice()
        .reverse()
        .map((item) => Number(item.close))
        .filter((point) => Number.isFinite(point))
        .slice(-365);

      if (points.length >= 2) {
        return points;
      }
    } catch (error) {
      emitClientDataSourceEvent({
        service: "Twelve Data",
        operation: "client_time_series",
        status: "error",
        provider: "Twelve Data",
        ticker: symbol,
        message: error instanceof Error ? error.message : "Twelve Data chart fetch failed.",
      });
      return undefined;
    }
  }

  return undefined;
}

/* Removed from the runtime: legacy browser-side Alpha Vantage request queue and
   financial statement cache. Financial data now refreshes through Convex.
const wait = (durationMs: number) =>
  new Promise((resolve) => window.setTimeout(resolve, durationMs));

let alphaVantageClientGlobalNextAllowedAt = 0;
let alphaVantageClientQueue: Promise<number | undefined> = Promise.resolve(undefined);

function chooseAlphaVantageClientKey(keySlots: AlphaVantageClientKeySlot[]) {
  return keySlots
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
}

async function scheduleAlphaVantageClientRequest(keySlot: AlphaVantageClientKeySlot) {
  const run = async () => {
    const waitMs = Math.max(
      alphaVantageClientGlobalNextAllowedAt - Date.now(),
      keySlot.nextAllowedAt - Date.now(),
      0
    );
    if (waitMs > 0) {
      await wait(waitMs);
    }

    const requestedAt = Date.now();
    alphaVantageClientGlobalNextAllowedAt =
      requestedAt + alphaVantageClientGlobalSpacingMs;
    keySlot.lastRequestedAt = requestedAt;
    keySlot.lastCalledAt = requestedAt;
    keySlot.nextAllowedAt = requestedAt + alphaVantageClientPerKeySpacingMs;
    keySlot.count += 1;
    return requestedAt;
  };

  const scheduled = alphaVantageClientQueue.then(run, run);
  alphaVantageClientQueue = scheduled.catch(() => undefined);
  return await scheduled;
}

const financialCacheKey = (symbol: string) =>
  `stock-app-financial-report:${symbol.toUpperCase()}`;

function readCachedFinancialReport(symbol: string) {
  try {
    const rawValue = window.sessionStorage.getItem(financialCacheKey(symbol));
    if (!rawValue) {
      return null;
    }

    const parsed = JSON.parse(rawValue) as CachedFinancialReport;
    const maxAgeMs = 12 * 60 * 60 * 1000;
    if (Date.now() - parsed.cachedAt > maxAgeMs) {
      window.sessionStorage.removeItem(financialCacheKey(symbol));
      return null;
    }

    return parsed;
  } catch {
    return null;
  }
}

function writeCachedFinancialReport(
  symbol: string,
  report: NonNullable<ResearchBundle["financialReport"]>,
  usedSecondaryKey: boolean
) {
  try {
    const payload: CachedFinancialReport = {
      cachedAt: Date.now(),
      report,
      usedSecondaryKey,
    };
    window.sessionStorage.setItem(financialCacheKey(symbol), JSON.stringify(payload));
  } catch {
    // Ignore cache write failures.
  }
}

async function fetchAlphaVantageClientJson<T>(
  symbol: string,
  fn: string,
  keySlot: AlphaVantageClientKeySlot
) {
  const requestedAt = await scheduleAlphaVantageClientRequest(keySlot);

  const url = new URL("https://www.alphavantage.co/query");
  url.searchParams.set("function", fn);
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("apikey", keySlot.apiKey);
  const requestUrl = redactApiUrl(url);

  const response = await fetch(url);
  if (!response.ok) {
    emitClientDataSourceEvent({
      service: keySlot.label,
      operation: `client_${fn}`,
      status: "error",
      provider: "Alpha Vantage",
      ticker: symbol,
      message: `Alpha Vantage ${fn} failed.`,
      requestUrl,
      requestedAt,
    });
    throw new Error(`Alpha Vantage ${fn} failed.`);
  }

  const data = (await response.json()) as T & {
    Note?: string;
    Information?: string;
    "Error Message"?: string;
  };

  if (data.Note || data.Information || data["Error Message"]) {
    const message =
      data.Note || data.Information || data["Error Message"] || "Alpha Vantage unavailable.";
    if (message.includes("1 request per second")) {
      alphaVantageClientGlobalNextAllowedAt = Math.max(
        alphaVantageClientGlobalNextAllowedAt,
        Date.now() + alphaVantageClientGlobalSpacingMs
      );
    }
    emitClientDataSourceEvent({
      service: keySlot.label,
      operation: `client_${fn}`,
      status: "error",
      provider: "Alpha Vantage",
      ticker: symbol,
      message,
      requestUrl,
      requestedAt,
    });
    throw toAlphaVantageClientError(message);
  }

  emitClientDataSourceEvent({
    service: keySlot.label,
    operation: `client_${fn}`,
    status: "success",
    provider: "Alpha Vantage",
    ticker: symbol,
    requestUrl,
    requestedAt,
  });

  return data;
}

async function fetchAlphaVantageClientJsonWithRetry<T>(
  symbol: string,
  fn: string,
  keySlot: AlphaVantageClientKeySlot
) {
  let lastError: unknown;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await fetchAlphaVantageClientJson<T>(symbol, fn, keySlot);
    } catch (error) {
      lastError = error;
      if (error instanceof AlphaVantageDailyLimitError) {
        throw error;
      }
      if (attempt < 2) {
        await wait(1_500);
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error(`Alpha Vantage ${fn} failed.`);
}

async function fetchAlphaVantageClientJsonWithRotation<T>(
  symbol: string,
  fn: string,
  keySlots: AlphaVantageClientKeySlot[]
) {
  let lastError: unknown;
  let previousKeySlot: AlphaVantageClientKeySlot | undefined;

  for (let attempt = 0; attempt < keySlots.length; attempt += 1) {
    const keySlot = chooseAlphaVantageClientKey(keySlots);
    if (!keySlot) {
      break;
    }

    try {
      if (previousKeySlot) {
        emitClientDataSourceEvent({
          service: keySlot.label,
          operation: `client_${fn}_rotation`,
          status: "fallback",
          provider: previousKeySlot.label,
          fallbackProvider: keySlot.label,
          ticker: symbol,
          message: `${previousKeySlot.label} reached the daily Alpha Vantage limit; trying ${keySlot.label}.`,
        });
      }

      const data = await fetchAlphaVantageClientJsonWithRetry<T>(
        symbol,
        fn,
        keySlot
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
    : new Error(`Unable to load ${fn} from Alpha Vantage.`);
}

*/

function formatAbbreviatedFinancialValue(rawValue?: string) {
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
}

/* Removed from the runtime: legacy browser-side FMP and Alpha Vantage
   statement adapters. The equivalent provider adapters live in Convex.
function formatFinancialRatio(rawValue?: string) {
  if (!rawValue || rawValue === "None") {
    return "N/A";
  }

  const numeric = Number(rawValue);
  return Number.isFinite(numeric) ? numeric.toFixed(2) : "N/A";
}

function formatFinancialPercent(rawValue?: string) {
  if (!rawValue || rawValue === "None") {
    return "N/A";
  }

  const numeric = Number(rawValue);
  if (!Number.isFinite(numeric)) {
    return "N/A";
  }

  const normalized = numeric <= 1 ? numeric * 100 : numeric;
  return `${normalized.toFixed(2)}%`;
}

function formatFinancialCurrency(rawValue?: string) {
  if (!rawValue || rawValue === "None") {
    return "N/A";
  }

  const numeric = Number(rawValue);
  return Number.isFinite(numeric) ? `$${numeric.toFixed(2)}` : "N/A";
}

function toFinancialReportPeriod(
  income?: AlphaVantageStatementClient,
  balance?: AlphaVantageStatementClient,
  cash?: AlphaVantageStatementClient
) {
  const operatingCashflow = cash?.operatingCashflow;
  const capitalExpenditures = cash?.capitalExpenditures;
  const freeCashFlowValue =
    Number(operatingCashflow) - Math.abs(Number(capitalExpenditures));

  return {
    fiscalDateEnding:
      income?.fiscalDateEnding || balance?.fiscalDateEnding || cash?.fiscalDateEnding || "N/A",
    totalRevenue: formatAbbreviatedFinancialValue(income?.totalRevenue),
    grossProfit: formatAbbreviatedFinancialValue(income?.grossProfit),
    operatingIncome: formatAbbreviatedFinancialValue(income?.operatingIncome),
    netIncome: formatAbbreviatedFinancialValue(income?.netIncome),
    dilutedEps: formatFinancialRatio(income?.dilutedEPS),
    operatingCashflow: formatAbbreviatedFinancialValue(operatingCashflow),
    capitalExpenditures: formatAbbreviatedFinancialValue(capitalExpenditures),
    freeCashFlow: Number.isFinite(freeCashFlowValue)
      ? formatAbbreviatedFinancialValue(String(freeCashFlowValue))
      : "N/A",
    totalAssets: formatAbbreviatedFinancialValue(balance?.totalAssets),
    totalLiabilities: formatAbbreviatedFinancialValue(balance?.totalLiabilities),
    totalShareholderEquity: formatAbbreviatedFinancialValue(balance?.totalShareholderEquity),
  };
}

function fmpValue(value?: number | string) {
  return value === undefined || value === null ? undefined : String(value);
}

function toFmpFinancialReportPeriod(
  income?: FmpStatementClient,
  balance?: FmpStatementClient,
  cash?: FmpStatementClient
) {
  const operatingCashflow = cash?.operatingCashFlow ?? cash?.operatingCashflow;
  const capitalExpenditures = cash?.capitalExpenditure ?? cash?.capitalExpenditures;
  const freeCashFlowValue =
    cash?.freeCashFlow ??
    Number(operatingCashflow) - Math.abs(Number(capitalExpenditures));

  return {
    fiscalDateEnding: income?.date || balance?.date || cash?.date || "N/A",
    totalRevenue: formatAbbreviatedFinancialValue(fmpValue(income?.revenue)),
    grossProfit: formatAbbreviatedFinancialValue(fmpValue(income?.grossProfit)),
    operatingIncome: formatAbbreviatedFinancialValue(fmpValue(income?.operatingIncome)),
    netIncome: formatAbbreviatedFinancialValue(fmpValue(income?.netIncome)),
    dilutedEps: formatFinancialRatio(fmpValue(income?.epsdiluted ?? income?.epsDiluted)),
    operatingCashflow: formatAbbreviatedFinancialValue(fmpValue(operatingCashflow)),
    capitalExpenditures: formatAbbreviatedFinancialValue(fmpValue(capitalExpenditures)),
    freeCashFlow: Number.isFinite(freeCashFlowValue)
      ? formatAbbreviatedFinancialValue(String(freeCashFlowValue))
      : "N/A",
    totalAssets: formatAbbreviatedFinancialValue(fmpValue(balance?.totalAssets)),
    totalLiabilities: formatAbbreviatedFinancialValue(fmpValue(balance?.totalLiabilities)),
    totalShareholderEquity: formatAbbreviatedFinancialValue(
      fmpValue(balance?.totalStockholdersEquity ?? balance?.totalShareholderEquity)
    ),
  };
}

function buildFmpFinancialReport(
  income: FmpStatementClient[],
  balance: FmpStatementClient[],
  cash: FmpStatementClient[],
  ratios: FmpRatioClient[] = [],
  keyMetrics: FmpKeyMetricClient[] = []
): NonNullable<ResearchBundle["financialReport"]> | undefined {
  const quarterlyIncome = income.filter((item) => item.period !== "FY").slice(0, 4);
  const annualIncome = income.filter((item) => item.period === "FY").slice(0, 4);
  const quarterlyBalance = balance.filter((item) => item.period !== "FY");
  const annualBalance = balance.filter((item) => item.period === "FY");
  const quarterlyCash = cash.filter((item) => item.period !== "FY");
  const annualCash = cash.filter((item) => item.period === "FY");

  const quarterly = quarterlyIncome.map((item, index) =>
    toFmpFinancialReportPeriod(item, quarterlyBalance[index], quarterlyCash[index])
  );
  const annual = annualIncome.map((item, index) =>
    toFmpFinancialReportPeriod(item, annualBalance[index], annualCash[index])
  );

  if (!quarterly.length && !annual.length) {
    return undefined;
  }

  const latestIncome = income[0];
  const latestRatio = ratios[0];
  const latestMetric = keyMetrics[0];

  return {
    source: "Financial Modeling Prep",
    currency: latestIncome?.reportedCurrency || "USD",
    fiscalYearEnd: latestIncome?.calendarYear || "N/A",
    latestQuarter: latestIncome?.date || "N/A",
    profitMargin: formatFinancialPercent(fmpValue(latestRatio?.netProfitMarginTTM)),
    operatingMarginTtm: formatFinancialPercent(fmpValue(latestRatio?.operatingProfitMarginTTM)),
    returnOnEquityTtm: formatFinancialPercent(fmpValue(latestRatio?.returnOnEquityTTM)),
    priceToBookRatio: formatFinancialRatio(fmpValue(latestRatio?.priceToBookRatioTTM)),
    evToRevenue: formatFinancialRatio(
      fmpValue(latestMetric?.evToRevenueTTM ?? latestMetric?.evToSalesTTM)
    ),
    evToEbitda: formatFinancialRatio(fmpValue(latestMetric?.enterpriseValueMultipleTTM)),
    beta: "N/A",
    analystTargetPrice: "N/A",
    quarterly,
    annual,
    updatedAt: Date.now(),
  };
}

async function fetchFmpClientJson<T>(
  symbol: string,
  path: string,
  params: Record<string, string> = {}
) {
  if (!fmpClientKey) {
    throw new Error("Financial Modeling Prep key is missing.");
  }

  const url = new URL(`https://financialmodelingprep.com/stable/${path}`);
  url.searchParams.set("symbol", symbol);
  Object.entries(params).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });
  url.searchParams.set("apikey", fmpClientKey);

  const response = await fetch(url);
  const data = (await response.json()) as T & {
    Error?: string;
    error?: string;
    message?: string;
  };

  if (!response.ok || data.Error || data.error || data.message) {
    const message =
      data.Error || data.error || data.message || `FMP ${path} failed with ${response.status}.`;
    emitClientDataSourceEvent({
      service: "Financial Modeling Prep",
      operation: `client_${path}`,
      status: "error",
      provider: "Financial Modeling Prep",
      ticker: symbol,
      message,
    });
    throw new Error(message);
  }

  emitClientDataSourceEvent({
    service: "Financial Modeling Prep",
    operation: `client_${path}`,
    status: "success",
    provider: "Financial Modeling Prep",
    ticker: symbol,
  });

  return data;
}

async function fetchFmpFinancialReportFromClient(symbol: string) {
  const [
    annualIncome,
    annualBalance,
    annualCash,
    quarterlyIncome,
    quarterlyBalance,
    quarterlyCash,
    ratios,
    keyMetrics,
  ] = await Promise.all([
    fetchFmpClientJson<FmpStatementClient[]>(symbol, "income-statement"),
    fetchFmpClientJson<FmpStatementClient[]>(symbol, "balance-sheet-statement"),
    fetchFmpClientJson<FmpStatementClient[]>(symbol, "cash-flow-statement"),
    fetchFmpClientJson<FmpStatementClient[]>(symbol, "income-statement", {
      period: "quarter",
    }).catch(() => []),
    fetchFmpClientJson<FmpStatementClient[]>(symbol, "balance-sheet-statement", {
      period: "quarter",
    }).catch(() => []),
    fetchFmpClientJson<FmpStatementClient[]>(symbol, "cash-flow-statement", {
      period: "quarter",
    }).catch(() => []),
    fetchFmpClientJson<FmpRatioClient[]>(symbol, "ratios-ttm").catch(() => []),
    fetchFmpClientJson<FmpKeyMetricClient[]>(symbol, "key-metrics-ttm").catch(() => []),
  ]);

  const report = buildFmpFinancialReport(
    [...quarterlyIncome, ...annualIncome],
    [...quarterlyBalance, ...annualBalance],
    [...quarterlyCash, ...annualCash],
    ratios,
    keyMetrics
  );
  if (!report) {
    throw new Error(`Financial Modeling Prep did not return statement data for ${symbol}.`);
  }

  return report;
}

function buildClientFinancialReport(
  overview: AlphaVantageOverviewClient,
  income: AlphaVantageStatementResponseClient,
  balance: AlphaVantageStatementResponseClient,
  cash: AlphaVantageStatementResponseClient
): NonNullable<ResearchBundle["financialReport"]> {
  return {
    source: "Alpha Vantage",
    currency: overview.Currency || "USD",
    fiscalYearEnd: overview.FiscalYearEnd || "N/A",
    latestQuarter: overview.LatestQuarter || "N/A",
    profitMargin: formatFinancialPercent(overview.ProfitMargin),
    operatingMarginTtm: formatFinancialPercent(overview.OperatingMarginTTM),
    returnOnEquityTtm: formatFinancialPercent(overview.ReturnOnEquityTTM),
    priceToBookRatio: formatFinancialRatio(overview.PriceToBookRatio),
    evToRevenue: formatFinancialRatio(overview.EVToRevenue),
    evToEbitda: formatFinancialRatio(overview.EVToEBITDA),
    beta: formatFinancialRatio(overview.Beta),
    analystTargetPrice: formatFinancialCurrency(overview.AnalystTargetPrice),
    quarterly: (income.quarterlyReports ?? []).slice(0, 4).map((item, index) =>
      toFinancialReportPeriod(
        item,
        balance.quarterlyReports?.[index],
        cash.quarterlyReports?.[index]
      )
    ),
    annual: (income.annualReports ?? []).slice(0, 4).map((item, index) =>
      toFinancialReportPeriod(item, balance.annualReports?.[index], cash.annualReports?.[index])
    ),
    updatedAt: Date.now(),
  };
}

async function fetchFinancialReportFromClient(
  symbol: string,
  health?: DataSourceHealth
) {
  if (fmpClientKey) {
    try {
      return {
        report: await fetchFmpFinancialReportFromClient(symbol),
        usedSecondaryKey: false,
      };
    } catch (error) {
      emitClientDataSourceEvent({
        service: "Financials Fallback",
        operation: "client_financials",
        status: "fallback",
        provider: "Financial Modeling Prep",
        fallbackProvider: "Alpha Vantage",
        ticker: symbol,
        message:
          error instanceof Error
            ? error.message
            : "FMP financial sync failed; trying Alpha Vantage.",
      });
    }
  }

  const alphaVantageClientKeys = orderAlphaVantageClientKeysByUsage(health);
  let usedSecondaryKey = false;

  if (!alphaVantageClientKeys.length) {
    throw new Error("Unable to load financial statements from Alpha Vantage.");
  }

  const overviewResult = await fetchAlphaVantageClientJsonWithRotation<AlphaVantageOverviewClient>(
    symbol,
    "OVERVIEW",
    alphaVantageClientKeys
  );
  usedSecondaryKey = usedSecondaryKey || overviewResult.usedSecondaryKey;

  const incomeResult = await fetchAlphaVantageClientJsonWithRotation<AlphaVantageStatementResponseClient>(
    symbol,
    "INCOME_STATEMENT",
    alphaVantageClientKeys
  );
  usedSecondaryKey = usedSecondaryKey || incomeResult.usedSecondaryKey;

  const balanceResult = await fetchAlphaVantageClientJsonWithRotation<AlphaVantageStatementResponseClient>(
    symbol,
    "BALANCE_SHEET",
    alphaVantageClientKeys
  );
  usedSecondaryKey = usedSecondaryKey || balanceResult.usedSecondaryKey;

  const cashResult = await fetchAlphaVantageClientJsonWithRotation<AlphaVantageStatementResponseClient>(
    symbol,
    "CASH_FLOW",
    alphaVantageClientKeys
  );
  usedSecondaryKey = usedSecondaryKey || cashResult.usedSecondaryKey;

  return {
    report: buildClientFinancialReport(
      overviewResult.data,
      incomeResult.data,
      balanceResult.data,
      cashResult.data
    ),
    usedSecondaryKey,
  };
}

*/

function getListSummaries(
  items: Array<{ listName: string }>,
  listNames: string[]
): ListSummary[] {
  const counts = new Map<string, number>();
  for (const name of listNames) {
    counts.set(name, 0);
  }

  for (const item of items) {
    counts.set(item.listName, (counts.get(item.listName) ?? 0) + 1);
  }

  return [
    { name: "All", count: items.length },
    ...Array.from(counts.entries()).map(([name, count]) => ({ name, count })),
  ];
}

function buildCompareEntryFromBundle(
  ticker: string,
  bundle: ResearchBundle | undefined
): CompareEntry | null {
  if (!bundle?.stock) {
    return null;
  }

  const snapshots = bundle.snapshots ?? [];
  const latestSnapshot = snapshots[0] ?? null;
  const baselineSnapshot = snapshots[snapshots.length - 1] ?? latestSnapshot;
  const performanceSinceFirstSnapshot =
    latestSnapshot && baselineSnapshot && baselineSnapshot.price > 0
      ? ((latestSnapshot.price - baselineSnapshot.price) / baselineSnapshot.price) *
        100
      : null;

  return {
    ticker,
    stock: bundle.stock,
    aiReport: bundle.aiReport ?? null,
    investmentThesis: bundle.investmentThesis ?? null,
    financialReport: bundle.financialReport ?? null,
    latestSnapshot,
    performanceSinceFirstSnapshot,
    snapshotCount: snapshots.length,
  };
}

const summarizeRuntimeError = (errorMessage: string) => {
  if (errorMessage.includes("Could not find public function")) {
    return "The frontend is calling a newer Convex function than the current dev deployment exposes. Restart `npx convex dev` so the latest backend functions are published.";
  }

  const firstLine = errorMessage.split("\n").find((line) => line.trim());
  return firstLine ?? "The live backend is temporarily unavailable.";
};

class ConvexRuntimeGuard extends Component<
  ConvexRuntimeGuardProps,
  ConvexRuntimeGuardState
> {
  state: ConvexRuntimeGuardState = {
    errorMessage: null,
  };

  static getDerivedStateFromError(error: unknown): ConvexRuntimeGuardState {
    return {
      errorMessage:
        error instanceof Error
          ? error.message
          : "The live backend is temporarily unavailable.",
    };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("Convex runtime guard caught an error.", error, info);
  }

  render() {
    if (!this.state.errorMessage) {
      return this.props.children;
    }

    const isFunctionMismatch = this.state.errorMessage.includes(
      "Could not find public function"
    );

    return (
      <>
        <div className="runtime-banner">
          <div className="runtime-banner-copy">
            <strong>
              {isFunctionMismatch
                ? "Convex backend needs refresh"
                : "Live backend unavailable"}
            </strong>
            <span>{summarizeRuntimeError(this.state.errorMessage)}</span>
          </div>
          <button
            className="secondary-button compact"
            onClick={() => window.location.reload()}
            type="button"
          >
            Reload app
          </button>
        </div>
        <StaticResearchApp />
      </>
    );
  }
}

export default function App({ convexEnabled }: AppProps) {
  if (convexEnabled) {
    return (
      <ConvexRuntimeGuard>
        <ConvexResearchApp />
      </ConvexRuntimeGuard>
    );
  }

  return <StaticResearchApp />;
}

function ConvexResearchApp() {
  const [ticker, setTicker] = useState("NVDA");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeView, setActiveView] = useState<AppView>("research");
  const [compareTickers, setCompareTickers] = useState<string[]>([]);
  const [selectedList, setSelectedList] = useState("All");
  const [selectedListName, setSelectedListName] = useState(defaultListNames[0]);
  const normalizedSearchQuery = searchQuery.trim();
  const bundle = useQuery(api.stocks.researchBundle, { ticker });
  const portfolio = (useQuery(api.stocks.portfolio) ?? []) as PortfolioItem[];
  const dataSourceHealth = useQuery(api.dataSources.healthDashboard, {
    dateKey: getTodayDateKey(),
  }) as DataSourceHealth | undefined;
  const liveCompareEntries =
    useQuery(
      api.stocks.compareCompanies,
      compareTickers.length ? { tickers: compareTickers } : "skip"
    ) ?? [];
  const watchlists = useQuery(api.stocks.watchlists);
  const fetchedSearchResults = useQuery(
    api.stocks.search,
    normalizedSearchQuery ? { query: normalizedSearchQuery } : "skip"
  );
  const searchResults = normalizedSearchQuery
    ? (fetchedSearchResults ?? searchableStocks)
    : [];
  const saveToPortfolio = useMutation(api.stocks.saveToPortfolio);
  const removeFromPortfolio = useMutation(api.stocks.removeFromPortfolio);
  const updatePortfolioList = useMutation(api.stocks.updatePortfolioList);
  const updatePortfolioPosition = useMutation(api.stocks.updatePortfolioPosition);
  const recordClientDataSourceEvent = useMutation(api.dataSources.recordClientEvent);
  const initializeWatchlists = useMutation(api.stocks.initializeWatchlists);
  const createWatchlist = useMutation(api.stocks.createWatchlist);
  const renameWatchlist = useMutation(api.stocks.renameWatchlist);
  const deleteWatchlist = useMutation(api.stocks.deleteWatchlist);
  const syncTicker = useAction(api.marketData.syncTicker);
  const syncFinancials = useAction(api.marketData.syncFinancials);
  const saveAiReport = useMutation(api.stocks.saveAiReport);
  const createNote = useMutation(api.stocks.createNote);
  const deleteNote = useMutation(api.stocks.deleteNote);
  const saveInvestmentThesis = useMutation(api.stocks.saveInvestmentThesis);
  const searchFinnhubSymbols = useAction(api.marketData.searchSymbols);
  const [syncStatus, setSyncStatus] = useState<
    "idle" | "syncing" | "success" | "error"
  >("idle");
  const [syncMessage, setSyncMessage] = useState("");
  const [aiReportStatus, setAiReportStatus] = useState<
    "idle" | "generating" | "success" | "error"
  >("idle");
  const [aiReportMessage, setAiReportMessage] = useState("");
  const [noteStatus, setNoteStatus] = useState<NoteStatus>("idle");
  const [noteMessage, setNoteMessage] = useState("");
  const [thesisStatus, setThesisStatus] = useState<
    "idle" | "proposing" | "saving" | "success" | "error"
  >("idle");
  const [thesisMessage, setThesisMessage] = useState("");
  const [finnhubResults, setFinnhubResults] = useState<FinnhubSearchResult[]>([]);
  const [finnhubSearchStatus, setFinnhubSearchStatus] = useState<
    "idle" | "searching" | "success" | "error"
  >("idle");
  const [finnhubSearchMessage, setFinnhubSearchMessage] = useState("");
  const listNames = useMemo(() => {
    const names = watchlists?.map((item) => item.name) ?? [];
    return names.length ? names : defaultListNames;
  }, [watchlists]);

  useEffect(() => {
    clientDataSourceRecorder = (event) => {
      clientDataSourceEventQueue = clientDataSourceEventQueue
        .catch(() => undefined)
        .then(() => recordClientDataSourceEvent(event))
        .then(
          () => undefined,
          (error) => {
            console.warn("Unable to record data source event", error);
          }
        );
    };

    return () => {
      clientDataSourceRecorder = () => undefined;
    };
  }, [recordClientDataSourceEvent]);

  useEffect(() => {
    if (watchlists && watchlists.length === 0) {
      void initializeWatchlists({ listNames: defaultListNames });
    }
  }, [initializeWatchlists, watchlists]);

  useEffect(() => {
    if (!listNames.includes(selectedListName)) {
      setSelectedListName(listNames[0] ?? defaultListNames[0]);
    }
  }, [listNames, selectedListName]);

  useEffect(() => {
    if (selectedList !== "All" && !listNames.includes(selectedList)) {
      setSelectedList("All");
    }
  }, [listNames, selectedList]);

  useEffect(() => {
    const portfolioTickers = new Set(portfolio.map((item) => item.ticker));
    setCompareTickers((current) =>
      current.filter((item) => portfolioTickers.has(item)).slice(0, 4)
    );
  }, [portfolio]);

  const fallbackBundle = useMemo<ResearchBundle>(() => {
    if (!bundle?.stock) {
      return { ...demoBundle, isSaved: false };
    }

    return {
      stock: bundle.stock,
      news: bundle.news,
      notes: bundle.notes,
      researchItems: bundle.researchItems,
      financialReport: bundle.financialReport ?? undefined,
      aiReport: bundle.aiReport ?? undefined,
      investmentThesis: bundle.investmentThesis ?? undefined,
      snapshots: bundle.snapshots ?? [],
      isSaved: bundle.isSaved,
    };
  }, [bundle]);

  const onSaveToggle = async () => {
    if (fallbackBundle.isSaved) {
      await removeFromPortfolio({ ticker });
      return;
    }

    await saveToPortfolio({ ticker, listName: selectedListName });
  };

  const onSelectedListNameChange = async (listName: string) => {
    setSelectedListName(listName);

    if (fallbackBundle.isSaved) {
      await updatePortfolioList({ ticker, listName });
    }
  };

  const onUpdatePortfolioPosition = async (input: PortfolioPositionInput) => {
    await updatePortfolioPosition(input);
  };

  const onCreateList = async (name: string) => {
    await createWatchlist({ name });
    setSelectedListName(name.trim());
  };

  const onRenameList = async (currentName: string, nextName: string) => {
    const normalized = nextName.trim();
    await renameWatchlist({ currentName, nextName: normalized });
    if (selectedList === currentName) {
      setSelectedList(normalized);
    }
    if (selectedListName === currentName) {
      setSelectedListName(normalized);
    }
  };

  const onDeleteList = async (name: string, fallbackListName?: string) => {
    await deleteWatchlist({ name, fallbackListName });
    if (selectedList === name) {
      setSelectedList("All");
    }
    if (selectedListName === name) {
      const nextName =
        listNames.find((item) => item !== name && item !== fallbackListName) ??
        fallbackListName ??
        defaultListNames[0];
      setSelectedListName(nextName);
    }
  };

  const onSyncMarketData = async () => {
    setSyncStatus("syncing");
    setSyncMessage(`Syncing ${ticker} market data...`);

    try {
      const result = await syncTicker({ ticker });
      setSyncStatus("success");
      const baseMessage = result.hasChartData
        ? `${result.ticker} synced at $${result.price.toFixed(2)} with live chart data.`
        : `${result.ticker} quote synced at $${result.price.toFixed(2)}. Historical chart data is temporarily unavailable.`;
      const financialMessage = result.refreshedFinancials
        ? ` Financials were refreshed from ${result.financialSource ?? "the active provider"}${
            result.usedSecondaryAlphaKey ? " using a secondary Alpha Vantage key" : ""
          }.`
        : result.preservedStoredFinancials
          ? ` ${result.financialSource ?? "The active provider"} returned a lower-quality financial report, so the stronger stored report was preserved.`
        : result.usingCachedFinancials
          ? ` Showing cached financials${
              result.financialSource ? ` from ${result.financialSource}` : ""
            } because live fundamentals were unavailable.`
          : "";
      const newsMessage = result.relevantNewsCount
        ? ` ${result.relevantNewsCount} company-relevant headline${
            result.relevantNewsCount === 1 ? " was" : "s were"
          } kept; ${result.filteredNewsCount} unrelated or duplicate headline${
            result.filteredNewsCount === 1 ? " was" : "s were"
          } filtered.`
        : ` No company-specific headlines passed the relevance check; ${result.filteredNewsCount} candidate headline${
            result.filteredNewsCount === 1 ? " was" : "s were"
          } filtered.`;
      setSyncMessage(
        `${baseMessage}${financialMessage}${newsMessage} A research snapshot was saved for history.`
      );
    } catch (error) {
      setSyncStatus("error");
      setSyncMessage(
        error instanceof Error
          ? error.message
          : "Unable to sync market data from Finnhub."
      );
    }
  };

  const onSyncFinancials = async () => {
    setSyncStatus("syncing");
    setSyncMessage(`Refreshing ${ticker} financial statements in Convex...`);

    try {
      const result = await syncFinancials({ ticker });
      setSyncStatus("success");
      setSyncMessage(
        result.persisted
          ? `${result.ticker} financial statements refreshed from ${result.source}${
              result.usedSecondaryAlphaKey ? " using a secondary Alpha Vantage key" : ""
            }.`
          : `${result.ticker} returned lower-quality data from ${result.source}; the stronger stored report was preserved.`
      );
    } catch (error) {
      setSyncStatus("error");
      setSyncMessage(
        error instanceof Error
          ? error.message
          : "Unable to refresh financial statements in Convex."
      );
    }
  };

  const onSearchFinnhub = async (query: string) => {
    const trimmedQuery = query.trim();
    if (trimmedQuery.length < 2) {
      setFinnhubResults([]);
      setFinnhubSearchStatus("idle");
      setFinnhubSearchMessage("Type at least 2 characters to search Finnhub.");
      return;
    }

    setFinnhubSearchStatus("searching");
    setFinnhubSearchMessage(`Searching Finnhub for "${trimmedQuery}"...`);

    try {
      const results = await searchFinnhubSymbols({ query: trimmedQuery });
      setFinnhubResults(results);
      setFinnhubSearchStatus("success");
      setFinnhubSearchMessage(
        results.length
          ? `Found ${results.length} Finnhub result${results.length === 1 ? "" : "s"}.`
          : "No Finnhub matches found."
      );
    } catch (error) {
      setFinnhubResults([]);
      setFinnhubSearchStatus("error");
      setFinnhubSearchMessage(
        error instanceof Error ? error.message : "Unable to search Finnhub."
      );
    }
  };

  const onImportFinnhubSymbol = async (symbol: string) => {
    const nextTicker = symbol.trim().toUpperCase();
    if (!nextTicker) {
      return;
    }

    setFinnhubSearchStatus("searching");
    setFinnhubSearchMessage(`Importing ${nextTicker} from Finnhub...`);

    try {
      await syncTicker({ ticker: nextTicker });
      await saveToPortfolio({ ticker: nextTicker, listName: selectedListName });
      setTicker(nextTicker);
      setActiveView("research");
      setSearchQuery("");
      setFinnhubResults([]);
      setFinnhubSearchStatus("success");
      setFinnhubSearchMessage(
        `${nextTicker} imported and saved to ${selectedListName}.`
      );
    } catch (error) {
      setFinnhubSearchStatus("error");
      setFinnhubSearchMessage(
        error instanceof Error
          ? error.message
          : `Unable to import ${nextTicker} from Finnhub.`
      );
    }
  };

  const onSearchChange = (query: string) => {
    setSearchQuery(query);

    if (!query.trim()) {
      setFinnhubResults([]);
      setFinnhubSearchStatus("idle");
      setFinnhubSearchMessage("");
    }
  };

  const onGenerateAiResearchReport = async () => {
    setAiReportStatus("generating");
    setAiReportMessage(`Generating AI research report for ${ticker}...`);

    try {
      const response = await fetch("/local-ai/report", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ticker,
          asOf: new Date().toISOString(),
          stock: fallbackBundle.stock,
          news: fallbackBundle.news,
          notes: fallbackBundle.notes,
          researchItems: fallbackBundle.researchItems,
          investmentThesis: fallbackBundle.investmentThesis,
          financialReport: fallbackBundle.financialReport,
          snapshots: fallbackBundle.snapshots?.slice(0, 3) ?? [],
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "The local AI bridge failed.");
      }

      const result = (await response.json()) as {
        ticker: string;
        summary: string;
        bullPoints: string[];
        bearPoints: string[];
        thesisPoints: string[];
        watchItems: string[];
        provider: string;
        model: string;
        generatedAt: number;
      };

      await saveAiReport({
        ticker: result.ticker,
        summary: result.summary,
        bullPoints: result.bullPoints,
        bearPoints: result.bearPoints,
        thesisPoints: result.thesisPoints,
        watchItems: result.watchItems,
        provider: result.provider,
        model: result.model,
        generatedAt: result.generatedAt,
      });
      emitClientDataSourceEvent({
        service: "Local AI Bridge",
        operation: "ai_report",
        status: "success",
        provider: result.provider,
        ticker: result.ticker,
        message: result.model,
      });
      setAiReportStatus("success");
      setAiReportMessage(
        `${result.ticker} AI report generated with ${result.provider} (${result.model}).`
      );
    } catch (error) {
      emitClientDataSourceEvent({
        service: "Local AI Bridge",
        operation: "ai_report",
        status: "error",
        provider: "Local bridge",
        ticker,
        message:
          error instanceof Error ? error.message : "Unable to generate AI research report.",
      });
      setAiReportStatus("error");
      setAiReportMessage(
        error instanceof Error
          ? error.message
          : "Unable to generate AI research report."
      );
    }
  };

  const onProposeInvestmentThesis = async () => {
    setThesisStatus("proposing");
    setThesisMessage(`Proposing an investment thesis for ${ticker}...`);

    try {
      const response = await fetch("/local-ai/thesis", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ticker,
          stock: fallbackBundle.stock,
          news: fallbackBundle.news,
          notes: fallbackBundle.notes,
          researchItems: fallbackBundle.researchItems,
          aiReport: fallbackBundle.aiReport,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "The local thesis bridge failed.");
      }

      const result = (await response.json()) as {
        ticker: string;
        summary: string;
        thesisPoints: string[];
        watchItems: string[];
        source: string;
        generatedAt: number;
      };

      await saveInvestmentThesis({
        ticker: result.ticker,
        summary: result.summary,
        thesisPoints: result.thesisPoints,
        watchItems: result.watchItems,
        source: result.source,
        updatedAt: result.generatedAt,
      });

      emitClientDataSourceEvent({
        service: "Local AI Bridge",
        operation: "investment_thesis",
        status: "success",
        provider: result.source,
        ticker: result.ticker,
      });

      setThesisStatus("success");
      setThesisMessage(`${result.ticker} investment thesis proposed and saved.`);
    } catch (error) {
      emitClientDataSourceEvent({
        service: "Local AI Bridge",
        operation: "investment_thesis",
        status: "error",
        provider: "Local bridge",
        ticker,
        message:
          error instanceof Error ? error.message : "Unable to propose investment thesis.",
      });
      setThesisStatus("error");
      setThesisMessage(
        error instanceof Error ? error.message : "Unable to propose investment thesis."
      );
    }
  };

  const onSaveInvestmentThesisDraft = async (input: {
    summary: string;
    thesisPoints: string[];
    watchItems: string[];
  }) => {
    setThesisStatus("saving");
    setThesisMessage(`Saving investment thesis for ${ticker}...`);

    try {
      await saveInvestmentThesis({
        ticker,
        summary: input.summary,
        thesisPoints: input.thesisPoints,
        watchItems: input.watchItems,
        source: "Manual thesis",
        updatedAt: Date.now(),
      });
      setThesisStatus("success");
      setThesisMessage(`${ticker} investment thesis saved.`);
    } catch (error) {
      setThesisStatus("error");
      setThesisMessage(
        error instanceof Error ? error.message : "Unable to save investment thesis."
      );
    }
  };

  const onCreateNote = async (input: NoteInput) => {
    setNoteStatus("saving");
    setNoteMessage(`Saving note for ${input.ticker}...`);

    try {
      await createNote(input);
      setNoteStatus("success");
      setNoteMessage(`${input.ticker} note saved.`);
    } catch (error) {
      setNoteStatus("error");
      setNoteMessage(error instanceof Error ? error.message : "Unable to save note.");
    }
  };

  const onDeleteNote = async (input: NoteDeleteInput) => {
    if (!input.noteId) {
      setNoteStatus("error");
      setNoteMessage("This note cannot be deleted because it is missing a saved note id.");
      return;
    }

    if (!window.confirm(`Delete note "${input.title}"?`)) {
      return;
    }

    setNoteStatus("deleting");
    setNoteMessage(`Deleting note for ${input.ticker}...`);

    try {
      await deleteNote({ noteId: input.noteId as Id<"notes"> });
      setNoteStatus("success");
      setNoteMessage(`${input.ticker} note deleted.`);
    } catch (error) {
      setNoteStatus("error");
      setNoteMessage(error instanceof Error ? error.message : "Unable to delete note.");
    }
  };

  const onGenerateAiNotes = async () => {
    setNoteStatus("generating");
    setNoteMessage(`Asking the local LLM to generate practical notes for ${ticker}...`);

    try {
      const response = await fetch("/local-ai/notes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ticker,
          stock: fallbackBundle.stock,
          news: fallbackBundle.news,
          notes: fallbackBundle.notes,
          researchItems: fallbackBundle.researchItems,
          aiReport: fallbackBundle.aiReport,
          investmentThesis: fallbackBundle.investmentThesis,
          financialReport: fallbackBundle.financialReport,
          snapshots: fallbackBundle.snapshots?.slice(0, 5) ?? [],
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "The local notes bridge failed.");
      }

      const result = (await response.json()) as {
        ticker: string;
        notes: Array<{ title: string; body: string; tag: string }>;
        provider: string;
        model: string;
      };

      const existingTitles = new Set(
        fallbackBundle.notes.map((note) => note.title.trim().toLowerCase())
      );
      const newNotes = result.notes.filter((note) => {
        const normalizedTitle = note.title.trim().toLowerCase();
        if (!normalizedTitle || existingTitles.has(normalizedTitle)) {
          return false;
        }
        existingTitles.add(normalizedTitle);
        return true;
      });

      for (const note of newNotes) {
        await createNote({
          ticker: result.ticker,
          title: note.title,
          body: note.body,
          tag: note.tag,
        });
      }

      emitClientDataSourceEvent({
        service: "Local AI Bridge",
        operation: "ai_notes",
        status: "success",
        provider: result.provider,
        ticker: result.ticker,
        message: result.model,
      });
      setNoteStatus("success");
      setNoteMessage(
        newNotes.length
          ? `${newNotes.length} practical AI note${newNotes.length === 1 ? "" : "s"} created for ${ticker} with ${result.provider} (${result.model}).`
          : `${ticker} already has these LLM-generated notes.`
      );
    } catch (error) {
      emitClientDataSourceEvent({
        service: "Local AI Bridge",
        operation: "ai_notes",
        status: "error",
        provider: "Local bridge",
        ticker,
        message: error instanceof Error ? error.message : "Unable to generate AI notes.",
      });
      setNoteStatus("error");
      setNoteMessage(
        error instanceof Error ? error.message : "Unable to generate AI notes."
      );
    }
  };

  const compareEntries = useMemo<CompareEntry[]>(
    () =>
      liveCompareEntries.map((entry) => ({
        ticker: entry.ticker,
        stock: entry.stock ?? null,
        aiReport: entry.aiReport ?? null,
        investmentThesis: entry.investmentThesis ?? null,
        financialReport: entry.financialReport ?? null,
        latestSnapshot: entry.latestSnapshot ?? null,
        performanceSinceFirstSnapshot: entry.performanceSinceFirstSnapshot ?? null,
        snapshotCount: entry.snapshotCount ?? 0,
      })),
    [liveCompareEntries]
  );

  return (
    <ResearchShell
      bundle={fallbackBundle}
      activeView={activeView}
      compareEntries={compareEntries}
      compareTickers={compareTickers}
      dataSourceHealth={dataSourceHealth}
      selectedList={selectedList}
      listNames={listNames}
      selectedListName={selectedListName}
      listSummaries={getListSummaries(portfolio, listNames)}
      portfolioItems={portfolio
        .filter((item) => item.stock)
        .map((item) => ({
          ticker: item.ticker,
          listName: item.listName,
          shares: item.shares,
          averageCost: item.averageCost,
          targetAllocation: item.targetAllocation,
          positionNotes: item.positionNotes,
          updatedAt: item.updatedAt,
          savedAt: item.savedAt,
          stock: item.stock,
        }))}
      searchQuery={searchQuery}
      selectedTicker={ticker}
      searchResults={searchResults}
      finnhubResults={finnhubResults}
      finnhubSearchStatus={finnhubSearchStatus}
      finnhubSearchMessage={finnhubSearchMessage}
      onViewChange={setActiveView}
      onCompareTickersChange={setCompareTickers}
      onOpenCompare={(tickersToCompare) => {
        if (tickersToCompare?.length) {
          setCompareTickers(tickersToCompare.slice(0, 4));
        }
        setActiveView("compare");
      }}
      onUpdatePortfolioPosition={onUpdatePortfolioPosition}
      onSelectedListChange={(listName) => {
        setSelectedList(listName);
        setActiveView("watchlist");
      }}
      onSelectedListNameChange={onSelectedListNameChange}
      onCreateList={onCreateList}
      onRenameList={onRenameList}
      onDeleteList={onDeleteList}
      onSearchChange={onSearchChange}
      onSearchFinnhub={onSearchFinnhub}
      onImportFinnhubSymbol={onImportFinnhubSymbol}
      onSelectTicker={(nextTicker) => {
        setTicker(nextTicker);
        setActiveView("research");
      }}
      onSaveToggle={onSaveToggle}
      onSyncMarketData={onSyncMarketData}
      onSyncFinancials={onSyncFinancials}
      onGenerateAiReport={onGenerateAiResearchReport}
      onCreateNote={onCreateNote}
      onDeleteNote={onDeleteNote}
      onGenerateAiNotes={onGenerateAiNotes}
      onProposeInvestmentThesis={onProposeInvestmentThesis}
      onSaveInvestmentThesis={onSaveInvestmentThesisDraft}
      syncStatus={syncStatus}
      syncMessage={syncMessage}
      aiReportStatus={aiReportStatus}
      aiReportMessage={aiReportMessage}
      noteStatus={noteStatus}
      noteMessage={noteMessage}
      thesisStatus={thesisStatus}
      thesisMessage={thesisMessage}
    />
  );
}

function StaticResearchApp() {
  const [selectedTicker, setSelectedTicker] = useState("NVDA");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeView, setActiveView] = useState<AppView>("research");
  const [compareTickers, setCompareTickers] = useState<string[]>([]);
  const [selectedList, setSelectedList] = useState("All");
  const [selectedListName, setSelectedListName] = useState(defaultListNames[0]);
  const [listNames, setListNames] = useState(defaultListNames);
  const [localNotes, setLocalNotes] = useState<Record<string, ResearchBundle["notes"]>>(
    {}
  );
  const [noteStatus, setNoteStatus] = useState<NoteStatus>("idle");
  const [noteMessage, setNoteMessage] = useState("");
  const [savedStocks, setSavedStocks] = useState<
    Map<
      string,
      {
        listName: string;
        shares?: number;
        averageCost?: number;
        targetAllocation?: number;
        positionNotes?: string;
        updatedAt?: number;
        savedAt: number;
      }
    >
  >(new Map());
  const baseBundle = researchBundles[selectedTicker] ?? demoBundle;
  const bundle = {
    ...baseBundle,
    notes: localNotes[selectedTicker] ?? baseBundle.notes,
    isSaved: savedStocks.has(selectedTicker),
  };
  const portfolioItems = Array.from(savedStocks.entries()).map(
    ([ticker, item]) => ({
      ticker,
      listName: item.listName,
      shares: item.shares,
      averageCost: item.averageCost,
      targetAllocation: item.targetAllocation,
      positionNotes: item.positionNotes,
      updatedAt: item.updatedAt,
      savedAt: item.savedAt,
      stock: researchBundles[ticker]?.stock ?? null,
    })
  );
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const searchResults = searchableStocks.filter((stock) => {
    if (!normalizedQuery) {
      return false;
    }

    return (
      stock.ticker.toLowerCase().includes(normalizedQuery) ||
      stock.companyName.toLowerCase().includes(normalizedQuery) ||
      stock.sector.toLowerCase().includes(normalizedQuery)
    );
  });
  const fallbackDataSourceHealth: DataSourceHealth = {
    dateKey: getTodayDateKey(),
    usage: [],
    events: [],
  };
  const compareEntries = useMemo(
    () =>
      compareTickers
        .map((item) => buildCompareEntryFromBundle(item, researchBundles[item]))
        .filter((item): item is CompareEntry => Boolean(item)),
    [compareTickers]
  );

  useEffect(() => {
    const availableTickers = new Set(portfolioItems.map((item) => item.ticker));
    setCompareTickers((current) =>
      current.filter((item) => availableTickers.has(item)).slice(0, 4)
    );
  }, [portfolioItems]);

  return (
    <ResearchShell
      bundle={bundle}
      activeView={activeView}
      compareEntries={compareEntries}
      compareTickers={compareTickers}
      dataSourceHealth={fallbackDataSourceHealth}
      selectedList={selectedList}
      listNames={listNames}
      selectedListName={selectedListName}
      listSummaries={getListSummaries(portfolioItems, listNames)}
      portfolioItems={portfolioItems}
      searchQuery={searchQuery}
      selectedTicker={selectedTicker}
      searchResults={searchResults}
      finnhubSearchMessage={
        normalizedQuery
          ? "Connect Convex to search and import new symbols from Finnhub."
          : ""
      }
      onViewChange={setActiveView}
      onCompareTickersChange={setCompareTickers}
      onOpenCompare={(tickersToCompare) => {
        if (tickersToCompare?.length) {
          setCompareTickers(tickersToCompare.slice(0, 4));
        }
        setActiveView("compare");
      }}
      onUpdatePortfolioPosition={async (input) => {
        setSavedStocks((current) => {
          const next = new Map(current);
          const existing = next.get(input.ticker);
          next.set(input.ticker, {
            listName: input.listName ?? existing?.listName ?? selectedListName,
            savedAt: existing?.savedAt ?? Date.now(),
            shares: input.shares,
            averageCost: input.averageCost,
            targetAllocation: input.targetAllocation,
            positionNotes: input.positionNotes,
            updatedAt: Date.now(),
          });
          return next;
        });
      }}
      onSelectedListChange={(listName) => {
        setSelectedList(listName);
        setActiveView("watchlist");
      }}
      onCreateList={async (name) => {
        const normalized = name.trim();
        if (!normalized || listNames.includes(normalized)) {
          throw new Error(normalized ? `${normalized} already exists.` : "List name cannot be empty.");
        }
        setListNames((current) => [...current, normalized]);
        setSelectedListName(normalized);
      }}
      onRenameList={async (currentName, nextName) => {
        const normalized = nextName.trim();
        if (!normalized) {
          throw new Error("List name cannot be empty.");
        }
        if (listNames.includes(normalized) && normalized !== currentName) {
          throw new Error(`${normalized} already exists.`);
        }
        setListNames((current) =>
          current.map((name) => (name === currentName ? normalized : name))
        );
        setSavedStocks((current) => {
          const next = new Map(current);
          for (const [ticker, item] of next.entries()) {
            if (item.listName === currentName) {
              next.set(ticker, { ...item, listName: normalized });
            }
          }
          return next;
        });
        if (selectedList === currentName) {
          setSelectedList(normalized);
        }
        if (selectedListName === currentName) {
          setSelectedListName(normalized);
        }
      }}
      onDeleteList={async (name, fallbackListName) => {
        const fallback = fallbackListName?.trim();
        setListNames((current) => current.filter((item) => item !== name));
        setSavedStocks((current) => {
          const next = new Map(current);
          for (const [ticker, item] of next.entries()) {
            if (item.listName === name) {
              if (!fallback) {
                next.delete(ticker);
              } else {
                next.set(ticker, { ...item, listName: fallback });
              }
            }
          }
          return next;
        });
        if (selectedList === name) {
          setSelectedList("All");
        }
        if (selectedListName === name) {
          setSelectedListName(fallback ?? defaultListNames[0]);
        }
      }}
      onSelectedListNameChange={(listName) => {
        setSelectedListName(listName);
        setSavedStocks((current) => {
          if (!current.has(selectedTicker)) {
            return current;
          }

          const next = new Map(current);
          next.set(selectedTicker, {
            ...current.get(selectedTicker)!,
            listName,
          });
          return next;
        });
      }}
      onSearchChange={setSearchQuery}
      onSelectTicker={(ticker) => {
        setSelectedTicker(ticker);
        setActiveView("research");
      }}
      onSaveToggle={() => {
        setSavedStocks((current) => {
          const next = new Map(current);
          if (next.has(selectedTicker)) {
            next.delete(selectedTicker);
          } else {
            next.set(selectedTicker, {
              listName: selectedListName,
              savedAt: Date.now(),
            });
          }
          return next;
        });
      }}
      onCreateNote={async (input) => {
        const title = input.title.trim();
        const body = input.body.trim();
        if (!title || !body) {
          throw new Error("Note title and body are required.");
        }

        setLocalNotes((current) => ({
          ...current,
          [input.ticker]: [
            {
              _id: `local-${Date.now()}`,
              title,
              body,
              tag: input.tag.trim() || "General",
              createdAt: Date.now(),
            },
            ...(current[input.ticker] ?? researchBundles[input.ticker]?.notes ?? []),
          ].slice(0, 20),
        }));
        setNoteStatus("success");
        setNoteMessage(`${input.ticker} note saved locally.`);
      }}
      onDeleteNote={async (input) => {
        if (!window.confirm(`Delete note "${input.title}"?`)) {
          return;
        }

        setLocalNotes((current) => {
          const existing = current[input.ticker] ?? researchBundles[input.ticker]?.notes ?? [];
          return {
            ...current,
            [input.ticker]: existing.filter((note) =>
              input.noteId
                ? note._id !== input.noteId
                : note.title !== input.title || note.createdAt !== input.createdAt
            ),
          };
        });
        setNoteStatus("success");
        setNoteMessage(`${input.ticker} note deleted locally.`);
      }}
      onGenerateAiNotes={async () => {
        const currentBundle = researchBundles[selectedTicker] ?? demoBundle;
        const generatedAt = Date.now();
        const rawGeneratedNotes: Array<ResearchBundle["notes"][number] | undefined> = [
          currentBundle.aiReport?.summary
            ? {
                _id: `local-ai-summary-${generatedAt}`,
                title: "AI report summary",
                body: currentBundle.aiReport.summary,
                tag: "AI Note",
                createdAt: generatedAt,
              }
            : undefined,
          currentBundle.news[0]
            ? {
                _id: `local-news-${generatedAt}`,
                title: `Latest headline: ${currentBundle.news[0].headline}`,
                body: `Review this ${currentBundle.news[0].source} headline against the current thesis.`,
                tag: "News",
                createdAt: generatedAt,
              }
            : undefined,
          {
            _id: `local-follow-up-${generatedAt}`,
            title: "Check next earnings call margin guidance",
            body: "Follow up on whether management guidance supports the current margin and revenue trajectory.",
            tag: "Follow-up",
            createdAt: generatedAt,
          },
        ];
        const generatedNotes = rawGeneratedNotes.filter(
          (item): item is ResearchBundle["notes"][number] => item !== undefined
        );

        setLocalNotes((current) => ({
          ...current,
          [selectedTicker]: [
            ...generatedNotes,
            ...(current[selectedTicker] ?? currentBundle.notes),
          ].slice(0, 20),
        }));
        setNoteStatus("success");
        setNoteMessage(`${generatedNotes.length} demo AI notes created locally.`);
      }}
      aiReportMessage="Run the local AI bridge in the Vite dev server to generate a full AI research report."
      noteStatus={noteStatus}
      noteMessage={noteMessage}
      thesisMessage="Generate or edit an investment thesis to personalize your research case."
    />
  );
}

function ResearchShell({
  bundle,
  activeView,
  compareEntries,
  compareTickers,
  dataSourceHealth,
  selectedList,
  listNames,
  listSummaries,
  portfolioItems,
  searchQuery,
  selectedTicker,
  selectedListName,
  searchResults,
  finnhubResults = [],
  finnhubSearchStatus = "idle",
  finnhubSearchMessage,
  onViewChange,
  onCompareTickersChange,
  onOpenCompare,
  onUpdatePortfolioPosition,
  onSelectedListChange,
  onSelectedListNameChange,
  onCreateList,
  onRenameList,
  onDeleteList,
  onSearchChange,
  onSearchFinnhub,
  onImportFinnhubSymbol,
  onSelectTicker,
  onSaveToggle,
  onSyncMarketData,
  onSyncFinancials,
  onGenerateAiReport,
  onCreateNote,
  onDeleteNote,
  onGenerateAiNotes,
  onProposeInvestmentThesis,
  onSaveInvestmentThesis,
  syncStatus = "idle",
  syncMessage,
  aiReportStatus = "idle",
  aiReportMessage,
  noteStatus = "idle",
  noteMessage,
  thesisStatus = "idle",
  thesisMessage,
}: ShellProps) {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return window.localStorage.getItem("stock-app-theme") === "dark"
      ? "dark"
      : "light";
  });
  const [isSidebarCompact, setIsSidebarCompact] = useState(() => {
    return window.localStorage.getItem("stock-app-sidebar-compact") === "true";
  });
  const [selectedTab, setSelectedTab] = useState<ResearchTab>("Overview");
  const { stock } = bundle;
  const strengths = bundle.researchItems.filter((item) => item.kind === "strength");
  const risks = bundle.researchItems.filter((item) => item.kind === "risk");
  const thesis = bundle.researchItems.filter((item) => item.kind === "thesis");
  const financialReport = bundle.financialReport;
  const activeFinancialReport = financialReport;
  const heroFinancials = getKeyFinancialMetricValues(stock, activeFinancialReport);
  const aiReport = bundle.aiReport;
  const savedThesis = bundle.investmentThesis;
  const normalizedSearchQuery = searchQuery.trim();
  const canSearchFinnhub = Boolean(onSearchFinnhub && normalizedSearchQuery);

  useEffect(() => {
    window.localStorage.setItem("stock-app-theme", theme);
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem("stock-app-sidebar-compact", String(isSidebarCompact));
  }, [isSidebarCompact]);

  useEffect(() => {
    setSelectedTab("Overview");
  }, [selectedTicker]);

  return (
    <div
      className={`app-shell${isSidebarCompact ? " sidebar-compact" : ""}`}
      data-theme={theme}
    >
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <LineChart size={18} />
          </div>
          <span>Company Research</span>
        </div>

        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              className={
                (item.view === activeView &&
                  !(activeView === "research" && selectedTab === "Notes")) ||
                (item.tab === selectedTab && activeView === "research")
                  ? "nav-item active"
                  : "nav-item"
              }
              key={item.label}
              onClick={() => {
                if (item.view) {
                  onViewChange(item.view as AppView);
                  if (item.view === "research") {
                    setSelectedTab("Overview");
                  }
                  return;
                }

                if (item.tab) {
                  onViewChange("research");
                  setSelectedTab(item.tab);
                }
              }}
              type="button"
            >
              <item.icon size={20} aria-hidden="true" />
              {item.label}
            </button>
          ))}
        </nav>

        <div className="my-lists">
          <div className="section-label">
            <span>My Lists</span>
            <span>+</span>
          </div>
          {listSummaries.map(({ name, count }) => (
            <button
              className={selectedList === name ? "list-row active" : "list-row"}
              key={name}
              onClick={() => onSelectedListChange(name)}
              type="button"
            >
              <span>{name}</span>
              <span>{count}</span>
            </button>
          ))}
        </div>

        <button
          aria-label={isSidebarCompact ? "Expand sidebar" : "Collapse sidebar"}
          className="collapse-button"
          onClick={() => setIsSidebarCompact((current) => !current)}
          title={isSidebarCompact ? "Expand sidebar" : "Collapse sidebar"}
          type="button"
        >
          {isSidebarCompact ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          <span>{isSidebarCompact ? "Expand" : "Collapse"}</span>
        </button>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="search-box">
            <div className="search-field">
              <Search size={18} />
              <input
                placeholder="Search company or ticker"
                value={searchQuery}
                onChange={(event) => onSearchChange(event.target.value)}
              />
              <kbd>⌘ K</kbd>
            </div>
            <div className="search-results">
              {searchResults.slice(0, 6).map((result) => (
                <button
                  className={
                    result.ticker === selectedTicker
                      ? "search-result active"
                      : "search-result"
                  }
                  key={result.ticker}
                  onClick={() => {
                    onSelectTicker(result.ticker);
                    onSearchChange("");
                  }}
                >
                  <span>{result.ticker}</span>
                  <div>
                    <strong>{result.companyName}</strong>
                    <small>
                      {result.exchange} • {result.sector}
                    </small>
                  </div>
                  <em>{result.changePercent > 0 ? "+" : ""}{result.changePercent.toFixed(2)}%</em>
                </button>
              ))}
              {canSearchFinnhub && (
                <button
                  className="search-finnhub-button"
                  disabled={finnhubSearchStatus === "searching"}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    void onSearchFinnhub?.(normalizedSearchQuery);
                  }}
                  type="button"
                >
                  <RefreshCw size={16} />
                  {finnhubSearchStatus === "searching"
                    ? "Searching Finnhub..."
                    : `Search Finnhub for "${normalizedSearchQuery}"`}
                </button>
              )}
              {finnhubResults.map((result) => (
                <button
                  className="search-result finnhub-result"
                  key={result.symbol}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onImportFinnhubSymbol?.(result.symbol)}
                  type="button"
                >
                  <span>{result.displaySymbol || result.symbol}</span>
                  <div>
                    <strong>{result.description}</strong>
                    <small>{result.type} • Import from Finnhub and save</small>
                  </div>
                  <em>Import</em>
                </button>
              ))}
              {finnhubSearchMessage && (
                <p className={`search-message ${finnhubSearchStatus}`}>
                  {finnhubSearchMessage}
                </p>
              )}
            </div>
          </div>

          <div className="market-strip">
            {marketIndexes.map(([label, value, change, direction]) => (
              <div className="market-pill" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <em className={direction}>{change}</em>
              </div>
            ))}
          </div>

          <button
            aria-label={
              theme === "light" ? "Switch to dark mode" : "Switch to light mode"
            }
            className="icon-button theme-toggle"
            type="button"
            onClick={() =>
              setTheme((current) => (current === "light" ? "dark" : "light"))
            }
          >
            {theme === "light" ? <Moon size={19} /> : <Sun size={19} />}
          </button>
          <button className="avatar">A</button>
          <ChevronDown size={17} />
        </header>

        {activeView === "watchlist" ? (
          <WatchlistView
            items={portfolioItems}
            listNames={listNames}
            selectedList={selectedList}
            compareTickers={compareTickers}
            onCreateList={onCreateList}
            onRenameList={onRenameList}
            onDeleteList={onDeleteList}
            onCompareTickersChange={onCompareTickersChange}
            onOpenCompare={onOpenCompare}
            onUpdatePortfolioPosition={onUpdatePortfolioPosition}
            onOpenResearch={(ticker) => {
              onSelectTicker(ticker);
              onViewChange("research");
            }}
            onSelectedListChange={onSelectedListChange}
          />
        ) : activeView === "portfolio" ? (
          <PortfolioView
            items={portfolioItems}
            listNames={listNames}
            selectedList={selectedList}
            compareTickers={compareTickers}
            onCompareTickersChange={onCompareTickersChange}
            onOpenCompare={onOpenCompare}
            onUpdatePortfolioPosition={onUpdatePortfolioPosition}
            onOpenResearch={(ticker) => {
              onSelectTicker(ticker);
              onViewChange("research");
            }}
            onSelectedListChange={onSelectedListChange}
          />
        ) : activeView === "compare" ? (
          <CompareCompaniesView
            entries={compareEntries}
            selectedTickers={compareTickers}
            onOpenResearch={(ticker) => {
              onSelectTicker(ticker);
              onViewChange("research");
            }}
            onBackToPortfolio={() => onViewChange("watchlist")}
            onRemoveTicker={(ticker) =>
              onCompareTickersChange(compareTickers.filter((item) => item !== ticker))
            }
          />
        ) : activeView === "screener" ? (
          <ScreenerView
            items={portfolioItems}
            listNames={listNames}
            compareTickers={compareTickers}
            onCompareTickersChange={onCompareTickersChange}
            onOpenCompare={onOpenCompare}
            onOpenResearch={(ticker) => {
              onSelectTicker(ticker);
              onViewChange("research");
            }}
          />
        ) : activeView === "data-health" ? (
          <DataSourceHealthView health={dataSourceHealth} />
        ) : (
          <>
            <section className="company-hero">
          <div className="company-lockup">
            <div className={stock.logoUrl ? "logo-tile has-logo" : "logo-tile"}>
              {stock.logoUrl ? (
                <img src={stock.logoUrl} alt="" />
              ) : (
                <span>{stock.ticker.slice(0, 1)}</span>
              )}
            </div>

            <div>
              <span className="ticker-badge">{stock.ticker}</span>
              <h1>{stock.companyName}</h1>
              <p>
                {stock.exchange} <span>•</span> {stock.sector}
              </p>
              <div className="price-row">
                <strong>{stock.price.toFixed(2)}</strong>
                <span>
                  {formatSignedNumber(stock.change)} ({formatSignedNumber(stock.changePercent)}%)
                </span>
              </div>
              <small>{formatQuoteTimestamp(stock.updatedAt)} • Market Closed</small>
            </div>
          </div>

          <div className="metric-grid">
            <Metric label="Market Cap" value={stock.marketCap} />
            <Metric label="P/E (TTM)" value={heroFinancials.peRatio} />
            <Metric label="Revenue (TTM)" value={heroFinancials.revenueTtm} />
            <Metric label="EPS (TTM)" value={heroFinancials.epsTtm} />
            <Metric label="Dividend Yield" value={heroFinancials.dividendYield} />
          </div>

          <div className="hero-actions">
            <button
              className={bundle.isSaved ? "primary-button is-saved" : "primary-button"}
              type="button"
              onClick={onSaveToggle}
            >
              <Star
                size={18}
                fill={bundle.isSaved ? "currentColor" : "none"}
                strokeWidth={bundle.isSaved ? 1.8 : 2}
              />
              {bundle.isSaved ? "Saved to watchlist" : "Save to Watchlist"}
            </button>
            {onSyncMarketData ? (
              <button
                className="secondary-button"
                data-testid="sync-market-data"
                disabled={syncStatus === "syncing"}
                type="button"
                onClick={onSyncMarketData}
              >
                <RefreshCw size={17} />
                {syncStatus === "syncing" ? "Syncing..." : "Sync live data"}
              </button>
            ) : (
              <button className="secondary-button" type="button">
                <MoreHorizontal size={20} />
              </button>
            )}
            {syncMessage && (
              <p className={`sync-message ${syncStatus}`}>{syncMessage}</p>
            )}
          </div>
        </section>

        <div className="save-list-row">
          <span>Save destination</span>
          <select
            value={selectedListName}
            onChange={(event) => onSelectedListNameChange(event.target.value)}
          >
            {listNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>

        <div className="tabs">
          {researchTabs.map((tab) => (
            <button
              className={tab === selectedTab ? "selected" : ""}
              key={tab}
              onClick={() => setSelectedTab(tab)}
              type="button"
            >
              {tab}
            </button>
          ))}
        </div>

        {selectedTab === "Overview" && (
          <OverviewTab
            aiReport={aiReport}
            aiReportMessage={aiReportMessage}
            aiReportStatus={aiReportStatus}
            bundle={bundle}
            risks={risks}
            savedThesis={savedThesis}
            stock={stock}
            strengths={strengths}
            thesis={thesis}
            thesisMessage={thesisMessage}
            thesisStatus={thesisStatus}
            syncStatus={syncStatus}
            onGenerateAiReport={onGenerateAiReport}
            onCreateNote={onCreateNote}
            onDeleteNote={onDeleteNote}
            onOpenNewsTab={() => setSelectedTab("News")}
            onOpenNotesTab={() => setSelectedTab("Notes")}
            onSyncMarketData={onSyncMarketData}
            onProposeInvestmentThesis={onProposeInvestmentThesis}
            onSaveInvestmentThesis={onSaveInvestmentThesis}
          />
        )}

        {selectedTab === "Financials" && (
          <FinancialsTab
            financialReport={activeFinancialReport}
            stock={stock}
            syncMessage={syncMessage}
            syncStatus={syncStatus}
            onSyncFinancials={onSyncFinancials}
          />
        )}

        {selectedTab === "News" && <NewsTab news={bundle.news} stock={stock} />}

        {selectedTab === "Filings" && (
          <FilingsTab financialReport={activeFinancialReport} stock={stock} />
        )}

        {selectedTab === "Notes" && (
          <NotesTab
            notes={bundle.notes}
            noteMessage={noteMessage}
            noteStatus={noteStatus}
            stock={stock}
            onCreateNote={onCreateNote}
            onDeleteNote={onDeleteNote}
            onGenerateAiNotes={onGenerateAiNotes}
          />
        )}
          </>
        )}
      </main>
    </div>
  );
}

function OverviewTab({
  bundle,
  stock,
  strengths,
  risks,
  thesis,
  aiReport,
  savedThesis,
  aiReportStatus,
  aiReportMessage,
  thesisStatus,
  thesisMessage,
  syncStatus,
  onGenerateAiReport,
  onCreateNote,
  onDeleteNote,
  onOpenNewsTab,
  onOpenNotesTab,
  onSyncMarketData,
  onProposeInvestmentThesis,
  onSaveInvestmentThesis,
}: {
  bundle: ResearchBundle;
  stock: ResearchBundle["stock"];
  strengths: ResearchItem[];
  risks: ResearchItem[];
  thesis: ResearchItem[];
  aiReport?: ResearchBundle["aiReport"];
  savedThesis?: ResearchBundle["investmentThesis"];
  aiReportStatus: "idle" | "generating" | "success" | "error";
  aiReportMessage?: string;
  thesisStatus: "idle" | "proposing" | "saving" | "success" | "error";
  thesisMessage?: string;
  syncStatus?: "idle" | "syncing" | "success" | "error";
  onGenerateAiReport?: () => Promise<void>;
  onCreateNote?: (input: NoteInput) => Promise<void>;
  onDeleteNote?: (input: NoteDeleteInput) => Promise<void>;
  onOpenNewsTab?: () => void;
  onOpenNotesTab?: () => void;
  onSyncMarketData?: () => Promise<void>;
  onProposeInvestmentThesis?: () => Promise<void>;
  onSaveInvestmentThesis?: (input: {
    summary: string;
    thesisPoints: string[];
    watchItems: string[];
  }) => Promise<void>;
}) {
  const snapshots = bundle.snapshots ?? [];

  return (
    <div className="content-grid">
      <section className="left-column">
        <PriceChart stock={stock} />

        <div className="lower-grid">
          <Panel
            title="Latest News"
            actions={
              <>
                {onSyncMarketData && (
                  <button
                    aria-label={`Refresh ${stock.ticker} latest news`}
                    className="panel-icon-action"
                    disabled={syncStatus === "syncing"}
                    onClick={() => void onSyncMarketData()}
                    title="Refresh latest news with live data sync"
                    type="button"
                  >
                    <RefreshCw size={15} />
                    <span>{syncStatus === "syncing" ? "Syncing" : "Sync"}</span>
                  </button>
                )}
                <button onClick={onOpenNewsTab} type="button">
                  View all
                </button>
              </>
            }
          >
            {bundle.news.length ? (
              <div className="timeline">
                {bundle.news.map((item) => (
                  <article className="timeline-item" key={item.headline}>
                    <NewsTimestamp timestamp={item.publishedAt} />
                    <div className="timeline-content">
                      <h3>{item.headline}</h3>
                      <p>
                        <NewsSourceLink item={item} />
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="news-empty">
                No company-specific headlines passed the latest relevance check.
              </p>
            )}
          </Panel>

          <Panel title="Notes" action="View all" onAction={onOpenNotesTab}>
            {bundle.notes.length ? (
              <div className="notes-stack">
                {bundle.notes.map((note) => (
                  <NoteCard
                    note={note}
                    ticker={stock.ticker}
                    key={`${note.title}-${note.createdAt}`}
                    onCreateNote={onCreateNote}
                    onDeleteNote={onDeleteNote}
                    onOpenNotesTab={onOpenNotesTab}
                  />
                ))}
              </div>
            ) : (
              <p className="notes-empty">
                No notes yet. Open the Notes tab to add a manual note, generate AI
                notes, or save a follow-up reminder.
              </p>
            )}
          </Panel>
        </div>
      </section>

      <aside className="research-column">
        <Panel
          title={
            <span className="panel-title-icon">
              <Sparkles size={19} />
              AI Research Brief
            </span>
          }
          meta={
            aiReport
              ? `${aiReport.provider} • ${aiReport.model} • ${formatDayMonth(aiReport.generatedAt)}`
              : "Generated from live data"
          }
        >
          <p className="brief-copy">{aiReport?.summary ?? stock.summary}</p>
          {aiReport ? (
            <div className="brief-sections">
              <BriefPointSection
                items={aiReport.bullPoints}
                title="Bull case"
                tone="strength"
              />
              <BriefPointSection
                items={aiReport.bearPoints}
                title="Risks"
                tone="risk"
              />
              <BriefPointSection
                items={aiReport.watchItems}
                title="What to watch"
                tone="watch"
              />
            </div>
          ) : (
            <div className="research-stack">
              {strengths.map((item, index) => (
                  <ResearchHighlight key={item.title} item={item} index={index} />
              ))}
              {risks.slice(0, 1).map((item) => (
                <ResearchHighlight key={item.title} item={item} risk />
              ))}
            </div>
          )}
          {aiReportMessage && (
            <p className={`sync-message ${aiReportStatus}`}>{aiReportMessage}</p>
          )}
          <button
            className="link-button"
            onClick={() => void onGenerateAiReport?.()}
            type="button"
          >
            {aiReportStatus === "generating"
              ? "Generating AI report..."
              : aiReport
                ? "Refresh AI report →"
                : "Generate AI report →"}
          </button>
        </Panel>

        <InvestmentThesisPanel
          fallbackThesisPoints={aiReport ? aiReport.thesisPoints : thesis.map((item) => item.title)}
          savedThesis={savedThesis}
          thesisMessage={thesisMessage}
          thesisStatus={thesisStatus}
          watchItems={savedThesis?.watchItems ?? (aiReport?.watchItems ?? [])}
          onPropose={onProposeInvestmentThesis}
          onSave={onSaveInvestmentThesis}
        />

        <Panel
          title="Recent Snapshots"
          meta={snapshots.length ? `${snapshots.length} saved syncs` : "History starts after your first live sync"}
        >
          {snapshots.length ? (
            <div className="snapshot-history">
              {snapshots.slice(0, 5).map((snapshot) => (
                <article
                  className="snapshot-history-item"
                  key={`${snapshot.ticker}-${snapshot.syncedAt}`}
                >
                  <div className="snapshot-history-top">
                    <strong>{formatDate(snapshot.syncedAt)}</strong>
                    <span className={snapshot.changePercent >= 0 ? "up" : "down"}>
                      {snapshot.changePercent >= 0 ? "+" : ""}
                      {snapshot.changePercent.toFixed(2)}%
                    </span>
                  </div>
                  <div className="snapshot-history-price">
                    <strong>${snapshot.price.toFixed(2)}</strong>
                    <span>{snapshot.marketCap} market cap</span>
                  </div>
                  <p>{snapshot.aiBriefSummary ?? snapshot.thesisSummary ?? snapshot.summary}</p>
                </article>
              ))}
            </div>
          ) : (
            <p className="portfolio-muted-copy">
              Each successful live sync now saves a lightweight company snapshot with the
              quote, core metrics, AI brief, and thesis state.
            </p>
          )}
        </Panel>

        <Panel title="Risk Factors">
          <ul className="risk-list">
            {(aiReport ? aiReport.watchItems : risks.map((item) => item.title)).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Panel>
      </aside>
    </div>
  );
}

function FinancialsTab({
  stock,
  financialReport,
  syncStatus,
  syncMessage,
  onSyncFinancials,
}: {
  stock: ResearchBundle["stock"];
  financialReport?: ResearchBundle["financialReport"];
  syncStatus: "idle" | "syncing" | "success" | "error";
  syncMessage?: string;
  onSyncFinancials?: () => Promise<void>;
}) {
  const report = financialReport;
  const financialStatus = syncStatus === "syncing" ? "loading" : syncStatus;
  const financialMessage =
    syncMessage ||
    (financialReport
      ? `Showing financial statements stored in Convex from ${financialReport.source}.`
      : `Financial statements for ${stock.ticker} are ready for Convex sync.`);
  const quarterly = report?.quarterly ?? [];
  const annual = report?.annual ?? [];
  const hasProviderData = Boolean(report);
  const [trendMetric, setTrendMetric] = useState<FinancialTrendMetric>("revenue");
  const [trendPeriod, setTrendPeriod] = useState<FinancialTrendPeriod>("annual");
  const keyFinancials = getKeyFinancialMetricValues(stock, report);
  const snapshotRows = [
    { label: "Market Cap", value: stock.marketCap, keep: true },
    { label: "Latest Quarter", value: report?.latestQuarter ?? "N/A" },
    { label: "Filed", value: report?.filedAt ?? "N/A" },
    { label: "Verification", value: report?.validationStatus ?? "Provider data" },
    { label: "Currency", value: report?.currency ?? "N/A" },
    { label: "EV / Revenue", value: report?.evToRevenue ?? "N/A" },
    { label: "EV / EBITDA", value: report?.evToEbitda ?? "N/A" },
    { label: "Fiscal Year End", value: report?.fiscalYearEnd ?? "N/A" },
  ].filter((row) => row.keep || hasFinancialValue(row.value));

  useEffect(() => {
    if (!quarterly.length && annual.length) {
      setTrendPeriod("annual");
    }
  }, [annual.length, quarterly.length]);

  return (
    <div className="financials-grid">
      <section className="left-column">
        <section className="panel">
          <div className="panel-header">
            <h2>Key Financials</h2>
            <div className="panel-actions financial-panel-actions">
              <span>
                {report?.source ??
                  (financialStatus === "loading"
                    ? "Loading provider data"
                    : hasProviderData
                      ? "Cached fundamentals"
                      : "Manual sync")}
              </span>
              <button
                className="secondary-button"
                disabled={financialStatus === "loading" || !onSyncFinancials}
                onClick={() => void onSyncFinancials?.()}
                type="button"
              >
                {financialStatus === "loading" ? "Syncing..." : hasProviderData ? "Refresh financials" : "Sync financials"}
              </button>
            </div>
          </div>
          <div className="financial-metric-grid">
            <FinancialMetricCard label="Revenue (TTM)" value={keyFinancials.revenueTtm} />
            <FinancialMetricCard label="EPS (TTM)" value={keyFinancials.epsTtm} />
            <FinancialMetricCard label="P/E (TTM)" value={keyFinancials.peRatio} />
            <FinancialMetricCard label="Dividend Yield" value={keyFinancials.dividendYield} />
            <FinancialMetricCard label="Profit Margin" value={keyFinancials.profitMargin} />
            <FinancialMetricCard
              label="Operating Margin"
              value={keyFinancials.operatingMargin}
            />
            <FinancialMetricCard label="ROE (TTM)" value={keyFinancials.roeTtm} />
            <FinancialMetricCard label="Price / Book" value={keyFinancials.priceToBook} />
          </div>
          {financialMessage && (
            <p className={`sync-message ${financialStatus}`}>{financialMessage}</p>
          )}
        </section>

        <Panel title="Quarterly Performance" meta={quarterly.length ? `${quarterly.length} recent quarters` : undefined}>
          {quarterly.length ? (
            <FinancialTable
              rows={quarterly}
              columns={[
                { key: "fiscalDateEnding", label: "Quarter" },
                { key: "totalRevenue", label: "Revenue" },
                { key: "operatingIncome", label: "Op income" },
                { key: "netIncome", label: "Net income" },
                { key: "dilutedEps", label: "Diluted EPS" },
                { key: "freeCashFlow", label: "FCF" },
              ]}
            />
          ) : (
            <EmptyFinancialState
              ticker={stock.ticker}
              message={financialMessage}
            />
          )}
        </Panel>

        <Panel title="Balance Sheet and Cash Flow">
          {quarterly.length ? (
            <FinancialTable
              rows={quarterly}
              columns={[
                { key: "fiscalDateEnding", label: "Quarter" },
                { key: "totalAssets", label: "Assets" },
                { key: "totalLiabilities", label: "Liabilities" },
                { key: "totalShareholderEquity", label: "Equity" },
                { key: "operatingCashflow", label: "Operating CF" },
                { key: "capitalExpenditures", label: "Capex" },
              ]}
            />
          ) : (
            <EmptyFinancialState
              ticker={stock.ticker}
              compact
              message={financialMessage}
            />
          )}
        </Panel>
      </section>

      <aside className="research-column">
        <Panel title="Financial Snapshot" meta={report?.latestQuarter ?? "Waiting for live sync"}>
          <div className="snapshot-list">
            {snapshotRows.map((row) => (
              <SnapshotRow key={row.label} label={row.label} value={row.value} />
            ))}
          </div>
          {report?.sourceUrl && (
            <a href={report.sourceUrl} rel="noreferrer" target="_blank">
              Open source filing <ExternalLink size={14} />
            </a>
          )}
          {report?.warnings?.map((warning) => (
            <p className="sync-message error" key={warning}>{warning}</p>
          ))}
        </Panel>

        <FinancialTrendPanel
          annual={annual}
          metric={trendMetric}
          period={trendPeriod}
          quarterly={quarterly}
          source={report?.source}
          ticker={stock.ticker}
          updatedAt={report?.updatedAt}
          onMetricChange={setTrendMetric}
          onPeriodChange={setTrendPeriod}
        />
      </aside>
    </div>
  );
}

function NewsTab({
  news,
  stock,
}: {
  news: ResearchBundle["news"];
  stock: ResearchBundle["stock"];
}) {
  return (
    <div className="single-panel-layout">
      <Panel title="Latest News" meta={`${stock.ticker} live headlines`}>
        {news.length ? (
          <div className="timeline">
            {news.map((item) => (
              <article className="timeline-item" key={`${item.headline}-${item.publishedAt}`}>
                <NewsTimestamp timestamp={item.publishedAt} />
                <div className="timeline-content">
                  <h3>{item.headline}</h3>
                  <p>
                    <NewsSourceLink item={item} />
                  </p>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="news-empty">
            No company-specific headlines passed the latest relevance check.
          </p>
        )}
      </Panel>
    </div>
  );
}

function NewsSourceLink({ item }: { item: ResearchBundle["news"][number] }) {
  if (!item.url) {
    return (
      <span className="news-source-link unavailable">
        {item.source}
      </span>
    );
  }

  return (
    <a
      className="news-source-link"
      href={item.url}
      rel="noreferrer"
      target="_blank"
    >
      {item.source}
      <ExternalLink size={14} />
    </a>
  );
}

function NewsTimestamp({ timestamp }: { timestamp: number }) {
  const date = new Date(timestamp);
  const hasTime =
    date.getHours() !== 0 ||
    date.getMinutes() !== 0 ||
    date.getSeconds() !== 0;

  return (
    <time dateTime={date.toISOString()}>
      <span>{formatDate(timestamp)}</span>
      {hasTime && <small>{formatTime(timestamp)}</small>}
    </time>
  );
}

function FilingsTab({
  stock,
  financialReport,
}: {
  stock: ResearchBundle["stock"];
  financialReport?: ResearchBundle["financialReport"];
}) {
  const annual = financialReport?.annual ?? [];
  const quarterly = financialReport?.quarterly ?? [];

  return (
    <div className="single-panel-layout">
      <Panel title="Reported Financial Filings" meta={financialReport?.source ?? "No filing feed yet"}>
        {annual.length || quarterly.length ? (
          <div className="filings-list">
            {quarterly.map((period) => (
              <article className="filing-card" key={`quarter-${period.fiscalDateEnding}`}>
                <div>
                  <strong>Quarterly report</strong>
                  <p>{period.fiscalDateEnding}</p>
                </div>
                <span>{period.totalRevenue} revenue</span>
              </article>
            ))}
            {annual.map((period) => (
              <article className="filing-card" key={`annual-${period.fiscalDateEnding}`}>
                <div>
                  <strong>Annual report</strong>
                  <p>{period.fiscalDateEnding}</p>
                </div>
                <span>{period.netIncome} net income</span>
              </article>
            ))}
          </div>
        ) : (
          <EmptyFinancialState ticker={stock.ticker} />
        )}
      </Panel>
    </div>
  );
}

function NotesTab({
  notes,
  noteMessage,
  noteStatus = "idle",
  stock,
  onCreateNote,
  onDeleteNote,
  onGenerateAiNotes,
}: {
  notes: ResearchBundle["notes"];
  noteMessage?: string;
  noteStatus?: NoteStatus;
  stock: ResearchBundle["stock"];
  onCreateNote?: (input: NoteInput) => Promise<void>;
  onDeleteNote?: (input: NoteDeleteInput) => Promise<void>;
  onGenerateAiNotes?: () => Promise<void>;
}) {
  const isBusy =
    noteStatus === "saving" ||
    noteStatus === "deleting" ||
    noteStatus === "generating";
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [draftTag, setDraftTag] = useState("General");

  const openNoteEditor = (preset?: { title?: string; body?: string; tag?: string }) => {
    setDraftTitle(preset?.title ?? "");
    setDraftBody(preset?.body ?? "");
    setDraftTag(preset?.tag ?? "General");
    setIsEditorOpen(true);
  };

  const closeNoteEditor = () => {
    setIsEditorOpen(false);
    setDraftTitle("");
    setDraftBody("");
    setDraftTag("General");
  };

  const saveDraftNote = async () => {
    const title = draftTitle.trim();
    const body = draftBody.trim();
    const tag = draftTag.trim() || "General";

    if (!onCreateNote || !title || !body) {
      return;
    }

    await onCreateNote({
      ticker: stock.ticker,
      title,
      body,
      tag,
    });
    closeNoteEditor();
  };

  return (
    <div className="single-panel-layout">
      <Panel title="Research Notes" meta={`${stock.ticker} working notes`}>
        <div className="notes-toolbar">
          <button
            className="primary-button compact"
            disabled={!onCreateNote || isBusy}
            onClick={() => openNoteEditor()}
            type="button"
          >
            Add Note
          </button>
          <button
            className="secondary-button compact"
            disabled={!onGenerateAiNotes || isBusy}
            onClick={() => void onGenerateAiNotes?.()}
            type="button"
          >
            {noteStatus === "generating" ? "Generating..." : "Auto-generate AI Notes"}
          </button>
          <button
            className="secondary-button compact"
            disabled={!onCreateNote || isBusy}
            onClick={() =>
              openNoteEditor({
                title: "Check next earnings call margin guidance",
                body: `Follow up on whether ${stock.companyName} management guidance supports the current margin and revenue trajectory.`,
                tag: "Follow-up",
              })
            }
            type="button"
          >
            Add Follow-up
          </button>
        </div>
        {isEditorOpen && (
          <div className="note-editor">
            <div className="note-editor-grid">
              <label>
                Title
                <input
                  autoFocus
                  disabled={isBusy}
                  onChange={(event) => setDraftTitle(event.target.value)}
                  placeholder="What should you remember?"
                  value={draftTitle}
                />
              </label>
              <label>
                Tag
                <select
                  disabled={isBusy}
                  onChange={(event) => setDraftTag(event.target.value)}
                  value={draftTag}
                >
                  <option>General</option>
                  <option>AI Note</option>
                  <option>News</option>
                  <option>Financials</option>
                  <option>Risk</option>
                  <option>Follow-up</option>
                  <option>Thesis</option>
                </select>
              </label>
            </div>
            <label>
              Note
              <textarea
                disabled={isBusy}
                onChange={(event) => setDraftBody(event.target.value)}
                placeholder="Write the detail, decision, question, or next check."
                rows={4}
                value={draftBody}
              />
            </label>
            <div className="note-editor-actions">
              <button
                className="primary-button compact"
                disabled={!draftTitle.trim() || !draftBody.trim() || isBusy}
                onClick={() => void saveDraftNote()}
                type="button"
              >
                Save Note
              </button>
              <button
                className="secondary-button compact"
                disabled={isBusy}
                onClick={closeNoteEditor}
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        {noteMessage && (
          <p className={`sync-message ${noteStatus}`}>{noteMessage}</p>
        )}
        {notes.length ? (
          <div className="notes-stack">
            {notes.map((note) => (
              <NoteCard
                note={note}
                ticker={stock.ticker}
                key={`${note.title}-${note.createdAt}`}
                onCreateNote={onCreateNote}
                onDeleteNote={onDeleteNote}
              />
            ))}
          </div>
        ) : (
          <p className="notes-empty">
            No notes yet. Start with a manual note, generate AI notes from the
            current research data, or create a follow-up reminder.
          </p>
        )}
      </Panel>
    </div>
  );
}

function NoteCard({
  note,
  ticker,
  onCreateNote,
  onDeleteNote,
  onOpenNotesTab,
}: {
  note: ResearchBundle["notes"][number];
  ticker?: string;
  onCreateNote?: (input: NoteInput) => Promise<void>;
  onDeleteNote?: (input: NoteDeleteInput) => Promise<void>;
  onOpenNotesTab?: () => void;
}) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const canCreateFollowUp = Boolean(ticker && onCreateNote);
  const canDeleteNote = Boolean(ticker && onDeleteNote);
  const noteText = `${note.title}\n\n${note.body}`;

  const copyNote = async () => {
    await navigator.clipboard.writeText(noteText);
    setIsMenuOpen(false);
  };

  const createFollowUp = async () => {
    if (!ticker || !onCreateNote) {
      return;
    }

    await onCreateNote({
      ticker,
      title: note.title.startsWith("Follow up:")
        ? note.title
        : `Follow up: ${note.title}`,
      body: `Revisit this note after the next earnings call, filing, or major news update.\n\nOriginal note: ${note.body}`,
      tag: "Follow-up",
    });
    setIsMenuOpen(false);
  };

  const deleteCurrentNote = async () => {
    if (!ticker || !onDeleteNote) {
      return;
    }

    setIsMenuOpen(false);
    await onDeleteNote({
      noteId: note._id,
      ticker,
      title: note.title,
      createdAt: note.createdAt,
    });
  };

  return (
    <article className="note-card">
      <div>
        <h3>{note.title}</h3>
        <p>{note.body}</p>
        <time>{formatDate(note.createdAt)}</time>
      </div>
      <div className="note-card-actions">
        <span className={`tag ${note.tag.toLowerCase().replace(" ", "-")}`}>
          {note.tag}
        </span>
        <div className="note-card-menu">
          <button
            aria-expanded={isMenuOpen}
            aria-label={`Actions for ${note.title}`}
            className="icon-button small note-menu-button"
            onClick={() => setIsMenuOpen((current) => !current)}
            type="button"
          >
            <MoreHorizontal size={18} strokeWidth={2.4} />
          </button>
          {isMenuOpen && (
            <div className="note-actions-menu" role="menu">
              <button onClick={() => void copyNote()} role="menuitem" type="button">
                Copy note
              </button>
              {canCreateFollowUp && (
                <button
                  onClick={() => void createFollowUp()}
                  role="menuitem"
                  type="button"
                >
                  Create follow-up
                </button>
              )}
              {onOpenNotesTab && (
                <button onClick={onOpenNotesTab} role="menuitem" type="button">
                  Open Notes tab
                </button>
              )}
              {canDeleteNote && (
                <button
                  className="danger-menu-item"
                  onClick={() => void deleteCurrentNote()}
                  role="menuitem"
                  type="button"
                >
                  Delete note
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function FinancialMetricCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="financial-metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function SnapshotRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="snapshot-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

type FinancialReportPeriod = NonNullable<ResearchBundle["financialReport"]>["quarterly"][number];
type FinancialNumericField = keyof NonNullable<FinancialReportPeriod["normalized"]>;
type FinancialTrendMetric = "revenue" | "netIncome" | "freeCashFlow" | "eps";
type FinancialTrendPeriod = "quarterly" | "annual";
type FinancialTrendPoint = {
  displayValue: string;
  label: string;
  tableLabel: string;
  value: number;
};

type FinancialReport = NonNullable<ResearchBundle["financialReport"]>;

const financialTrendMetrics: Array<{
  key: FinancialTrendMetric;
  label: string;
  field: FinancialNumericField;
}> = [
  { key: "revenue", label: "Revenue", field: "totalRevenue" },
  { key: "netIncome", label: "Net Income", field: "netIncome" },
  { key: "freeCashFlow", label: "Free Cash Flow", field: "freeCashFlow" },
  { key: "eps", label: "EPS", field: "dilutedEps" },
];

function parseFinancialChartValue(value: string) {
  if (!value || value === "N/A") {
    return null;
  }

  const cleaned = value.replace(/[$,%]/g, "").trim();
  const match = cleaned.match(/^(-?\d+(?:\.\d+)?)([TtBbMmKk])?$/);
  if (!match) {
    const numeric = Number(cleaned);
    return Number.isFinite(numeric) ? numeric : null;
  }

  const numeric = Number(match[1]);
  const suffix = match[2]?.toUpperCase();
  const multiplier =
    suffix === "T"
      ? 1_000_000_000_000
      : suffix === "B"
        ? 1_000_000_000
        : suffix === "M"
          ? 1_000_000
          : suffix === "K"
            ? 1_000
            : 1;

  return Number.isFinite(numeric) ? numeric * multiplier : null;
}

function financialFieldValue(
  row: FinancialReportPeriod | undefined,
  field: FinancialNumericField
) {
  const normalized = row?.normalized?.[field];
  if (typeof normalized === "number" && Number.isFinite(normalized)) {
    return normalized;
  }
  return parseFinancialChartValue(String(row?.[field] ?? "N/A"));
}

function hasFinancialValue(value?: string) {
  return Boolean(value && value !== "N/A" && value !== "None");
}

function formatDerivedLargeFinancialValue(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return formatAbbreviatedFinancialValue(String(value));
}

function formatDerivedRatio(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return value.toFixed(2);
}

function formatDerivedPercent(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toFixed(2)}%`;
}

function sumFinancialField(
  rows: FinancialReportPeriod[],
  field: FinancialNumericField,
  count: number
) {
  const selectedRows = rows.slice(0, count);
  const hasQuarterContinuity = selectedRows.every((row, index) => {
    if (index === selectedRows.length - 1) return true;
    const current = new Date(row.fiscalDateEnding).getTime();
    const previous = new Date(selectedRows[index + 1].fiscalDateEnding).getTime();
    const days = (current - previous) / (24 * 60 * 60 * 1000);
    return Number.isFinite(days) && days >= 60 && days <= 120;
  });
  if (!hasQuarterContinuity) {
    return null;
  }
  const values = selectedRows
    .map((row) => financialFieldValue(row, field));

  if (values.length < count || values.some((value) => value === null)) {
    return null;
  }

  return values.reduce<number>((sum, value) => sum + (value as number), 0);
}

function latestFinancialField(
  rows: FinancialReportPeriod[],
  field: FinancialNumericField
) {
  return financialFieldValue(rows[0], field);
}

function deriveRevenueTtm(report?: FinancialReport) {
  if (!report) {
    return "N/A";
  }

  return formatDerivedLargeFinancialValue(
    sumFinancialField(report.quarterly, "totalRevenue", 4) ??
      latestFinancialField(report.annual, "totalRevenue")
  );
}

function deriveEpsTtm(report?: FinancialReport) {
  if (!report) {
    return "N/A";
  }

  return formatDerivedRatio(
    sumFinancialField(report.quarterly, "dilutedEps", 4) ??
      latestFinancialField(report.annual, "dilutedEps")
  );
}

function derivePeRatio(
  stock: ResearchBundle["stock"],
  report?: FinancialReport
) {
  const eps =
    sumFinancialField(report?.quarterly ?? [], "dilutedEps", 4) ??
    latestFinancialField(report?.annual ?? [], "dilutedEps");
  if (eps && eps > 0) {
    return formatDerivedRatio(stock.price / eps);
  }

  return hasFinancialValue(stock.peRatio) ? stock.peRatio : "N/A";
}

function deriveReturnOnEquity(report?: FinancialReport) {
  if (!report || hasFinancialValue(report.returnOnEquityTtm)) {
    return report?.returnOnEquityTtm ?? "N/A";
  }

  const netIncome = latestFinancialField(report.annual, "netIncome");
  const equity = latestFinancialField(report.annual, "totalShareholderEquity");
  if (!netIncome || !equity) {
    return "N/A";
  }

  return formatDerivedPercent((netIncome / equity) * 100);
}

function getKeyFinancialMetricValues(
  stock: ResearchBundle["stock"],
  report?: FinancialReport
) {
  const derivedRevenueTtm = deriveRevenueTtm(report);
  const derivedEpsTtm = deriveEpsTtm(report);

  return {
    revenueTtm: hasFinancialValue(derivedRevenueTtm)
      ? derivedRevenueTtm
      : stock.revenueTtm,
    epsTtm: hasFinancialValue(derivedEpsTtm) ? derivedEpsTtm : stock.epsTtm,
    peRatio: derivePeRatio(stock, report),
    dividendYield: hasFinancialValue(stock.dividendYield) ? stock.dividendYield : "N/A",
    profitMargin: report?.profitMargin ?? "N/A",
    operatingMargin: report?.operatingMarginTtm ?? "N/A",
    roeTtm: deriveReturnOnEquity(report),
    priceToBook: report?.priceToBookRatio ?? "N/A",
  };
}

function toFiscalLabel(dateValue: string, period: FinancialTrendPeriod) {
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) {
    return dateValue;
  }

  if (period === "annual") {
    return String(date.getUTCFullYear());
  }

  const quarter = Math.floor(date.getUTCMonth() / 3) + 1;
  return `Q${quarter} '${String(date.getUTCFullYear()).slice(-2)}`;
}

function getFinancialTrendLabelAnchor(index: number, total: number) {
  if (index === 0) {
    return "start";
  }

  if (index === total - 1) {
    return "end";
  }

  return "middle";
}

function FinancialTrendPanel({
  annual,
  metric,
  period,
  quarterly,
  source,
  ticker,
  updatedAt,
  onMetricChange,
  onPeriodChange,
}: {
  annual: FinancialReportPeriod[];
  metric: FinancialTrendMetric;
  period: FinancialTrendPeriod;
  quarterly: FinancialReportPeriod[];
  source?: string;
  ticker: string;
  updatedAt?: number;
  onMetricChange: (metric: FinancialTrendMetric) => void;
  onPeriodChange: (period: FinancialTrendPeriod) => void;
}) {
  const selectedMetric =
    financialTrendMetrics.find((item) => item.key === metric) ?? financialTrendMetrics[0];
  const hasQuarterlyRows = quarterly.length > 0;
  const hasAnnualRows = annual.length > 0;
  const sourceRows = (period === "quarterly" ? quarterly : annual)
    .slice()
    .reverse();
  const points: FinancialTrendPoint[] = sourceRows
    .map((row) => {
      const displayValue = String(row[selectedMetric.field] ?? "N/A");
      const value = financialFieldValue(row, selectedMetric.field);
      return {
        label: toFiscalLabel(row.fiscalDateEnding, period),
        tableLabel: row.fiscalDateEnding,
        displayValue,
        value,
      };
    })
    .filter((point): point is FinancialTrendPoint => point.value !== null);
  const tableRows = sourceRows.slice(-4).reverse();
  const numericValues = points.map((point) => point.value);
  const minValue = numericValues.length ? Math.min(...numericValues) : 0;
  const maxValue = numericValues.length ? Math.max(...numericValues) : 0;
  const range = maxValue - minValue || Math.max(Math.abs(maxValue), 1);
  const width = 560;
  const height = 270;
  const padding = { top: 38, right: 44, bottom: 48, left: 44 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const chartPoints = points.map((point, index) => {
    const x =
      padding.left +
      (points.length === 1 ? chartWidth / 2 : (index / (points.length - 1)) * chartWidth);
    const y =
      padding.top +
      chartHeight -
      ((point.value - minValue) / range) * chartHeight;
    return { ...point, x, y };
  });
  const path = chartPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
  const lastChartPoint = chartPoints[chartPoints.length - 1];

  return (
    <section className="panel financial-trend-panel">
      <div className="panel-header financial-trend-title">
        <div>
          <h2>Financial Trend</h2>
          <span>{source ?? "Reported statements"}</span>
        </div>
      </div>
      <div className="financial-trend-tabs" role="tablist" aria-label="Financial trend metric">
        {financialTrendMetrics.map((item) => (
          <button
            className={item.key === metric ? "selected" : ""}
            key={item.key}
            onClick={() => onMetricChange(item.key)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="financial-trend-toolbar">
        <div className="financial-period-toggle">
          {(["quarterly", "annual"] as const).map((item) => (
            <button
              className={item === period ? "selected" : ""}
              disabled={item === "quarterly" && !hasQuarterlyRows && hasAnnualRows}
              key={item}
              onClick={() => onPeriodChange(item)}
              type="button"
            >
              {item === "quarterly" ? "Quarterly" : "Annual"}
            </button>
          ))}
        </div>
        <span>
          Updated: {updatedAt ? formatDate(updatedAt) : "After sync"} · {ticker}
        </span>
      </div>
      {!hasQuarterlyRows && hasAnnualRows && (
        <p className="financial-trend-note">
          Quarterly statements are not available from the current provider response, so
          this chart is showing annual data.
        </p>
      )}
      {chartPoints.length >= 2 ? (
        <>
          <div className="financial-trend-chart" role="img" aria-label={`${ticker} ${selectedMetric.label} trend chart`}>
            <svg viewBox={`0 0 ${width} ${height}`}>
              {[0, 1, 2, 3].map((line) => {
                const y = padding.top + (line / 3) * chartHeight;
                return (
                  <line
                    className="financial-grid-line"
                    key={line}
                    x1={padding.left}
                    x2={width - padding.right}
                    y1={y}
                    y2={y}
                  />
                );
              })}
              <path className="financial-trend-area" d={`${path} L ${lastChartPoint.x} ${height - padding.bottom} L ${chartPoints[0].x} ${height - padding.bottom} Z`} />
              <path className="financial-trend-line" d={path} />
              {chartPoints.map((point, index) => (
                <g key={`${point.label}-${index}`}>
                  <circle className="financial-trend-dot" cx={point.x} cy={point.y} r="5" />
                  <text
                    className="financial-trend-value"
                    x={point.x}
                    y={point.y - 12}
                    textAnchor="middle"
                  >
                    {point.displayValue}
                  </text>
                  <line
                    className="financial-trend-tick"
                    x1={point.x}
                    x2={point.x}
                    y1={height - padding.bottom}
                    y2={height - padding.bottom + 6}
                  />
                  <text
                    className="financial-trend-label"
                    x={point.x}
                    y={height - 17}
                    textAnchor={getFinancialTrendLabelAnchor(index, chartPoints.length)}
                  >
                    {point.label}
                  </text>
                </g>
              ))}
            </svg>
          </div>
          <div className="financial-trend-legend">
            <span><i /> Actual {selectedMetric.label}</span>
            <small>Unit: reported currency</small>
          </div>
          <div className="financial-trend-table">
            <div className="financial-trend-table-row header">
              <span>Fiscal Period</span>
              <span>{selectedMetric.label}</span>
              <span>Revenue</span>
              <span>EPS</span>
            </div>
            {tableRows.map((row) => (
              <div className="financial-trend-table-row" key={`${period}-${row.fiscalDateEnding}`}>
                <span>{row.fiscalDateEnding}</span>
                <span>{String(row[selectedMetric.field] ?? "N/A")}</span>
                <span>{row.totalRevenue}</span>
                <span>{row.dilutedEps}</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <EmptyFinancialState ticker={ticker} compact />
      )}
    </section>
  );
}

function EmptyFinancialState({
  ticker,
  compact,
  message,
}: {
  ticker: string;
  compact?: boolean;
  message?: string;
}) {
  return (
    <div className={compact ? "financial-empty compact" : "financial-empty"}>
      <strong>No live financial statements yet</strong>
      <p>
        {message ||
          `Sync live data for ${ticker} to pull company overview, income statement, balance sheet, and cash flow data into this tab.`}
      </p>
    </div>
  );
}

function FinancialTable({
  rows,
  columns,
}: {
  rows: FinancialReportPeriod[];
  columns: Array<{ key: string; label: string }>;
}) {
  return (
    <div className="financial-table">
      <div className="financial-table-row financial-table-header">
        {columns.map((column) => (
          <span key={column.key}>{column.label}</span>
        ))}
      </div>
      {rows.map((row) => (
        <div className="financial-table-row" key={row.fiscalDateEnding}>
          {columns.map((column) => (
            <span
              key={`${row.fiscalDateEnding}-${column.key}`}
              title={row.derived ? row.derivation : undefined}
            >
              {column.key === "fiscalDateEnding" && row.derived
                ? `${row.fiscalDateEnding} (derived Q4)`
                : String(row[column.key as keyof FinancialReportPeriod] ?? "N/A")}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

function DataSourceHealthView({ health }: { health?: DataSourceHealth }) {
  const usageByService = new Map(
    (health?.usage ?? []).map((item) => [item.service, item])
  );
  const providerCards = [
    {
      service: "Finnhub",
      role: "Quotes, company profiles, news, symbol search",
      configured: "Server env",
      note: "Configured in Convex env; verified by recent calls.",
    },
    {
      service: "Financial Modeling Prep",
      role: "Primary financial statements, ratios, and key metrics",
      configured: "Convex server env",
      dailyLimit: 250,
      note: "Used by the Convex fundamentals action before falling back to Alpha Vantage.",
    },
    {
      service: "Alpha Vantage Primary",
      role: "Fallback financial statements",
      configured: "Convex server env",
      dailyLimit: 25,
      note: "Used by Convex when FMP is unavailable.",
    },
    {
      service: "Alpha Vantage Secondary",
      role: "Fallback financial statements",
      configured: "Convex server env",
      dailyLimit: 25,
      note: "Rotated by Convex when the primary key reaches its quota.",
    },
    {
      service: "Alpha Vantage Tertiary",
      role: "Fallback financial statements",
      configured: "Convex server env",
      dailyLimit: 25,
      note: "Final Convex fallback within the configured free quota.",
    },
    {
      service: "Twelve Data",
      role: "Fallback quote and chart history",
      configured: twelveDataClientKey ? "Client key configured" : "Client key missing",
      note: "Used when primary chart or quote providers are unavailable.",
    },
    {
      service: "Local AI Bridge",
      role: "AI research report, investment thesis, and practical notes",
      configured: "Local endpoint",
      note: "Tracked when report, thesis, or notes generation is requested.",
    },
    {
      service: "Cache",
      role: "Persisted Convex financial reports and snapshots",
      configured: "Convex",
      note: "Persisted reports avoid unnecessary provider calls.",
    },
  ];

  return (
    <section className="data-health-page">
      <div className="compare-hero">
        <div>
          <span className="ticker-badge">Settings</span>
          <h1>Data Source Health</h1>
          <p>
            Monitor configured providers, today&apos;s API usage, rate-limit errors,
            and fallback behavior across market data, financials, charts, and AI.
          </p>
        </div>
        <div className="portfolio-summary data-health-summary">
          <Metric label="Usage Date" value={health?.dateKey ?? getTodayDateKey()} />
          <Metric
            label="Calls Today"
            value={String((health?.usage ?? []).reduce((sum, item) => sum + item.count, 0))}
          />
          <Metric
            label="Errors"
            value={String((health?.usage ?? []).reduce((sum, item) => sum + item.errorCount, 0))}
          />
          <Metric
            label="Fallbacks"
            value={String((health?.usage ?? []).reduce((sum, item) => sum + item.fallbackCount, 0))}
          />
        </div>
      </div>

      <section className="data-source-grid">
        {providerCards.map((provider) => {
          const usage = usageByService.get(provider.service);
          const remainingCalls =
            provider.dailyLimit === undefined
              ? undefined
              : Math.max(provider.dailyLimit - (usage?.count ?? 0), 0);
          return (
            <article className="panel data-source-card" key={provider.service}>
              <div className="data-source-card-header">
                <div>
                  <h2>{provider.service}</h2>
                  <p>{provider.role}</p>
                </div>
                <span className={usage?.lastStatus ?? "idle"}>
                  {usage?.lastStatus ?? "idle"}
                </span>
              </div>
              <div className="data-source-card-body">
                <SnapshotRow label="Configured" value={provider.configured} />
                <SnapshotRow label="Calls today" value={String(usage?.count ?? 0)} />
                {provider.dailyLimit !== undefined && (
                  <>
                    <SnapshotRow
                      label="Daily free limit"
                      value={`${provider.dailyLimit} calls`}
                    />
                    <SnapshotRow
                      label="Remaining today"
                      value={`${remainingCalls ?? provider.dailyLimit} calls`}
                    />
                  </>
                )}
                <SnapshotRow label="Success" value={String(usage?.successCount ?? 0)} />
                <SnapshotRow label="Errors" value={String(usage?.errorCount ?? 0)} />
                <SnapshotRow label="Fallbacks" value={String(usage?.fallbackCount ?? 0)} />
                <SnapshotRow
                  label="Fallback provider"
                  value={usage?.lastFallbackProvider ?? "None today"}
                />
                <SnapshotRow
                  label="Last call"
                  value={usage ? formatDateTime(usage.lastCalledAt) : "No calls today"}
                />
                {usage?.lastRequestUrl && (
                  <SnapshotRow label="Last request URL" value={usage.lastRequestUrl} />
                )}
              </div>
              <p className="data-source-note">
                {usage?.lastMessage ?? provider.note}
              </p>
            </article>
          );
        })}
      </section>

      <section className="panel data-events-panel">
        <div className="panel-header">
          <h2>Recent Provider Events</h2>
          <span>{health?.events.length ?? 0} latest events</span>
        </div>
        <div className="data-events-list">
          {health?.events.length ? (
            health.events.map((event) => (
              <article
                className={`data-event-row ${event.status}`}
                key={`${event.service}-${event.operation}-${event.calledAt}`}
              >
                <div>
                  <strong>{event.service}</strong>
                  <small>
                    {event.operation}
                    {event.ticker ? ` • ${event.ticker}` : ""}
                  </small>
                </div>
                <span>{event.status}</span>
                <p>
                  {event.fallbackProvider
                    ? `${event.provider} -> ${event.fallbackProvider}`
                    : event.provider}
                  {event.message ? `: ${event.message}` : ""}
                  {event.requestUrl ? (
                    <>
                      <br />
                      <code>{event.requestUrl}</code>
                    </>
                  ) : null}
                </p>
                <time>{formatDateTime(event.calledAt)}</time>
              </article>
            ))
          ) : (
            <div className="compare-empty-state">
              <strong>No provider events recorded yet</strong>
              <p>
                Sync market data, search Finnhub, refresh financials, or generate an
                AI report to start building the daily usage log.
              </p>
            </div>
          )}
        </div>
      </section>
    </section>
  );
}

const screenerPresets: ScreenerPreset[] = [
  "All",
  "Momentum",
  "Mega Cap",
  "Reasonable P/E",
  "Dividend",
  "With Positions",
  "Needs Research",
];

function ScreenerView({
  items,
  listNames,
  compareTickers,
  onCompareTickersChange,
  onOpenCompare,
  onOpenResearch,
}: {
  items: PortfolioItem[];
  listNames: string[];
  compareTickers: string[];
  onCompareTickersChange: (tickers: string[]) => void;
  onOpenCompare: (tickers?: string[]) => void;
  onOpenResearch: (ticker: string) => void;
}) {
  const [preset, setPreset] = useState<ScreenerPreset>("All");
  const [listFilter, setListFilter] = useState("All");
  const [sectorFilter, setSectorFilter] = useState("All");
  const [query, setQuery] = useState("");
  const sectors = Array.from(
    new Set(items.map((item) => item.stock?.sector).filter(Boolean) as string[])
  ).sort((left, right) => left.localeCompare(right));

  const rows = items
    .map((item) => {
      const stock = item.stock;
      const marketCap = parseAbbreviatedMetric(stock?.marketCap);
      const peRatio = parseAbbreviatedMetric(stock?.peRatio);
      const revenue = parseAbbreviatedMetric(stock?.revenueTtm);
      const dividendYield = parseAbbreviatedMetric(stock?.dividendYield);
      const hasPosition = getPositionShares(item) > 0;
      const missingFundamentals = !stock || peRatio === null || revenue === null;
      const score =
        (stock?.changePercent ?? 0) * 2 +
        (marketCap && marketCap >= 1_000_000_000_000 ? 10 : 0) +
        (revenue && revenue >= 50_000_000_000 ? 8 : 0) +
        (peRatio && peRatio > 0 && peRatio <= 35 ? 8 : 0) +
        (dividendYield && dividendYield > 0 ? 4 : 0) +
        (hasPosition ? 5 : 0) -
        (missingFundamentals ? 10 : 0);
      const signal =
        missingFundamentals
          ? "Needs research"
          : (stock?.changePercent ?? 0) >= 3
            ? "Momentum"
            : peRatio && peRatio > 0 && peRatio <= 35
              ? "Reasonable valuation"
              : dividendYield && dividendYield > 0
                ? "Income"
                : "Watch";

      return {
        item,
        stock,
        marketCap,
        peRatio,
        revenue,
        dividendYield,
        hasPosition,
        missingFundamentals,
        score,
        signal,
      };
    })
    .filter((row) => {
      const normalizedQuery = query.trim().toLowerCase();
      const stock = row.stock;

      if (listFilter !== "All" && row.item.listName !== listFilter) {
        return false;
      }

      if (sectorFilter !== "All" && stock?.sector !== sectorFilter) {
        return false;
      }

      if (
        normalizedQuery &&
        !row.item.ticker.toLowerCase().includes(normalizedQuery) &&
        !stock?.companyName.toLowerCase().includes(normalizedQuery)
      ) {
        return false;
      }

      if (preset === "Momentum") {
        return (stock?.changePercent ?? 0) >= 2;
      }
      if (preset === "Mega Cap") {
        return Boolean(row.marketCap && row.marketCap >= 1_000_000_000_000);
      }
      if (preset === "Reasonable P/E") {
        return Boolean(row.peRatio && row.peRatio > 0 && row.peRatio <= 35);
      }
      if (preset === "Dividend") {
        return Boolean(row.dividendYield && row.dividendYield > 0);
      }
      if (preset === "With Positions") {
        return row.hasPosition;
      }
      if (preset === "Needs Research") {
        return row.missingFundamentals;
      }

      return true;
    })
    .sort((left, right) => right.score - left.score);

  const topCandidates = rows.slice(0, 3);
  const positionedCount = rows.filter((row) => row.hasPosition).length;
  const averagePeValues = rows
    .map((row) => row.peRatio)
    .filter((value): value is number => Boolean(value && value > 0));
  const averagePe =
    averagePeValues.length > 0
      ? averagePeValues.reduce((sum, value) => sum + value, 0) / averagePeValues.length
      : null;

  const toggleCompareTicker = (ticker: string) => {
    if (compareTickers.includes(ticker)) {
      onCompareTickersChange(compareTickers.filter((item) => item !== ticker));
      return;
    }

    if (compareTickers.length >= 4) {
      window.alert("Compare supports up to 4 companies at a time.");
      return;
    }

    onCompareTickersChange([...compareTickers, ticker]);
  };

  return (
    <section className="portfolio-page screener-page">
      <div className="portfolio-hero">
        <div>
          <span className="ticker-badge">Screener</span>
          <h1>Saved Company Screener</h1>
          <p>
            Find candidates from companies you already track. This uses saved watchlist
            data first, so screening does not burn market-data API quota.
          </p>
        </div>
        <div className="portfolio-summary">
          <Metric label="Screened" value={String(rows.length)} />
          <Metric label="Saved Universe" value={String(items.length)} />
          <Metric label="With Positions" value={String(positionedCount)} />
          <Metric label="Avg P/E" value={averagePe ? averagePe.toFixed(1) : "N/A"} />
        </div>
      </div>

      <section className="panel screener-controls-panel">
        <div className="panel-header">
          <h2>Screen Builder</h2>
          <span>{compareTickers.length} selected for compare</span>
        </div>
        <div className="screener-presets">
          {screenerPresets.map((name) => (
            <button
              className={preset === name ? "selected" : ""}
              key={name}
              onClick={() => setPreset(name)}
              type="button"
            >
              {name}
            </button>
          ))}
        </div>
        <div className="screener-filter-grid">
          <label>
            Search
            <input
              placeholder="Ticker or company"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label>
            List
            <select value={listFilter} onChange={(event) => setListFilter(event.target.value)}>
              {["All", ...listNames].map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <label>
            Sector
            <select
              value={sectorFilter}
              onChange={(event) => setSectorFilter(event.target.value)}
            >
              {["All", ...sectors].map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <button
            className="secondary-button"
            disabled={compareTickers.length === 0}
            type="button"
            onClick={() => onCompareTickersChange([])}
          >
            Clear compare
          </button>
          <button
            className="primary-button compact"
            disabled={compareTickers.length < 2}
            type="button"
            onClick={() => onOpenCompare(compareTickers)}
          >
            Compare selected
          </button>
        </div>
      </section>

      <section className="screener-opportunity-grid">
        {topCandidates.length ? (
          topCandidates.map((row, index) => (
            <article className="panel screener-opportunity-card" key={row.item.ticker}>
              <div className="screener-rank">#{index + 1}</div>
              <div>
                <span className="ticker-badge">{row.item.ticker}</span>
                <h2>{row.stock?.companyName ?? row.item.ticker}</h2>
                <p>{row.signal}</p>
              </div>
              <div className="screener-card-metrics">
                <Metric
                  label="Day"
                  value={
                    row.stock
                      ? `${row.stock.changePercent >= 0 ? "+" : ""}${row.stock.changePercent.toFixed(2)}%`
                      : "N/A"
                  }
                />
                <Metric label="P/E" value={row.stock?.peRatio ?? "N/A"} />
                <Metric label="Revenue" value={row.stock?.revenueTtm ?? "N/A"} />
              </div>
              <button
                className="secondary-button compact"
                type="button"
                onClick={() => onOpenResearch(row.item.ticker)}
              >
                Research
              </button>
            </article>
          ))
        ) : (
          <section className="panel compare-empty-state">
            <strong>No companies match this screen</strong>
            <p>Relax the preset or filters to bring more saved companies back into view.</p>
          </section>
        )}
      </section>

      <section className="panel screener-table-panel">
        <div className="panel-header">
          <h2>Screen Results</h2>
          <span>{rows.length} companies</span>
        </div>
        <div className="screener-table">
          <div className="screener-table-header">
            <span>Company</span>
            <span>Signal</span>
            <span>Price</span>
            <span>Day</span>
            <span>Market Cap</span>
            <span>P/E</span>
            <span>Revenue</span>
            <span>List</span>
            <span />
          </div>
          {rows.map((row) => (
            <article className="screener-row" key={row.item.ticker}>
              <button
                className="portfolio-company-cell company-cell-button"
                type="button"
                onClick={() => onOpenResearch(row.item.ticker)}
              >
                <span>{row.item.ticker.slice(0, 1)}</span>
                <div>
                  <strong>{row.stock?.companyName ?? row.item.ticker}</strong>
                  <small>{row.item.ticker} • {row.stock?.sector ?? "Unknown"}</small>
                </div>
              </button>
              <span className={`screener-signal ${row.missingFundamentals ? "warning" : ""}`}>
                {row.signal}
              </span>
              <strong>{row.stock ? `$${row.stock.price.toFixed(2)}` : "N/A"}</strong>
              <em className={(row.stock?.changePercent ?? 0) >= 0 ? "up" : "down"}>
                {row.stock
                  ? `${row.stock.changePercent >= 0 ? "+" : ""}${row.stock.changePercent.toFixed(2)}%`
                  : "N/A"}
              </em>
              <span>{row.stock?.marketCap ?? "N/A"}</span>
              <span>{row.stock?.peRatio ?? "N/A"}</span>
              <span>{row.stock?.revenueTtm ?? "N/A"}</span>
              <span className="portfolio-list-pill">{row.item.listName}</span>
              <div className="portfolio-row-actions">
                <button type="button" onClick={() => toggleCompareTicker(row.item.ticker)}>
                  {compareTickers.includes(row.item.ticker) ? "Selected" : "Compare"}
                </button>
                <button type="button" onClick={() => onOpenResearch(row.item.ticker)}>
                  Research
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

function WatchlistView({
  items,
  listNames,
  selectedList,
  compareTickers,
  onCreateList,
  onRenameList,
  onDeleteList,
  onCompareTickersChange,
  onOpenCompare,
  onUpdatePortfolioPosition,
  onOpenResearch,
  onSelectedListChange,
}: {
  items: PortfolioItem[];
  listNames: string[];
  selectedList: string;
  compareTickers: string[];
  onCreateList?: (name: string) => Promise<void>;
  onRenameList?: (currentName: string, nextName: string) => Promise<void>;
  onDeleteList?: (name: string, fallbackListName?: string) => Promise<void>;
  onCompareTickersChange: (tickers: string[]) => void;
  onOpenCompare: (tickers?: string[]) => void;
  onUpdatePortfolioPosition: (input: PortfolioPositionInput) => Promise<void>;
  onOpenResearch: (ticker: string) => void;
  onSelectedListChange: (listName: string) => void;
}) {
  const [newListName, setNewListName] = useState("");
  const [editingListName, setEditingListName] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [listManagerMessage, setListManagerMessage] = useState("");
  const visibleItems =
    selectedList === "All"
      ? items
      : items.filter((item) => item.listName === selectedList);
  const sortedItems = visibleItems
    .slice()
    .sort((left, right) => (right.savedAt ?? 0) - (left.savedAt ?? 0));
  const positionedCount = items.filter((item) => getPositionShares(item) > 0).length;
  const recentAdd = sortedItems[0] ?? null;
  const selectedVisibleCount = visibleItems.filter((item) =>
    compareTickers.includes(item.ticker)
  ).length;

  const toggleCompareTicker = (ticker: string) => {
    if (compareTickers.includes(ticker)) {
      onCompareTickersChange(compareTickers.filter((item) => item !== ticker));
      return;
    }

    if (compareTickers.length >= 4) {
      return;
    }

    onCompareTickersChange([...compareTickers, ticker]);
  };

  const handleEditPosition = async (item: PortfolioItem) => {
    const sharesInput = window.prompt(
      `Shares for ${item.ticker}`,
      String(item.shares ?? "")
    );
    if (sharesInput === null) {
      return;
    }

    const averageCostInput = window.prompt(
      `Average cost per share for ${item.ticker}`,
      String(item.averageCost ?? "")
    );
    if (averageCostInput === null) {
      return;
    }

    const targetAllocationInput = window.prompt(
      `Target allocation % for ${item.ticker}`,
      String(item.targetAllocation ?? "")
    );
    if (targetAllocationInput === null) {
      return;
    }

    const notesInput = window.prompt(
      `Position note for ${item.ticker}`,
      item.positionNotes ?? ""
    );
    if (notesInput === null) {
      return;
    }

    const shares = Number(sharesInput);
    const averageCost = Number(averageCostInput);
    const targetAllocation = Number(targetAllocationInput);

    if (
      !Number.isFinite(shares) ||
      !Number.isFinite(averageCost) ||
      !Number.isFinite(targetAllocation) ||
      shares < 0 ||
      averageCost < 0 ||
      targetAllocation < 0
    ) {
      window.alert("Use non-negative numbers for shares, average cost, and target allocation.");
      return;
    }

    await onUpdatePortfolioPosition({
      ticker: item.ticker,
      listName: item.listName,
      shares,
      averageCost,
      targetAllocation,
      positionNotes: notesInput.trim(),
    });
  };

  const handleCreateList = async () => {
    const normalized = newListName.trim();
    if (!normalized) {
      return;
    }

    try {
      await onCreateList?.(normalized);
      setNewListName("");
      setListManagerMessage(`${normalized} created.`);
    } catch (error) {
      setListManagerMessage(
        error instanceof Error ? error.message : "Unable to create list."
      );
    }
  };

  const startRenameList = (currentName: string) => {
    setEditingListName(currentName);
    setRenameDraft(currentName);
    setListManagerMessage("");
  };

  const cancelRenameList = () => {
    setEditingListName(null);
    setRenameDraft("");
    setListManagerMessage("");
  };

  const handleRenameList = async () => {
    if (!editingListName) {
      return;
    }

    const nextName = renameDraft.trim();
    if (!nextName || nextName === editingListName) {
      cancelRenameList();
      return;
    }

    if (listNames.includes(nextName)) {
      setListManagerMessage(`${nextName} already exists.`);
      return;
    }

    try {
      await onRenameList?.(editingListName, nextName);
      setListManagerMessage(`${editingListName} renamed to ${nextName}.`);
      setEditingListName(null);
      setRenameDraft("");
    } catch (error) {
      setListManagerMessage(
        error instanceof Error ? error.message : "Unable to rename list."
      );
    }
  };

  const handleDeleteList = async (name: string) => {
    const assignedCount = items.filter((item) => item.listName === name).length;
    if (assignedCount === 0) {
      if (!window.confirm(`Delete "${name}"?`)) {
        return;
      }

      await onDeleteList?.(name);
      return;
    }

    const fallbackOptions = listNames.filter((item) => item !== name);
    if (fallbackOptions.length === 0) {
      window.alert("Create another list before deleting the only remaining list.");
      return;
    }

    const fallbackListName = window
      .prompt(
        `Move ${assignedCount} compan${assignedCount === 1 ? "y" : "ies"} from "${name}" into which list before deleting it?`,
        fallbackOptions[0]
      )
      ?.trim();
    if (!fallbackListName) {
      return;
    }

    await onDeleteList?.(name, fallbackListName);
  };

  return (
    <section className="portfolio-page watchlist-page">
      <div className="portfolio-hero">
        <div>
          <span className="ticker-badge">Watchlist</span>
          <h1>Saved Research Lists</h1>
          <p>
            Organize companies you are researching, compare candidates, and promote
            a saved name into a real portfolio position when you add shares.
          </p>
        </div>
        <div className="portfolio-summary">
          <Metric label="Saved Companies" value={String(items.length)} />
          <Metric label="Lists" value={String(listNames.length)} />
          <Metric label="With Positions" value={String(positionedCount)} />
          <Metric label="Latest Add" value={recentAdd?.ticker ?? "None"} />
        </div>
      </div>

      <div className="portfolio-filters">
        {["All", ...listNames].map((name) => (
          <button
            className={selectedList === name ? "selected" : ""}
            key={name}
            onClick={() => onSelectedListChange(name)}
            type="button"
          >
            {name}
          </button>
        ))}
      </div>

      <section className="panel portfolio-list-manager-panel">
        <div className="panel-header">
          <h2>Manage Watchlists</h2>
          <span>{listNames.length} total lists</span>
        </div>
        <div className="list-manager-create">
          <input
            placeholder="Create a new watchlist"
            value={newListName}
            onChange={(event) => setNewListName(event.target.value)}
          />
          <button
            className="primary-button compact"
            type="button"
            onClick={() => void handleCreateList()}
          >
            Create list
          </button>
        </div>
        <div className="list-manager-stack">
          {listNames.map((name) => {
            const count = items.filter((item) => item.listName === name).length;
            const isActive = selectedList === name;
            const isRenaming = editingListName === name;

            return (
              <div className="list-manager-row" key={name}>
                {isRenaming ? (
                  <div className="list-manager-rename">
                    <input
                      autoFocus
                      aria-label={`New name for ${name}`}
                      onChange={(event) => setRenameDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          void handleRenameList();
                        }
                        if (event.key === "Escape") {
                          cancelRenameList();
                        }
                      }}
                      value={renameDraft}
                    />
                    <small>{count} compan{count === 1 ? "y" : "ies"}</small>
                  </div>
                ) : (
                  <button
                    className={isActive ? "list-manager-name active" : "list-manager-name"}
                    onClick={() => onSelectedListChange(name)}
                    type="button"
                  >
                    <strong>{name}</strong>
                    <small>{count} compan{count === 1 ? "y" : "ies"}</small>
                  </button>
                )}
                <div className="list-manager-actions">
                  {isRenaming ? (
                    <>
                      <button type="button" onClick={() => void handleRenameList()}>
                        Save
                      </button>
                      <button type="button" onClick={cancelRenameList}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" onClick={() => startRenameList(name)}>
                        Rename
                      </button>
                      <button type="button" onClick={() => void handleDeleteList(name)}>
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {listManagerMessage && (
          <p className="list-manager-message">{listManagerMessage}</p>
        )}
      </section>

      <section className="panel compare-selection-panel">
        <div className="panel-header">
          <h2>Compare Watchlist Companies</h2>
          <span>{compareTickers.length} selected</span>
        </div>
        <div className="compare-selection-body">
          <p>
            Select 2 to 4 saved companies to compare fundamentals, valuation,
            chart performance, and thesis side by side.
          </p>
          <div className="compare-selection-actions">
            <button
              className="secondary-button"
              disabled={compareTickers.length === 0}
              type="button"
              onClick={() => onCompareTickersChange([])}
            >
              Clear selection
            </button>
            <button
              className="primary-button compact"
              disabled={compareTickers.length < 2}
              type="button"
              onClick={() => onOpenCompare(compareTickers)}
            >
              Compare selected
            </button>
          </div>
          <small>
            {selectedVisibleCount > 0
              ? `${selectedVisibleCount} selected in the current watchlist.`
              : "Select companies from the table below to start."}
          </small>
        </div>
      </section>

      <section className="panel portfolio-table-panel">
        <div className="watchlist-table">
          <div className="watchlist-table-header">
            <span>Select</span>
            <span>Company</span>
            <span>List</span>
            <span>Price</span>
            <span>Day</span>
            <span>Saved</span>
            <span />
          </div>

          {visibleItems.length === 0 ? (
            <div className="empty-portfolio">
              <h2>No saved companies in this watchlist</h2>
              <p>
                Search for a ticker, open the research page, choose a save
                destination, and save it to this watchlist.
              </p>
            </div>
          ) : (
            sortedItems.map((item) => (
              <article className="watchlist-row" key={item.ticker}>
                <label className="portfolio-compare-check">
                  <input
                    checked={compareTickers.includes(item.ticker)}
                    onChange={() => toggleCompareTicker(item.ticker)}
                    type="checkbox"
                  />
                  <span>Compare</span>
                </label>
                <button
                  className="portfolio-company-cell company-cell-button"
                  type="button"
                  onClick={() => onOpenResearch(item.ticker)}
                >
                  <span>{item.ticker.slice(0, 1)}</span>
                  <div>
                    <strong>{item.stock?.companyName ?? item.ticker}</strong>
                    <small>
                      {item.ticker} • {item.stock?.sector ?? "Unknown sector"}
                    </small>
                  </div>
                </button>
                <span className="portfolio-list-pill">{item.listName}</span>
                <strong>{item.stock ? `$${item.stock.price.toFixed(2)}` : "N/A"}</strong>
                <em className={(item.stock?.changePercent ?? 0) >= 0 ? "up" : "down"}>
                  {item.stock
                    ? `${item.stock.changePercent >= 0 ? "+" : ""}${item.stock.changePercent.toFixed(2)}%`
                    : "N/A"}
                </em>
                <span>{formatDate(item.savedAt)}</span>
                <div className="portfolio-row-actions">
                  <button type="button" onClick={() => void handleEditPosition(item)}>
                    {getPositionShares(item) > 0 ? "Edit Position" : "Add Position"}
                  </button>
                  <button type="button" onClick={() => onOpenResearch(item.ticker)}>
                    Research
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}

function PortfolioView({
  items,
  listNames,
  selectedList,
  compareTickers,
  onCompareTickersChange,
  onOpenCompare,
  onUpdatePortfolioPosition,
  onOpenResearch,
  onSelectedListChange,
}: {
  items: PortfolioItem[];
  listNames: string[];
  selectedList: string;
  compareTickers: string[];
  onCompareTickersChange: (tickers: string[]) => void;
  onOpenCompare: (tickers?: string[]) => void;
  onUpdatePortfolioPosition: (input: PortfolioPositionInput) => Promise<void>;
  onOpenResearch: (ticker: string) => void;
  onSelectedListChange: (listName: string) => void;
}) {
  const positionItems = items.filter((item) => getPositionShares(item) > 0);
  const visibleItems =
    selectedList === "All"
      ? positionItems
      : positionItems.filter((item) => item.listName === selectedList);
  const sortedItems = visibleItems
    .slice()
    .sort((left, right) => (right.savedAt ?? 0) - (left.savedAt ?? 0));
  const totalMarketValue = visibleItems.reduce(
    (sum, item) => sum + getPositionMarketValue(item),
    0
  );
  const totalCostBasis = visibleItems.reduce(
    (sum, item) => sum + getPositionCostBasis(item),
    0
  );
  const totalGainLoss = totalMarketValue - totalCostBasis;
  const totalGainLossPercent =
    totalCostBasis > 0 ? (totalGainLoss / totalCostBasis) * 100 : 0;
  const investedCount = visibleItems.length;
  const totalTargetAllocation = visibleItems.reduce(
    (sum, item) => sum + (item.targetAllocation ?? 0),
    0
  );
  const largestGainLossPosition =
    visibleItems
      .slice()
      .sort(
        (left, right) => getPositionGainLoss(right) - getPositionGainLoss(left)
      )[0] ?? null;
  const biggestWinner = sortedItems.reduce<PortfolioItem | null>((best, item) => {
    if (!item.stock) {
      return best;
    }
    if (!best?.stock) {
      return item;
    }
    return (item.stock.changePercent ?? 0) > (best.stock.changePercent ?? 0)
      ? item
      : best;
  }, null);
  const biggestLoser = sortedItems.reduce<PortfolioItem | null>((worst, item) => {
    if (!item.stock) {
      return worst;
    }
    if (!worst?.stock) {
      return item;
    }
    return (item.stock.changePercent ?? 0) < (worst.stock.changePercent ?? 0)
      ? item
      : worst;
  }, null);
  const topLists = Array.from(
    visibleItems.reduce((counts, item) => {
      counts.set(item.listName, (counts.get(item.listName) ?? 0) + 1);
      return counts;
    }, new Map<string, number>())
  )
    .sort((left, right) => right[1] - left[1])
    .slice(0, 4);
  const recentAdds = sortedItems.slice(0, 3);
  const selectedVisibleCount = visibleItems.filter((item) =>
    compareTickers.includes(item.ticker)
  ).length;

  const toggleCompareTicker = (ticker: string) => {
    if (compareTickers.includes(ticker)) {
      onCompareTickersChange(compareTickers.filter((item) => item !== ticker));
      return;
    }

    if (compareTickers.length >= 4) {
      window.alert("Compare supports up to 4 companies at a time.");
      return;
    }

    onCompareTickersChange([...compareTickers, ticker]);
  };

  const handleEditPosition = async (item: PortfolioItem) => {
    const sharesInput = window.prompt(
      `Shares owned for ${item.ticker}`,
      String(item.shares ?? "")
    );
    if (sharesInput === null) {
      return;
    }

    const averageCostInput = window.prompt(
      `Average cost per share for ${item.ticker}`,
      String(item.averageCost ?? "")
    );
    if (averageCostInput === null) {
      return;
    }

    const targetAllocationInput = window.prompt(
      `Target allocation % for ${item.ticker}`,
      String(item.targetAllocation ?? "")
    );
    if (targetAllocationInput === null) {
      return;
    }

    const notesInput = window.prompt(
      `Position note for ${item.ticker}`,
      item.positionNotes ?? ""
    );
    if (notesInput === null) {
      return;
    }

    const shares = Number(sharesInput);
    const averageCost = Number(averageCostInput);
    const targetAllocation = Number(targetAllocationInput);

    if (
      !Number.isFinite(shares) ||
      !Number.isFinite(averageCost) ||
      !Number.isFinite(targetAllocation) ||
      shares < 0 ||
      averageCost < 0 ||
      targetAllocation < 0
    ) {
      window.alert("Use non-negative numbers for shares, average cost, and target allocation.");
      return;
    }

    await onUpdatePortfolioPosition({
      ticker: item.ticker,
      listName: item.listName,
      shares,
      averageCost,
      targetAllocation,
      positionNotes: notesInput.trim(),
    });
  };

  return (
    <section className="portfolio-page">
      <div className="portfolio-hero">
        <div>
          <span className="ticker-badge">Portfolio</span>
          <h1>Portfolio Positions</h1>
          <p>
            Track saved companies as real holdings with shares, cost basis,
            current value, allocation, and position notes.
          </p>
        </div>
        <div className="portfolio-summary">
          <Metric label="Holdings" value={String(visibleItems.length)} />
          <Metric label="Positions" value={String(investedCount)} />
          <Metric label="Market Value" value={formatCurrency(totalMarketValue)} />
          <Metric
            label="Unrealized P/L"
            value={`${totalGainLoss >= 0 ? "+" : ""}${formatCurrency(totalGainLoss)} (${totalGainLossPercent >= 0 ? "+" : ""}${totalGainLossPercent.toFixed(2)}%)`}
          />
        </div>
      </div>

      <div className="portfolio-filters">
        {["All", ...listNames].map((name) => (
          <button
            className={selectedList === name ? "selected" : ""}
            key={name}
            onClick={() => onSelectedListChange(name)}
            type="button"
          >
            {name}
          </button>
        ))}
      </div>

      <section className="panel compare-selection-panel">
        <div className="panel-header">
          <h2>Compare Companies</h2>
          <span>{compareTickers.length} selected</span>
        </div>
        <div className="compare-selection-body">
          <p>
            Pick 2 to 4 holdings from your portfolio to compare revenue,
            margins, valuation, recent performance, and thesis side by side.
          </p>
          <div className="compare-selection-actions">
            <button
              className="secondary-button"
              disabled={compareTickers.length === 0}
              type="button"
              onClick={() => onCompareTickersChange([])}
            >
              Clear selection
            </button>
            <button
              className="primary-button compact"
              disabled={compareTickers.length < 2}
              type="button"
              onClick={() => onOpenCompare(compareTickers)}
            >
              Compare selected
            </button>
          </div>
          <small>
            {selectedVisibleCount > 0
              ? `${selectedVisibleCount} selected in the current view.`
              : "Select companies from the table below to start."}
          </small>
        </div>
      </section>

      <div className="portfolio-dashboard-grid">
        <section className="panel portfolio-insights-panel">
          <div className="panel-header">
            <h2>Portfolio Snapshot</h2>
            <span>{selectedList === "All" ? "Across all lists" : selectedList}</span>
          </div>
          <div className="portfolio-insights-grid">
            <PortfolioInsightCard
              label="Best daily performer"
              title={biggestWinner?.ticker ?? "No holdings yet"}
              value={
                biggestWinner?.stock
                  ? `${biggestWinner.stock.changePercent >= 0 ? "+" : ""}${biggestWinner.stock.changePercent.toFixed(2)}%`
                  : "Add a company"
              }
              tone="up"
            />
            <PortfolioInsightCard
              label="Largest unrealized P/L"
              title={largestGainLossPosition?.ticker ?? "No positions yet"}
              value={
                largestGainLossPosition
                  ? formatCurrency(getPositionGainLoss(largestGainLossPosition))
                  : "Add shares and cost"
              }
              tone={
                (largestGainLossPosition
                  ? getPositionGainLoss(largestGainLossPosition)
                  : 0) >= 0
                  ? "up"
                  : "down"
              }
            />
            <PortfolioInsightCard
              label="Needs attention today"
              title={biggestLoser?.ticker ?? "No holdings yet"}
              value={
                biggestLoser?.stock
                  ? `${biggestLoser.stock.changePercent >= 0 ? "+" : ""}${biggestLoser.stock.changePercent.toFixed(2)}%`
                  : "Add a company"
              }
              tone="down"
            />
          </div>
        </section>

        <section className="panel portfolio-breakdown-panel">
          <div className="panel-header">
            <h2>Position Breakdown</h2>
            <span>How holdings are organized</span>
          </div>
          <div className="breakdown-stack">
            {topLists.length ? (
              topLists.map(([name, count]) => (
                <div className="breakdown-row" key={name}>
                  <div>
                    <strong>{name}</strong>
                    <small>{count} compan{count === 1 ? "y" : "ies"}</small>
                  </div>
                  <span>{Math.round((count / visibleItems.length) * 100)}%</span>
                </div>
              ))
            ) : (
              <p className="portfolio-muted-copy">
                Add shares from the Watchlist page to see how your holdings are distributed.
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="portfolio-dashboard-grid">
        <section className="panel portfolio-sector-panel">
          <div className="panel-header">
            <h2>Allocation</h2>
            <span>{totalTargetAllocation.toFixed(1)}% target assigned</span>
          </div>
          <div className="allocation-stack">
            {visibleItems.length ? (
              visibleItems
                .slice()
                .sort(
                  (left, right) =>
                    getPositionMarketValue(right) - getPositionMarketValue(left)
                )
                .slice(0, 5)
                .map((item) => {
                  const currentAllocation =
                    totalMarketValue > 0
                      ? (getPositionMarketValue(item) / totalMarketValue) * 100
                      : 0;
                  return (
                    <div className="allocation-row" key={item.ticker}>
                      <div>
                        <strong>{item.ticker}</strong>
                        <small>
                          Target {(item.targetAllocation ?? 0).toFixed(1)}%
                        </small>
                      </div>
                      <span>{currentAllocation.toFixed(1)}%</span>
                    </div>
                  );
                })
            ) : (
              <p className="portfolio-muted-copy">
                Add shares and average cost from Watchlist to see current allocation by position.
              </p>
            )}
          </div>
        </section>

        <section className="panel portfolio-activity-panel">
          <div className="panel-header">
            <h2>Recent Activity</h2>
            <span>Latest position updates</span>
          </div>
          <div className="activity-stack">
            {recentAdds.length ? (
              recentAdds.map((item) => (
                <button
                  className="activity-row"
                  key={`${item.ticker}-${item.savedAt}`}
                  onClick={() => onOpenResearch(item.ticker)}
                  type="button"
                >
                  <div>
                    <strong>{item.stock?.companyName ?? item.ticker}</strong>
                    <small>
                      {item.ticker} • {item.listName}
                    </small>
                  </div>
                  <span>{formatDate(item.savedAt)}</span>
                </button>
              ))
            ) : (
              <p className="portfolio-muted-copy">
                Add position details from Watchlist to see recent holdings here.
              </p>
            )}
          </div>
        </section>
      </div>

      <section className="panel portfolio-table-panel">
        <div className="portfolio-table">
          <div className="portfolio-table-header">
            <span>Select</span>
            <span>Company</span>
            <span>List</span>
            <span>Shares</span>
            <span>Avg Cost</span>
            <span>Value</span>
            <span>P/L</span>
            <span>Alloc.</span>
            <span />
          </div>

          {visibleItems.length === 0 ? (
            <div className="empty-portfolio">
              <h2>No portfolio positions yet</h2>
              <p>
                Open Watchlist, add shares and average cost to a saved company,
                and it will become a portfolio holding here.
              </p>
            </div>
          ) : (
            sortedItems.map((item) => (
              <article className="portfolio-row" key={item.ticker}>
                {(() => {
                  const marketValue = getPositionMarketValue(item);
                  const gainLoss = getPositionGainLoss(item);
                  const gainLossPercent = getPositionGainLossPercent(item);
                  const currentAllocation =
                    totalMarketValue > 0 ? (marketValue / totalMarketValue) * 100 : 0;

                  return (
                    <>
                <label className="portfolio-compare-check">
                  <input
                    checked={compareTickers.includes(item.ticker)}
                    onChange={() => toggleCompareTicker(item.ticker)}
                    type="checkbox"
                  />
                  <span>Compare</span>
                </label>
                <div className="portfolio-company-cell">
                  <span>{item.ticker.slice(0, 1)}</span>
                  <div>
                    <strong>{item.stock?.companyName ?? item.ticker}</strong>
                    <small>
                      {item.ticker} • {item.stock?.sector ?? "Unknown sector"}
                    </small>
                    {item.positionNotes && (
                      <small className="portfolio-position-note">
                        {item.positionNotes}
                      </small>
                    )}
                  </div>
                </div>
                <span className="portfolio-list-pill">{item.listName}</span>
                <strong>{getPositionShares(item) || "Not set"}</strong>
                <span>{getPositionCost(item) ? formatCurrency(getPositionCost(item)) : "N/A"}</span>
                <strong>{marketValue ? formatCurrency(marketValue) : "N/A"}</strong>
                <em
                  className={gainLoss >= 0 ? "up" : "down"}
                >
                  {marketValue
                    ? `${gainLoss >= 0 ? "+" : ""}${formatCurrency(gainLoss)} (${gainLossPercent >= 0 ? "+" : ""}${gainLossPercent.toFixed(2)}%)`
                    : "N/A"}
                </em>
                <span>
                  {marketValue
                    ? `${currentAllocation.toFixed(1)}% / ${(item.targetAllocation ?? 0).toFixed(1)}%`
                    : "N/A"}
                </span>
                <div className="portfolio-row-actions">
                  <button type="button" onClick={() => void handleEditPosition(item)}>
                    Edit Position
                  </button>
                  <button type="button" onClick={() => onOpenResearch(item.ticker)}>
                    Research
                  </button>
                </div>
                    </>
                  );
                })()}
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}

function CompareCompaniesView({
  entries,
  selectedTickers,
  onOpenResearch,
  onBackToPortfolio,
  onRemoveTicker,
}: {
  entries: CompareEntry[];
  selectedTickers: string[];
  onOpenResearch: (ticker: string) => void;
  onBackToPortfolio: () => void;
  onRemoveTicker: (ticker: string) => void;
}) {
  const visibleEntries = entries.filter((entry) => entry.stock);
  const metricRows = [
    {
      label: "Price",
      getValue: (entry: CompareEntry) =>
        entry.stock ? `$${entry.stock.price.toFixed(2)}` : "N/A",
    },
    {
      label: "Today's move",
      getValue: (entry: CompareEntry) =>
        entry.stock
          ? `${entry.stock.changePercent >= 0 ? "+" : ""}${entry.stock.changePercent.toFixed(2)}%`
          : "N/A",
      tone: (entry: CompareEntry) =>
        (entry.stock?.changePercent ?? 0) >= 0 ? "up" : "down",
    },
    {
      label: "Market cap",
      getValue: (entry: CompareEntry) => entry.stock?.marketCap ?? "N/A",
    },
    {
      label: "Revenue (TTM)",
      getValue: (entry: CompareEntry) => entry.stock?.revenueTtm ?? "N/A",
    },
    {
      label: "P/E (TTM)",
      getValue: (entry: CompareEntry) => entry.stock?.peRatio ?? "N/A",
    },
    {
      label: "Profit margin",
      getValue: (entry: CompareEntry) =>
        entry.financialReport?.profitMargin ?? "N/A",
    },
    {
      label: "Operating margin",
      getValue: (entry: CompareEntry) =>
        entry.financialReport?.operatingMarginTtm ?? "N/A",
    },
    {
      label: "Return on equity",
      getValue: (entry: CompareEntry) =>
        entry.financialReport?.returnOnEquityTtm ?? "N/A",
    },
    {
      label: "Price / book",
      getValue: (entry: CompareEntry) =>
        entry.financialReport?.priceToBookRatio ?? "N/A",
    },
    {
      label: "EV / revenue",
      getValue: (entry: CompareEntry) =>
        entry.financialReport?.evToRevenue ?? "N/A",
    },
    {
      label: "Latest quarter",
      getValue: (entry: CompareEntry) =>
        entry.financialReport?.latestQuarter ?? "N/A",
    },
    {
      label: "Snapshot trend",
      getValue: (entry: CompareEntry) =>
        entry.performanceSinceFirstSnapshot === null
          ? "N/A"
          : `${entry.performanceSinceFirstSnapshot >= 0 ? "+" : ""}${entry.performanceSinceFirstSnapshot.toFixed(2)}%`,
      tone: (entry: CompareEntry) =>
        (entry.performanceSinceFirstSnapshot ?? 0) >= 0 ? "up" : "down",
    },
  ];

  if (selectedTickers.length < 2 || visibleEntries.length < 2) {
    return (
      <section className="compare-page">
        <div className="compare-hero">
          <div>
            <span className="ticker-badge">Compare</span>
            <h1>Company Comparison</h1>
            <p>
              Compare works best when we stack 2 to 4 saved companies side by
              side across valuation, quality, momentum, and thesis.
            </p>
          </div>
          <div className="compare-hero-actions">
            <button
              className="primary-button compact"
              type="button"
              onClick={onBackToPortfolio}
            >
              Choose companies
            </button>
          </div>
        </div>

        <section className="panel compare-empty-panel">
          <div className="compare-empty-state">
            <strong>Select at least two saved companies</strong>
            <p>
              Head back to the portfolio table, tick the companies you want, and
              then launch compare mode from there.
            </p>
          </div>
        </section>
      </section>
    );
  }

  return (
    <section className="compare-page">
      <div className="compare-hero">
        <div>
          <span className="ticker-badge">Compare</span>
          <h1>Company Comparison</h1>
          <p>
            Put valuation, business quality, chart behavior, and the current
            thesis in one view so we can see the tradeoffs clearly.
          </p>
        </div>
        <div className="compare-hero-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={onBackToPortfolio}
          >
            Edit selection
          </button>
        </div>
      </div>

      <section className="panel compare-grid-panel">
        <div
          className="compare-grid"
          style={{
            gridTemplateColumns: `220px repeat(${visibleEntries.length}, minmax(220px, 1fr))`,
          }}
        >
          <div className="compare-grid-header compare-grid-corner">
            <strong>Metric</strong>
            <span>{visibleEntries.length} companies</span>
          </div>
          {visibleEntries.map((entry) => (
            <div className="compare-grid-header" key={entry.ticker}>
              <div className="compare-company-head">
                <div>
                  <strong>{entry.stock?.companyName ?? entry.ticker}</strong>
                  <small>
                    {entry.ticker} • {entry.stock?.sector ?? "Unknown sector"}
                  </small>
                </div>
                <button type="button" onClick={() => onRemoveTicker(entry.ticker)}>
                  Remove
                </button>
              </div>
              <div className="compare-company-subhead">
                <span>{entry.stock?.exchange ?? "Market"}</span>
                <button type="button" onClick={() => onOpenResearch(entry.ticker)}>
                  Open research
                </button>
              </div>
            </div>
          ))}

          {metricRows.map((row) => (
            <Fragment key={row.label}>
              <div className="compare-metric-label" key={`${row.label}-label`}>
                {row.label}
              </div>
              {visibleEntries.map((entry) => (
                <div
                  className={`compare-metric-value ${
                    row.tone ? row.tone(entry) : ""
                  }`}
                  key={`${row.label}-${entry.ticker}`}
                >
                  {row.getValue(entry)}
                </div>
              ))}
            </Fragment>
          ))}
        </div>
      </section>

      <section className="panel compare-chart-panel">
        <div className="panel-header">
          <h2>Performance View</h2>
          <span>Aligned to each latest saved or live price</span>
        </div>
        <div className="compare-chart-grid">
          {visibleEntries.map((entry) => {
            const chartPoints = alignChartToLatestPrice(
              entry.stock?.chartPoints ?? chartSeriesByTicker[entry.ticker],
              entry.stock?.price ?? 0
            );
            const displayPoints = chartPoints
              ? getChartPointsForRange(chartPoints, "3M")
              : undefined;

            return (
              <article className="compare-chart-card" key={`chart-${entry.ticker}`}>
                <div className="compare-chart-copy">
                  <strong>{entry.ticker}</strong>
                  <span>
                    {entry.latestSnapshot
                      ? `Last snapshot ${formatDate(entry.latestSnapshot.syncedAt)}`
                      : "No saved snapshot yet"}
                  </span>
                </div>
                {displayPoints && displayPoints.length >= 2 ? (
                  <>
                    <CompareSparkline
                      label={`${entry.ticker} performance`}
                      points={displayPoints}
                    />
                    <div className="compare-chart-stats">
                      <span>{formatReturn(displayPoints, Math.min(20, displayPoints.length - 1))} 1M</span>
                      <strong>
                        {formatReturn(
                          displayPoints,
                          Math.min(displayPoints.length - 1, 62)
                        )}{" "}
                        3M
                      </strong>
                    </div>
                  </>
                ) : (
                  <p className="portfolio-muted-copy">
                    Recent chart history is not available for this company yet.
                  </p>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <div className="compare-thesis-grid">
        {visibleEntries.map((entry) => (
          <section className="panel compare-thesis-panel" key={`thesis-${entry.ticker}`}>
            <div className="panel-header">
              <h2>{entry.ticker} Thesis</h2>
              <span>{entry.snapshotCount} snapshots saved</span>
            </div>
            <div className="compare-thesis-body">
              <p>
                {entry.investmentThesis?.summary ??
                  entry.aiReport?.summary ??
                  entry.stock?.summary ??
                  "No thesis has been saved for this company yet."}
              </p>
              <div className="compare-thesis-columns">
                <div>
                  <strong>Bull case</strong>
                  <ul className="risk-list compare-list">
                    {(entry.investmentThesis?.thesisPoints?.length
                      ? entry.investmentThesis.thesisPoints
                      : entry.aiReport?.bullPoints ?? []
                    )
                      .slice(0, 3)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                </div>
                <div>
                  <strong>Risks</strong>
                  <ul className="risk-list compare-list">
                    {(entry.aiReport?.bearPoints ?? entry.investmentThesis?.watchItems ?? [])
                      .slice(0, 3)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                </div>
              </div>
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function InvestmentThesisPanel({
  savedThesis,
  fallbackThesisPoints,
  watchItems,
  thesisStatus,
  thesisMessage,
  onPropose,
  onSave,
}: {
  savedThesis?: ResearchBundle["investmentThesis"];
  fallbackThesisPoints: string[];
  watchItems: string[];
  thesisStatus: "idle" | "proposing" | "saving" | "success" | "error";
  thesisMessage?: string;
  onPropose?: () => Promise<void>;
  onSave?: (input: {
    summary: string;
    thesisPoints: string[];
    watchItems: string[];
  }) => Promise<void>;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState(savedThesis?.summary ?? "");
  const [thesisPointsDraft, setThesisPointsDraft] = useState(
    (savedThesis?.thesisPoints ?? fallbackThesisPoints).join("\n")
  );
  const [watchItemsDraft, setWatchItemsDraft] = useState(
    (savedThesis?.watchItems ?? watchItems).join("\n")
  );

  useEffect(() => {
    if (isEditing) {
      return;
    }

    setSummaryDraft(savedThesis?.summary ?? "");
    setThesisPointsDraft((savedThesis?.thesisPoints ?? fallbackThesisPoints).join("\n"));
    setWatchItemsDraft((savedThesis?.watchItems ?? watchItems).join("\n"));
  }, [fallbackThesisPoints, isEditing, savedThesis, watchItems]);

  const displayThesisPoints = savedThesis?.thesisPoints?.length
    ? savedThesis.thesisPoints
    : fallbackThesisPoints;
  const displayWatchItems = savedThesis?.watchItems?.length
    ? savedThesis.watchItems
    : watchItems;

  const handleSave = async () => {
    const nextPoints = thesisPointsDraft
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const nextWatchItems = watchItemsDraft
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);

    await onSave?.({
      summary: summaryDraft.trim(),
      thesisPoints: nextPoints,
      watchItems: nextWatchItems,
    });
    setIsEditing(false);
  };

  return (
    <section className="panel thesis-panel">
      <div className="panel-header">
        <h2>Investment Thesis</h2>
        <div className="panel-actions">
          <button type="button" onClick={() => void onPropose?.()}>
            {thesisStatus === "proposing" ? "Proposing..." : "Propose"}
          </button>
          <button type="button" onClick={() => setIsEditing((current) => !current)}>
            {isEditing ? "Cancel" : "Edit"}
          </button>
        </div>
      </div>

      {isEditing ? (
        <div className="thesis-editor">
          <label>
            Thesis summary
            <textarea
              value={summaryDraft}
              onChange={(event) => setSummaryDraft(event.target.value)}
              placeholder="Write the core reason this company belongs in the portfolio."
            />
          </label>
          <label>
            Thesis points
            <textarea
              value={thesisPointsDraft}
              onChange={(event) => setThesisPointsDraft(event.target.value)}
              placeholder="One thesis point per line"
            />
          </label>
          <label>
            What to watch
            <textarea
              value={watchItemsDraft}
              onChange={(event) => setWatchItemsDraft(event.target.value)}
              placeholder="One validation or invalidation item per line"
            />
          </label>
          <div className="thesis-editor-actions">
            <button className="secondary-button" type="button" onClick={() => setIsEditing(false)}>
              Cancel
            </button>
            <button className="primary-button compact" type="button" onClick={() => void handleSave()}>
              {thesisStatus === "saving" ? "Saving..." : "Save thesis"}
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="thesis-summary">
            <p>{savedThesis?.summary || "Propose an investment thesis from live research data, then refine it into your own conviction case."}</p>
            <small>{savedThesis ? `${savedThesis.source} • ${formatDate(savedThesis.updatedAt)}` : "No saved thesis yet"}</small>
          </div>
          <div className="check-list">
            {displayThesisPoints.map((item) => (
              <div className="check-row" key={item}>
                <Circle size={17} />
                <span>{item}</span>
              </div>
            ))}
          </div>
          {displayWatchItems.length > 0 && (
            <div className="thesis-watch">
              <strong>What to watch</strong>
              <ul className="risk-list">
                {displayWatchItems.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {thesisMessage && <p className={`sync-message ${thesisStatus}`}>{thesisMessage}</p>}
    </section>
  );
}

function PortfolioInsightCard({
  label,
  title,
  value,
  tone,
}: {
  label: string;
  title: string;
  value: string;
  tone?: "up" | "down";
}) {
  return (
    <article className={`portfolio-insight-card${tone ? ` ${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{title}</strong>
      <p>{value}</p>
    </article>
  );
}

function CompareSparkline({
  points,
  label,
}: {
  points: number[];
  label: string;
}) {
  const width = 240;
  const height = 88;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const path = points
    .map((value, index) => {
      const x =
        points.length === 1 ? 0 : (index / (points.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="compare-sparkline">
      <svg aria-label={label} role="img" viewBox={`0 0 ${width} ${height}`}>
        <polyline
          fill="none"
          points={path}
          stroke="#2563eb"
          strokeWidth="2.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({
  title,
  action,
  actions,
  meta,
  children,
  onAction,
}: {
  title: ReactNode;
  action?: string;
  actions?: ReactNode;
  meta?: string;
  children: ReactNode;
  onAction?: () => void;
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
        {actions && <div className="panel-actions">{actions}</div>}
        {action && (
          <button onClick={onAction} type="button">
            {action}
          </button>
        )}
        {meta && <span>{meta}</span>}
      </div>
      {children}
    </section>
  );
}

function PriceChart({ stock }: {
  stock: ResearchBundle["stock"];
}) {
  const ticker = stock.ticker;
  const [selectedRange, setSelectedRange] = useState<
    "1D" | "5D" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "5Y" | "MAX"
  >("3M");
  const [clientChartPoints, setClientChartPoints] = useState<number[] | null>(null);
  const [chartFetchStatus, setChartFetchStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");

  useEffect(() => {
    let cancelled = false;

    if (stock.chartPoints?.length) {
      setClientChartPoints(null);
      setChartFetchStatus("ready");
      return () => {
        cancelled = true;
      };
    }

    if (chartSeriesByTicker[ticker]) {
      setClientChartPoints(null);
      setChartFetchStatus("ready");
      return () => {
        cancelled = true;
      };
    }

    if (!twelveDataClientKey) {
      setClientChartPoints(null);
      setChartFetchStatus("error");
      return () => {
        cancelled = true;
      };
    }

    const loadChartHistory = async () => {
      setChartFetchStatus("loading");

      try {
        const points = await fetchChartHistoryFromClientProviders(ticker);

        if (cancelled) {
          return;
        }

        if (points && points.length >= 2) {
          setClientChartPoints(points);
          setChartFetchStatus("ready");
          return;
        }

        setClientChartPoints(null);
        setChartFetchStatus("error");
      } catch {
        if (cancelled) {
          return;
        }

        setClientChartPoints(null);
        setChartFetchStatus("error");
      }
    };

    void loadChartHistory();

    return () => {
      cancelled = true;
    };
  }, [stock.chartPoints, ticker]);

  const chartPoints = alignChartToLatestPrice(
    stock.chartPoints ?? clientChartPoints ?? chartSeriesByTicker[ticker],
    stock.price
  );
  const displayedChartPoints = chartPoints
    ? getChartPointsForRange(chartPoints, selectedRange)
    : chartPoints;

  if (!displayedChartPoints || displayedChartPoints.length < 2) {
    return (
      <section className="panel chart-panel">
        <div className="chart-header">
          <h2>Price Chart</h2>
          <div className="range-tabs">
            {["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"].map(
              (range) => (
                <button
                  className={range === selectedRange ? "selected" : ""}
                  key={range}
                  onClick={() =>
                    setSelectedRange(
                      range as
                        | "1D"
                        | "5D"
                        | "1M"
                        | "3M"
                        | "6M"
                        | "YTD"
                        | "1Y"
                        | "5Y"
                        | "MAX"
                    )
                  }
                  type="button"
                >
                  {range}
                </button>
              )
            )}
          </div>
          <button className="select-button">Line</button>
          <button className="select-button">Compare</button>
          <button className="icon-button small">
            <Settings size={16} />
          </button>
        </div>

        <div className="chart-empty-state">
          <strong>
            {chartFetchStatus === "loading" ? "Loading live chart..." : "Live chart unavailable"}
          </strong>
          <p>
            {chartFetchStatus === "loading"
              ? `Fetching recent price history for ${ticker} from Twelve Data.`
              : `The latest quote for ${ticker} synced successfully, but historical chart data is currently unavailable.`}
          </p>
        </div>
      </section>
    );
  }

  const width = 920;
  const height = 290;
  const plot = {
    left: 58,
    right: 18,
    top: 18,
    bottom: 42,
  };
  const plotWidth = width - plot.left - plot.right;
  const plotHeight = height - plot.top - plot.bottom;
  const plotBottom = plot.top + plotHeight;
  const min = Math.min(...displayedChartPoints) - 20;
  const max = Math.max(...displayedChartPoints) + 20;
  const priceRange = max - min || 1;
  const points = displayedChartPoints.map((value, index) => {
    const x =
      displayedChartPoints.length === 1
        ? plot.left + plotWidth
        : plot.left + (index / (displayedChartPoints.length - 1)) * plotWidth;
    const y = plot.top + plotHeight - ((value - min) / priceRange) * plotHeight;
    return [x, y] as const;
  });
  const line = points.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `${plot.left},${plotBottom} ${line} ${plot.left + plotWidth},${plotBottom}`;
  const formatAxisPrice = (value: number) =>
    value >= 100 ? value.toFixed(0) : value.toFixed(2);
  const yTicks = [0, 1, 2, 3, 4].map((tickIndex) => {
    const ratio = tickIndex / 4;
    return {
      y: plot.top + plotHeight * ratio,
      value: max - priceRange * ratio,
    };
  });
  const formatAxisDate = (date: Date) => {
    const month = date.toLocaleString("en-US", { month: "short" });
    return `${String(date.getDate()).padStart(2, "0")}-${month}`;
  };
  const today = new Date();
  const daysAgo = (days: number) => {
    const date = new Date(today);
    date.setDate(today.getDate() - days);
    return date;
  };
  const monthsAgo = (months: number) => {
    const date = new Date(today);
    date.setMonth(today.getMonth() - months);
    return date;
  };
  const buildDateTicks = () => {
    const createTicks = (dates: Date[]) =>
      dates.map((date, index) => ({
        x:
          dates.length === 1
            ? plot.left + plotWidth
            : plot.left + (index / (dates.length - 1)) * plotWidth,
        label: formatAxisDate(date),
      }));

    if (selectedRange === "1D") {
      return createTicks([today]);
    }

    if (selectedRange === "5D") {
      return createTicks([5, 4, 3, 2, 1, 0].map(daysAgo));
    }

    if (selectedRange === "1M") {
      return createTicks([30, 21, 14, 7, 0].map(daysAgo));
    }

    if (selectedRange === "3M") {
      return createTicks([3, 2, 1, 0].map(monthsAgo));
    }

    if (selectedRange === "6M") {
      return createTicks([6, 5, 4, 3, 2, 1, 0].map(monthsAgo));
    }

    if (selectedRange === "YTD") {
      const start = new Date(today.getFullYear(), 0, 1);
      const dates = [start];
      for (let month = 1; month < today.getMonth(); month += 1) {
        dates.push(new Date(today.getFullYear(), month, 1));
      }
      dates.push(today);
      return createTicks(dates.length > 7 ? dates.filter((_, index) => index % 2 === 0 || index === dates.length - 1) : dates);
    }

    if (selectedRange === "1Y") {
      return createTicks([12, 10, 8, 6, 4, 2, 0].map(monthsAgo));
    }

    if (selectedRange === "5Y") {
      return createTicks([60, 48, 36, 24, 12, 0].map(monthsAgo));
    }

    return createTicks([
      monthsAgo(Math.max(1, Math.round(displayedChartPoints.length / 21))),
      monthsAgo(Math.max(1, Math.round(displayedChartPoints.length / 42))),
      today,
    ]);
  };
  const xTicks = buildDateTicks();
  const performanceRanges = [
    ["1D", 1],
    ["5D", 5],
    ["1M", 21],
    ["3M", 63],
    ["MAX", displayedChartPoints.length - 1],
  ] as const;

  return (
    <section className="panel chart-panel">
      <div className="chart-header">
        <h2>Price Chart</h2>
        <div className="range-tabs">
          {["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"].map(
            (range) => (
              <button
                className={range === selectedRange ? "selected" : ""}
                key={range}
                onClick={() =>
                  setSelectedRange(
                    range as
                      | "1D"
                      | "5D"
                      | "1M"
                      | "3M"
                      | "6M"
                      | "YTD"
                      | "1Y"
                      | "5Y"
                      | "MAX"
                  )
                }
                type="button"
              >
                {range}
              </button>
            )
          )}
        </div>
        <button className="select-button">Line</button>
        <button className="select-button">Compare</button>
        <button className="icon-button small">
          <Settings size={16} />
        </button>
      </div>

      <div className="chart-wrap">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${ticker} price chart`}>
          <defs>
            <linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#2563eb" stopOpacity="0" />
            </linearGradient>
          </defs>
          {yTicks.map((tick) => (
            <Fragment key={tick.y}>
              <line
                x1={plot.left}
                x2={plot.left + plotWidth}
                y1={tick.y}
                y2={tick.y}
              />
              <text
                className="chart-tick-label y"
                dominantBaseline="middle"
                x={plot.left - 10}
                y={tick.y}
              >
                {formatAxisPrice(tick.value)}
              </text>
            </Fragment>
          ))}
          <line
            className="chart-axis-line"
            x1={plot.left}
            x2={plot.left + plotWidth}
            y1={plotBottom}
            y2={plotBottom}
          />
          <line
            className="chart-axis-line"
            x1={plot.left}
            x2={plot.left}
            y1={plot.top}
            y2={plotBottom}
          />
          {xTicks.map((tick, index) => (
            <text
              className="chart-tick-label x"
              key={`${tick.label}-${index}`}
              textAnchor={
                index === 0
                  ? "start"
                  : index === xTicks.length - 1
                    ? "end"
                    : "middle"
              }
              x={tick.x}
              y={plotBottom + 22}
            >
              {tick.label}
            </text>
          ))}
          <text className="chart-axis-title x" textAnchor="middle" x={plot.left + plotWidth / 2} y={height - 6}>
            Time
          </text>
          <text
            className="chart-axis-title y"
            textAnchor="middle"
            transform={`translate(14 ${plot.top + plotHeight / 2}) rotate(-90)`}
          >
            Price ($)
          </text>
          <polygon points={area} fill="url(#chart-fill)" />
          <polyline points={line} fill="none" stroke="#1d4ed8" strokeWidth="2.5" />
        </svg>
        <div className="chart-price-label">
          {stock.price.toFixed(2)}
        </div>
      </div>

      <div className="performance-row">
        {performanceRanges.map(([range, lookback]) => (
          <div className={range === selectedRange ? "selected" : ""} key={range}>
            <span>{range}</span>
            <strong>{formatReturn(displayedChartPoints, lookback)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResearchHighlight({
  item,
  index = 0,
  risk,
}: {
  item: ResearchItem;
  index?: number;
  risk?: boolean;
}) {
  return (
    <article className={risk ? "research-highlight risk" : "research-highlight"}>
      {risk ? (
        <TriangleAlert size={22} />
      ) : index === 0 ? (
        <TrendingUp size={22} />
      ) : (
        <BarChart3 size={22} />
      )}
      <div>
        <h3>{item.title}</h3>
        <p>{item.body}</p>
      </div>
    </article>
  );
}

function BriefPointSection({
  items,
  title,
  tone,
}: {
  items: string[];
  title: string;
  tone: "strength" | "risk" | "watch";
}) {
  return (
    <section className={`brief-point-section ${tone}`}>
      <h3>
        {tone === "strength" ? (
          <TrendingUp size={17} />
        ) : tone === "risk" ? (
          <TriangleAlert size={17} />
        ) : (
          <Bell size={17} />
        )}
        {title}
      </h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function formatDate(timestamp: number) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(timestamp));
}

function formatDayMonth(timestamp: number) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(new Date(timestamp));
}

function formatQuoteTimestamp(timestamp?: number) {
  if (!timestamp || !Number.isFinite(timestamp)) {
    return "Quote time unavailable";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  }).format(new Date(timestamp));
}

function formatTime(timestamp: number) {
  return new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function formatDateTime(timestamp: number) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function formatSignedNumber(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en", {
    currency: "USD",
    maximumFractionDigits: value >= 10_000 ? 0 : 2,
    style: "currency",
  }).format(value);
}

function getPositionShares(item: PortfolioItem) {
  return item.shares && item.shares > 0 ? item.shares : 0;
}

function parseAbbreviatedMetric(value?: string) {
  if (!value || value === "N/A" || value === "None") {
    return null;
  }

  const trimmed = value.trim().replace(/[$,%]/g, "");
  const suffix = trimmed.slice(-1).toUpperCase();
  const multiplier =
    suffix === "T"
      ? 1_000_000_000_000
      : suffix === "B"
        ? 1_000_000_000
        : suffix === "M"
          ? 1_000_000
          : 1;
  const numeric = Number(
    suffix === "T" || suffix === "B" || suffix === "M"
      ? trimmed.slice(0, -1)
      : trimmed
  );

  return Number.isFinite(numeric) ? numeric * multiplier : null;
}

function getPositionCost(item: PortfolioItem) {
  return item.averageCost && item.averageCost > 0 ? item.averageCost : 0;
}

function getPositionMarketValue(item: PortfolioItem) {
  return getPositionShares(item) * (item.stock?.price ?? 0);
}

function getPositionCostBasis(item: PortfolioItem) {
  return getPositionShares(item) * getPositionCost(item);
}

function getPositionGainLoss(item: PortfolioItem) {
  return getPositionMarketValue(item) - getPositionCostBasis(item);
}

function getPositionGainLossPercent(item: PortfolioItem) {
  const costBasis = getPositionCostBasis(item);
  return costBasis > 0 ? (getPositionGainLoss(item) / costBasis) * 100 : 0;
}

function formatReturn(points: number[], lookback: number) {
  const latest = points[points.length - 1];
  const baseline = points[Math.max(points.length - 1 - lookback, 0)];

  if (!Number.isFinite(latest) || !Number.isFinite(baseline) || baseline === 0) {
    return "N/A";
  }

  const changePercent = ((latest - baseline) / baseline) * 100;
  return `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%`;
}

function alignChartToLatestPrice(points: number[] | undefined, latestPrice: number) {
  if (!points || points.length < 2 || !Number.isFinite(latestPrice)) {
    return points;
  }

  const lastPoint = points[points.length - 1];
  if (!Number.isFinite(lastPoint)) {
    return points;
  }

  const delta = latestPrice - lastPoint;
  if (Math.abs(delta) < 0.005) {
    return points;
  }

  return points.map((point) => point + delta);
}

function getChartPointsForRange(
  points: number[],
  range: "1D" | "5D" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "5Y" | "MAX"
) {
  const lookbackByRange: Record<typeof range, number> = {
    "1D": 2,
    "5D": 5,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    YTD: 180,
    "1Y": 252,
    "5Y": points.length,
    MAX: points.length,
  };

  const lookback = lookbackByRange[range];
  return points.slice(-Math.min(lookback, points.length));
}
