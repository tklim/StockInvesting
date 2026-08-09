import { v } from "convex/values";
import {
  internalAction,
  internalMutation,
  internalQuery,
  type ActionCtx,
} from "./_generated/server";
import { internal } from "./_generated/api";
import type { Doc } from "./_generated/dataModel";
import {
  SIGNAL_HORIZON_DAYS,
  SIGNAL_MODEL_VERSION,
  buildCurrentFeatures,
  buildFallbackFeatures,
  buildHistoricalObservations,
  calculateCompositeScore,
  calculateDataCoverage,
  calculateAnalogForecast,
  classifyAggressiveSignal,
  roundScore,
  scoreMarketFeatures,
  isAiSignalFresh,
  type AnalogForecast,
  type DailyPriceBar,
  type FactorScores,
  type SignalObservation,
} from "./lib/signalModel";

declare const process: {
  env: Record<string, string | undefined>;
};

const normalizeTicker = (ticker: string) => ticker.trim().toUpperCase();
const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);
const mean = (values: number[]) =>
  values.length
    ? values.reduce((total, value) => total + value, 0) / values.length
    : 50;

const featureValidator = v.object({
  return1m: v.number(),
  return3m: v.number(),
  return6m: v.number(),
  return12m: v.number(),
  relativeReturn6m: v.number(),
  sma200Distance: v.number(),
  volatility63d: v.number(),
  maxDrawdown126d: v.number(),
});

const barValidator = v.object({
  ticker: v.string(),
  tradingDate: v.string(),
  close: v.number(),
  adjustedClose: v.number(),
  volume: v.optional(v.number()),
  source: v.string(),
  fetchedAt: v.number(),
});

const observationValidator = v.object({
  ticker: v.string(),
  observationDate: v.string(),
  features: featureValidator,
  forwardReturn: v.number(),
  forwardExcessReturn: v.number(),
  win: v.boolean(),
  outperform: v.boolean(),
});

const factorScoresValidator = v.object({
  market: v.number(),
  growth: v.number(),
  profitability: v.number(),
  balanceSheet: v.number(),
  valuation: v.number(),
  ai: v.number(),
});

type FactorResult = {
  score: number;
  coverage: number;
  drivers: Array<{ label: string; score: number }>;
};

type SignalRefreshResult = {
  ticker: string;
  rating: "BUY" | "HOLD" | "SELL";
  score: number;
  provisional: boolean;
  calibrated: boolean;
  coverage: number;
  providerError?: string;
};

type FinancialPeriod = Doc<"financialReports">["annual"][number];

const parseNumber = (value?: string) => {
  if (!value || value.trim().toUpperCase() === "N/A") return undefined;
  const parsed = Number(value.replace(/[$,%x,]/gi, "").trim());
  return Number.isFinite(parsed) ? parsed : undefined;
};

const parsePercent = (value?: string) => {
  const parsed = parseNumber(value);
  if (parsed === undefined) return undefined;
  return value?.includes("%") ? parsed / 100 : Math.abs(parsed) > 1 ? parsed / 100 : parsed;
};

const boundedScore = (value: number, weak: number, strong: number) =>
  clamp(((value - weak) / (strong - weak)) * 100, 0, 100);

const periodValue = (
  period: FinancialPeriod | undefined,
  field: keyof NonNullable<FinancialPeriod["normalized"]>
) => period?.normalized?.[field];

const growthRate = (latest?: number, previous?: number) => {
  if (latest === undefined || previous === undefined || previous === 0) return undefined;
  return (latest - previous) / Math.abs(previous);
};

const averageAvailable = (
  rows: Array<{ label: string; score?: number }>
): FactorResult => {
  const available = rows.filter(
    (row): row is { label: string; score: number } => row.score !== undefined
  );
  return {
    score: available.length ? mean(available.map((row) => row.score)) : 50,
    coverage: rows.length ? (available.length / rows.length) * 100 : 0,
    drivers: available,
  };
};

const scoreFinancialFactors = (
  stock: Doc<"stocks"> | null,
  report: Doc<"financialReports"> | null
) => {
  const annual = [...(report?.annual ?? [])].sort((left, right) =>
    right.fiscalDateEnding.localeCompare(left.fiscalDateEnding)
  );
  const latest = annual[0];
  const previous = annual[1];
  const latestRevenue = periodValue(latest, "totalRevenue");
  const latestNetIncome = periodValue(latest, "netIncome");
  const latestFcf = periodValue(latest, "freeCashFlow");

  const revenueGrowth = growthRate(
    latestRevenue,
    periodValue(previous, "totalRevenue")
  );
  const earningsGrowth = growthRate(
    latestNetIncome,
    periodValue(previous, "netIncome")
  );
  const fcfGrowth = growthRate(latestFcf, periodValue(previous, "freeCashFlow"));
  const growth = averageAvailable([
    {
      label: "Revenue growth",
      score:
        revenueGrowth === undefined
          ? undefined
          : boundedScore(revenueGrowth, -0.15, 0.3),
    },
    {
      label: "Earnings growth",
      score:
        earningsGrowth === undefined
          ? undefined
          : boundedScore(earningsGrowth, -0.25, 0.4),
    },
    {
      label: "Free-cash-flow growth",
      score:
        fcfGrowth === undefined ? undefined : boundedScore(fcfGrowth, -0.25, 0.4),
    },
  ]);

  const profitMargin = parsePercent(report?.profitMargin);
  const operatingMargin = parsePercent(report?.operatingMarginTtm);
  const roe = parsePercent(report?.returnOnEquityTtm);
  const fcfMargin =
    latestFcf !== undefined && latestRevenue
      ? latestFcf / Math.abs(latestRevenue)
      : undefined;
  const profitability = averageAvailable([
    {
      label: "Net profit margin",
      score:
        profitMargin === undefined
          ? undefined
          : boundedScore(profitMargin, -0.05, 0.3),
    },
    {
      label: "Operating margin",
      score:
        operatingMargin === undefined
          ? undefined
          : boundedScore(operatingMargin, 0, 0.35),
    },
    {
      label: "Return on equity",
      score: roe === undefined ? undefined : boundedScore(roe, 0, 0.35),
    },
    {
      label: "Free-cash-flow margin",
      score:
        fcfMargin === undefined ? undefined : boundedScore(fcfMargin, -0.05, 0.25),
    },
  ]);

  const assets = periodValue(latest, "totalAssets");
  const liabilities = periodValue(latest, "totalLiabilities");
  const equity = periodValue(latest, "totalShareholderEquity");
  const liabilitiesToAssets =
    liabilities !== undefined && assets ? liabilities / Math.abs(assets) : undefined;
  const equityToAssets =
    equity !== undefined && assets ? equity / Math.abs(assets) : undefined;
  const balanceSheet = averageAvailable([
    {
      label: "Liabilities to assets",
      score:
        liabilitiesToAssets === undefined
          ? undefined
          : boundedScore(liabilitiesToAssets, 0.9, 0.25),
    },
    {
      label: "Equity to assets",
      score:
        equityToAssets === undefined
          ? undefined
          : boundedScore(equityToAssets, 0.05, 0.65),
    },
    {
      label: "Positive free cash flow",
      score: latestFcf === undefined ? undefined : latestFcf > 0 ? 80 : 20,
    },
  ]);

  const pe = parseNumber(stock?.peRatio);
  const priceToBook = parseNumber(report?.priceToBookRatio);
  const evToRevenue = parseNumber(report?.evToRevenue);
  const evToEbitda = parseNumber(report?.evToEbitda);
  const valuation = averageAvailable([
    {
      label: "Price-to-earnings valuation",
      score:
        pe === undefined || pe <= 0 ? undefined : boundedScore(pe, 60, 10),
    },
    {
      label: "Price-to-book valuation",
      score:
        priceToBook === undefined || priceToBook <= 0
          ? undefined
          : boundedScore(priceToBook, 15, 1),
    },
    {
      label: "Enterprise value to revenue",
      score:
        evToRevenue === undefined || evToRevenue <= 0
          ? undefined
          : boundedScore(evToRevenue, 15, 1),
    },
    {
      label: "Enterprise value to EBITDA",
      score:
        evToEbitda === undefined || evToEbitda <= 0
          ? undefined
          : boundedScore(evToEbitda, 40, 7),
    },
  ]);

  return { growth, profitability, balanceSheet, valuation };
};

const scoreMarketModel = (
  featureScore: number,
  forecast: AnalogForecast
) => {
  if (!forecast.calibrated) return featureScore;
  const probabilityScore = mean([
    (forecast.winProbability ?? 0.5) * 100,
    (forecast.outperformProbability ?? 0.5) * 100,
    boundedScore(forecast.expectedReturn ?? 0, -0.25, 0.35),
  ]);
  return featureScore * 0.55 + probabilityScore * 0.45;
};

type TwelveDataResponse = {
  values?: Array<{
    datetime?: string;
    close?: string;
    volume?: string;
  }>;
  status?: string;
  code?: number;
  message?: string;
};

const fetchTwelveDataHistory = async (ticker: string, apiKey: string) => {
  const endpoint = new URL("https://api.twelvedata.com/time_series");
  endpoint.searchParams.set("symbol", ticker);
  endpoint.searchParams.set("interval", "1day");
  endpoint.searchParams.set("outputsize", "3000");
  endpoint.searchParams.set("adjust", "all");
  endpoint.searchParams.set("order", "asc");
  endpoint.searchParams.set("apikey", apiKey);
  const response = await fetch(endpoint.toString());
  if (!response.ok) throw new Error(`Twelve Data history returned HTTP ${response.status}.`);
  const payload = (await response.json()) as TwelveDataResponse;
  if (payload.status === "error" || !payload.values?.length) {
    throw new Error(payload.message || `Twelve Data returned no history for ${ticker}.`);
  }
  const fetchedAt = Date.now();
  const bars: DailyPriceBar[] = payload.values.flatMap((item) => {
      const close = Number(item.close);
      const volume = Number(item.volume);
      if (!item.datetime || !Number.isFinite(close) || close <= 0) return [];
      return [{
        ticker,
        tradingDate: item.datetime.slice(0, 10),
        close,
        adjustedClose: close,
        ...(Number.isFinite(volume) ? { volume } : {}),
        source: "Twelve Data adjust=all",
        fetchedAt,
      } satisfies DailyPriceBar];
    });
  if (bars.length < 20) throw new Error(`Twelve Data history for ${ticker} was incomplete.`);
  return bars.slice(-3000);
};

const persistBars = async (ctx: ActionCtx, bars: DailyPriceBar[]) => {
  for (let index = 0; index < bars.length; index += 75) {
    await ctx.runMutation(internal.signals.upsertBarsBatch, {
      bars: bars.slice(index, index + 75),
    });
  }
  const keepFromDate = [...bars].sort((left, right) =>
    left.tradingDate.localeCompare(right.tradingDate)
  )[0]?.tradingDate;
  if (keepFromDate) {
    for (let pass = 0; pass < 20; pass += 1) {
      const result = (await ctx.runMutation(internal.signals.pruneTickerBars, {
        ticker: bars[0].ticker,
        keepFromDate,
      })) as { deleted: number };
      if (result.deleted < 200) break;
    }
  }
};

const historyNeedsRefresh = (bars: DailyPriceBar[]) => {
  const latestFetch = Math.max(0, ...bars.map((bar) => bar.fetchedAt));
  return bars.length < 1260 || Date.now() - latestFetch > 24 * 60 * 60 * 1000;
};

const historyYears = (bars: DailyPriceBar[]) => {
  if (bars.length < 2) return 0;
  const ordered = [...bars].sort((left, right) =>
    left.tradingDate.localeCompare(right.tradingDate)
  );
  return Math.max(
    0,
    (Date.parse(ordered[ordered.length - 1].tradingDate) -
      Date.parse(ordered[0].tradingDate)) /
      (365.25 * 24 * 60 * 60 * 1000)
  );
};

const runSignalRefresh = async (
  ctx: ActionCtx,
  rawTicker: string,
  fetchHistory: boolean
): Promise<SignalRefreshResult> => {
  const ticker = normalizeTicker(rawTicker);
  const requestedAt = Date.now();
  let providerError: string | undefined;

  try {
    let tickerBars = (await ctx.runQuery(internal.signals.getTickerBars, {
      ticker,
    })) as DailyPriceBar[];
    let spyBars = (await ctx.runQuery(internal.signals.getTickerBars, {
      ticker: "SPY",
    })) as DailyPriceBar[];

    if (
      fetchHistory &&
      (historyNeedsRefresh(tickerBars) || historyNeedsRefresh(spyBars))
    ) {
      const apiKey = process.env.TWELVEDATA_API_KEY?.trim();
      if (!apiKey) {
        providerError = "TWELVEDATA_API_KEY is not configured; using stored or provisional data.";
      } else {
        try {
          if (historyNeedsRefresh(spyBars)) {
            spyBars = await fetchTwelveDataHistory("SPY", apiKey);
            await persistBars(ctx, spyBars);
          }
          if (ticker === "SPY") {
            tickerBars = spyBars;
          } else if (historyNeedsRefresh(tickerBars)) {
            tickerBars = await fetchTwelveDataHistory(ticker, apiKey);
            await persistBars(ctx, tickerBars);
          }
          await ctx.runMutation(internal.dataSources.recordInternalEvent, {
            service: "Signal Engine",
            operation: "Adjusted daily history backfill",
            status: "success",
            provider: "Twelve Data",
            ticker,
            requestedAt,
            message: `${tickerBars.length} adjusted daily bars available.`,
          });
        } catch (error) {
          providerError = error instanceof Error ? error.message : String(error);
          await ctx.runMutation(internal.dataSources.recordInternalEvent, {
            service: "Signal Engine",
            operation: "Adjusted daily history backfill",
            status: "error",
            provider: "Twelve Data",
            ticker,
            requestedAt,
            message: providerError,
          });
          tickerBars = (await ctx.runQuery(internal.signals.getTickerBars, {
            ticker,
          })) as DailyPriceBar[];
          spyBars = (await ctx.runQuery(internal.signals.getTickerBars, {
            ticker: "SPY",
          })) as DailyPriceBar[];
        }
      }
    }

    const tickerObservations = buildHistoricalObservations(ticker, tickerBars, spyBars);
    if (tickerObservations.length) {
      await ctx.runMutation(internal.signals.replaceTickerObservations, {
        ticker,
        observations: tickerObservations,
      });
    }

    const inputs = await ctx.runQuery(internal.signals.getSignalInputs, { ticker });
    const allObservations = (await ctx.runQuery(
      internal.signals.getAllObservations,
      {}
    )) as SignalObservation[];
    const typedInputs = inputs as {
      stock: Doc<"stocks"> | null;
      financialReport: Doc<"financialReports"> | null;
      aiReport: Doc<"aiReports"> | null;
      previousSignal: Doc<"stockSignals"> | null;
    };
    if (!typedInputs.stock) throw new Error(`${ticker} has no synced stock record.`);

    const features =
      buildCurrentFeatures(tickerBars, spyBars) ??
      buildFallbackFeatures(typedInputs.stock.chartPoints ?? []);
    const asOfDate =
      [...tickerBars].sort((left, right) =>
        left.tradingDate.localeCompare(right.tradingDate)
      )[tickerBars.length - 1]?.tradingDate ??
      new Date(typedInputs.stock.updatedAt).toISOString().slice(0, 10);
    const forecast: AnalogForecast = features
      ? calculateAnalogForecast(
          features,
          allObservations,
          historyYears(tickerBars),
          asOfDate
        )
      : ({
          sampleSize: 0,
          tickerCount: 0,
          calibrationSampleSize: 0,
          calibrated: false,
          confidence: "low",
        } satisfies AnalogForecast);
    const marketFeatures = scoreMarketFeatures(features);
    const financial = scoreFinancialFactors(
      typedInputs.stock,
      typedInputs.financialReport
    );
    const latestNonAiInput = Math.max(
      typedInputs.stock.updatedAt,
      typedInputs.financialReport?.updatedAt ?? 0
    );
    const aiFresh = isAiSignalFresh({
      signalScore: typedInputs.aiReport?.signalScore,
      generatedAt: typedInputs.aiReport?.generatedAt,
      latestMarketSync: typedInputs.stock.updatedAt,
      latestFinancialSync: typedInputs.financialReport?.updatedAt,
      now: Date.now(),
    });
    const aiScore = aiFresh
      ? clamp(typedInputs.aiReport?.signalScore ?? 50, 0, 100)
      : 50;
    const factorScores: FactorScores = {
      market: roundScore(scoreMarketModel(marketFeatures.score, forecast)),
      growth: roundScore(financial.growth.score),
      profitability: roundScore(financial.profitability.score),
      balanceSheet: roundScore(financial.balanceSheet.score),
      valuation: roundScore(financial.valuation.score),
      ai: roundScore(aiScore),
    };
    const compositeScore = calculateCompositeScore(factorScores);
    const dataCoverage = calculateDataCoverage({
      market: marketFeatures.coverage,
      growth: financial.growth.coverage,
      profitability: financial.profitability.coverage,
      balanceSheet: financial.balanceSheet.coverage,
      valuation: financial.valuation.coverage,
      ai: aiFresh ? 100 : 0,
    });
    const classification = classifyAggressiveSignal({
      compositeScore,
      coverage: dataCoverage,
      forecast,
    });
    const drivers = [
      { label: "Price trend and statistical setup", score: factorScores.market },
      ...financial.growth.drivers,
      ...financial.profitability.drivers,
      ...financial.balanceSheet.drivers,
      ...financial.valuation.drivers,
      ...(aiFresh
        ? [{ label: "AI Research Brief", score: factorScores.ai }]
        : []),
    ];
    const orderedBars = [...tickerBars].sort((left, right) =>
      left.tradingDate.localeCompare(right.tradingDate)
    );
    const computedAt = Date.now();
    await ctx.runMutation(internal.signals.upsertSignal, {
      ticker,
      rating: classification.rating,
      provisional: classification.provisional,
      compositeScore,
      horizonDays: SIGNAL_HORIZON_DAYS,
      winProbability: forecast.calibrated ? forecast.winProbability : undefined,
      lossProbability: forecast.calibrated ? forecast.lossProbability : undefined,
      outperformProbability: forecast.calibrated
        ? forecast.outperformProbability
        : undefined,
      expectedReturn: forecast.expectedReturn,
      expectedExcessReturn: forecast.expectedExcessReturn,
      downsideP10: forecast.downsideP10,
      factorScores,
      confidence: forecast.confidence,
      sampleSize: forecast.sampleSize,
      tickerCount: forecast.tickerCount,
      calibrationSampleSize: forecast.calibrationSampleSize,
      brierScore: forecast.brierScore,
      dataCoverage,
      topPositiveDrivers: [...drivers]
        .sort((left, right) => right.score - left.score)
        .slice(0, 3)
        .map((item) => `${item.label} (${Math.round(item.score)}/100)`),
      topNegativeDrivers: [...drivers]
        .sort((left, right) => left.score - right.score)
        .slice(0, 3)
        .map((item) => `${item.label} (${Math.round(item.score)}/100)`),
      aiRationale: aiFresh ? typedInputs.aiReport?.signalRationale : undefined,
      aiFresh,
      modelVersion: SIGNAL_MODEL_VERSION,
      dataStatus: providerError
        ? "stale"
        : forecast.calibrated
          ? "ready"
          : "insufficient",
      source: "Twelve Data adjusted prices + Convex factor model",
      historyStart: orderedBars[0]?.tradingDate,
      historyEnd: orderedBars[orderedBars.length - 1]?.tradingDate,
      computedAt,
      inputsUpdatedAt: latestNonAiInput,
    });
    await ctx.runMutation(internal.dataSources.recordInternalEvent, {
      service: "Signal Engine",
      operation: "Six-month signal calculation",
      status: providerError ? "fallback" : "success",
      provider: forecast.calibrated ? "Calibrated historical analogs" : "Factor fallback",
      fallbackProvider: providerError ? "Stored market data" : undefined,
      ticker,
      requestedAt,
      message: `${classification.rating} ${compositeScore}/100; ${dataCoverage}% coverage; ${forecast.sampleSize} analogs.`,
    });
    return {
      ticker,
      rating: classification.rating,
      score: compositeScore,
      provisional: classification.provisional,
      calibrated: forecast.calibrated,
      coverage: dataCoverage,
      providerError,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await ctx.runMutation(internal.signals.markSignalStale, { ticker });
    await ctx.runMutation(internal.dataSources.recordInternalEvent, {
      service: "Signal Engine",
      operation: "Six-month signal calculation",
      status: "error",
      provider: "signal-v1-6m",
      ticker,
      requestedAt,
      message,
    });
    throw error;
  }
};

export const getTickerBars = internalQuery({
  args: { ticker: v.string() },
  handler: async (ctx, args) =>
    await ctx.db
      .query("dailyPriceBars")
      .withIndex("by_ticker_and_tradingDate", (q) =>
        q.eq("ticker", normalizeTicker(args.ticker))
      )
      .order("asc")
      .take(3000),
});

export const getSignalInputs = internalQuery({
  args: { ticker: v.string() },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const [stock, financialReport, aiReport, previousSignal] = await Promise.all([
      ctx.db.query("stocks").withIndex("by_ticker", (q) => q.eq("ticker", ticker)).unique(),
      ctx.db
        .query("financialReports")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
      ctx.db.query("aiReports").withIndex("by_ticker", (q) => q.eq("ticker", ticker)).unique(),
      ctx.db
        .query("stockSignals")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
    ]);
    return { stock, financialReport, aiReport, previousSignal };
  },
});

export const getAllObservations = internalQuery({
  args: {},
  handler: async (ctx) =>
    await ctx.db
      .query("signalObservations")
      .withIndex("by_modelVersion_and_observationDate", (q) =>
        q.eq("modelVersion", SIGNAL_MODEL_VERSION)
      )
      .order("asc")
      .take(5000),
});

export const getUniverseTickers = internalQuery({
  args: {},
  handler: async (ctx) => {
    const [stocks, portfolio] = await Promise.all([
      ctx.db.query("stocks").take(100),
      ctx.db.query("portfolioStocks").take(100),
    ]);
    return Array.from(
      new Set([...stocks.map((item) => item.ticker), ...portfolio.map((item) => item.ticker)])
    )
      .map(normalizeTicker)
      .filter(Boolean)
      .slice(0, 100);
  },
});

export const upsertBarsBatch = internalMutation({
  args: { bars: v.array(barValidator) },
  handler: async (ctx, args) => {
    let inserted = 0;
    let updated = 0;
    for (const rawBar of args.bars.slice(0, 75)) {
      const bar = { ...rawBar, ticker: normalizeTicker(rawBar.ticker) };
      const existing = await ctx.db
        .query("dailyPriceBars")
        .withIndex("by_ticker_and_tradingDate", (q) =>
          q.eq("ticker", bar.ticker).eq("tradingDate", bar.tradingDate)
        )
        .unique();
      if (existing) {
        if (
          existing.adjustedClose !== bar.adjustedClose ||
          existing.close !== bar.close ||
          existing.source !== bar.source
        ) {
          await ctx.db.patch(existing._id, bar);
          updated += 1;
        }
      } else {
        await ctx.db.insert("dailyPriceBars", bar);
        inserted += 1;
      }
    }
    return { inserted, updated };
  },
});

export const pruneTickerBars = internalMutation({
  args: { ticker: v.string(), keepFromDate: v.string() },
  handler: async (ctx, args) => {
    const rows = await ctx.db
      .query("dailyPriceBars")
      .withIndex("by_ticker_and_tradingDate", (q) =>
        q
          .eq("ticker", normalizeTicker(args.ticker))
          .lt("tradingDate", args.keepFromDate)
      )
      .take(200);
    for (const row of rows) await ctx.db.delete(row._id);
    return { deleted: rows.length };
  },
});

export const replaceTickerObservations = internalMutation({
  args: { ticker: v.string(), observations: v.array(observationValidator) },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("signalObservations")
      .withIndex("by_ticker_and_observationDate", (q) => q.eq("ticker", ticker))
      .take(200);
    for (const item of existing) await ctx.db.delete(item._id);
    for (const observation of args.observations.slice(-150)) {
      await ctx.db.insert("signalObservations", {
        ...observation,
        ticker,
        modelVersion: SIGNAL_MODEL_VERSION,
      });
    }
    return { removed: existing.length, inserted: Math.min(args.observations.length, 150) };
  },
});

export const upsertSignal = internalMutation({
  args: {
    ticker: v.string(),
    rating: v.union(v.literal("BUY"), v.literal("HOLD"), v.literal("SELL")),
    provisional: v.boolean(),
    compositeScore: v.number(),
    horizonDays: v.number(),
    winProbability: v.optional(v.number()),
    lossProbability: v.optional(v.number()),
    outperformProbability: v.optional(v.number()),
    expectedReturn: v.optional(v.number()),
    expectedExcessReturn: v.optional(v.number()),
    downsideP10: v.optional(v.number()),
    factorScores: factorScoresValidator,
    confidence: v.union(v.literal("low"), v.literal("medium"), v.literal("high")),
    sampleSize: v.number(),
    tickerCount: v.number(),
    calibrationSampleSize: v.number(),
    brierScore: v.optional(v.number()),
    dataCoverage: v.number(),
    topPositiveDrivers: v.array(v.string()),
    topNegativeDrivers: v.array(v.string()),
    aiRationale: v.optional(v.string()),
    aiFresh: v.boolean(),
    modelVersion: v.string(),
    dataStatus: v.union(
      v.literal("ready"),
      v.literal("insufficient"),
      v.literal("stale"),
      v.literal("error")
    ),
    source: v.string(),
    historyStart: v.optional(v.string()),
    historyEnd: v.optional(v.string()),
    computedAt: v.number(),
    inputsUpdatedAt: v.number(),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("stockSignals")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();
    const signal = { ...args, ticker };
    if (existing) {
      await ctx.db.patch(existing._id, signal);
      return existing._id;
    }
    return await ctx.db.insert("stockSignals", signal);
  },
});

export const markSignalStale = internalMutation({
  args: { ticker: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("stockSignals")
      .withIndex("by_ticker", (q) => q.eq("ticker", normalizeTicker(args.ticker)))
      .unique();
    if (existing) await ctx.db.patch(existing._id, { dataStatus: "stale" });
    return Boolean(existing);
  },
});

export const refreshTickerInternal = internalAction({
  args: { ticker: v.string() },
  handler: async (ctx, args): Promise<SignalRefreshResult> =>
    await runSignalRefresh(ctx, args.ticker, true),
});

export const recalculateTickerInternal = internalAction({
  args: { ticker: v.string() },
  handler: async (ctx, args): Promise<SignalRefreshResult> =>
    await runSignalRefresh(ctx, args.ticker, false),
});

export const refreshTicker = internalAction({
  args: { ticker: v.string() },
  handler: async (ctx, args): Promise<SignalRefreshResult> =>
    await runSignalRefresh(ctx, args.ticker, true),
});

export const refreshUniverse = internalAction({
  args: {},
  handler: async (ctx) => {
    const tickers = (await ctx.runQuery(
      internal.signals.getUniverseTickers,
      {}
    )) as string[];
    for (const [index, ticker] of tickers.entries()) {
      await ctx.scheduler.runAfter(index * 9_000, internal.signals.refreshTickerInternal, {
        ticker,
      });
    }
    const secondPassStart = tickers.length * 9_000 + 10_000;
    for (const [index, ticker] of tickers.entries()) {
      await ctx.scheduler.runAfter(
        secondPassStart + index * 1_000,
        internal.signals.recalculateTickerInternal,
        { ticker }
      );
    }
    return { scheduled: tickers.length, tickers, secondPassStart };
  },
});

export const recalculateUniverse = internalAction({
  args: {},
  handler: async (ctx) => {
    const tickers = (await ctx.runQuery(
      internal.signals.getUniverseTickers,
      {}
    )) as string[];
    for (const [index, ticker] of tickers.entries()) {
      await ctx.scheduler.runAfter(
        index * 500,
        internal.signals.recalculateTickerInternal,
        { ticker }
      );
    }
    return { scheduled: tickers.length, tickers };
  },
});
