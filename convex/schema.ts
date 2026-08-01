import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";
import { authTables } from "@convex-dev/auth/server";

export default defineSchema({
  ...authTables,
  stocks: defineTable({
    ticker: v.string(),
    companyName: v.string(),
    exchange: v.string(),
    sector: v.string(),
    logoUrl: v.optional(v.string()),
    price: v.number(),
    change: v.number(),
    changePercent: v.number(),
    marketCap: v.string(),
    peRatio: v.string(),
    revenueTtm: v.string(),
    epsTtm: v.string(),
    dividendYield: v.string(),
    summary: v.string(),
    chartPoints: v.optional(v.array(v.number())),
    updatedAt: v.number(),
  }).index("by_ticker", ["ticker"]),

  portfolioStocks: defineTable({
    ticker: v.string(),
    listName: v.string(),
    // Deprecated portfolio-position fields. They remain optional during the
    // multi-portfolio migration so watchlist data can be rolled back safely.
    shares: v.optional(v.number()),
    averageCost: v.optional(v.number()),
    targetAllocation: v.optional(v.number()),
    positionNotes: v.optional(v.string()),
    savedAt: v.number(),
    updatedAt: v.optional(v.number()),
  })
    .index("by_ticker", ["ticker"])
    .index("by_listName", ["listName"])
    .index("by_savedAt", ["savedAt"]),

  portfolios: defineTable({
    name: v.string(),
    type: v.union(v.literal("actual"), v.literal("model")),
    description: v.string(),
    baseCurrency: v.string(),
    benchmarkTicker: v.string(),
    startingValue: v.optional(v.number()),
    cashBalance: v.number(),
    status: v.union(v.literal("active"), v.literal("archived")),
    initializedAt: v.optional(v.number()),
    lastValuedAt: v.optional(v.number()),
    lastValuationDate: v.optional(v.string()),
    lastValuationStatus: v.optional(
      v.union(v.literal("fresh"), v.literal("partial"), v.literal("stale"))
    ),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_name", ["name"])
    .index("by_status_and_updatedAt", ["status", "updatedAt"]),

  portfolioHoldings: defineTable({
    portfolioId: v.id("portfolios"),
    ticker: v.string(),
    shares: v.number(),
    averageCost: v.number(),
    targetAllocation: v.number(),
    notes: v.string(),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_portfolioId", ["portfolioId"])
    .index("by_portfolioId_and_ticker", ["portfolioId", "ticker"]),

  portfolioSnapshots: defineTable({
    portfolioId: v.id("portfolios"),
    marketDate: v.string(),
    capturedAt: v.number(),
    securitiesValue: v.number(),
    cashValue: v.number(),
    totalValue: v.number(),
    costBasis: v.number(),
    totalPnl: v.number(),
    benchmarkPrice: v.optional(v.number()),
    benchmarkValue: v.optional(v.number()),
    dataStatus: v.union(
      v.literal("fresh"),
      v.literal("partial"),
      v.literal("stale")
    ),
    staleTickerCount: v.number(),
  })
    .index("by_portfolioId_and_marketDate", ["portfolioId", "marketDate"])
    .index("by_portfolioId_and_capturedAt", ["portfolioId", "capturedAt"]),

  portfolioActivities: defineTable({
    portfolioId: v.id("portfolios"),
    type: v.union(
      v.literal("created"),
      v.literal("updated"),
      v.literal("holding_added"),
      v.literal("holding_updated"),
      v.literal("holding_removed"),
      v.literal("refreshed"),
      v.literal("model_initialized"),
      v.literal("model_rebalanced"),
      v.literal("duplicated"),
      v.literal("archived")
    ),
    ticker: v.optional(v.string()),
    summary: v.string(),
    occurredAt: v.number(),
  }).index("by_portfolioId_and_occurredAt", ["portfolioId", "occurredAt"]),

  watchlists: defineTable({
    name: v.string(),
    createdAt: v.number(),
  }).index("by_name", ["name"]),

  news: defineTable({
    ticker: v.string(),
    headline: v.string(),
    source: v.string(),
    url: v.optional(v.string()),
    publishedAt: v.number(),
  })
    .index("by_ticker", ["ticker"])
    .index("by_ticker_publishedAt", ["ticker", "publishedAt"]),

  notes: defineTable({
    ticker: v.string(),
    title: v.string(),
    body: v.string(),
    tag: v.string(),
    createdAt: v.number(),
  })
    .index("by_ticker", ["ticker"])
    .index("by_ticker_createdAt", ["ticker", "createdAt"]),

  researchItems: defineTable({
    ticker: v.string(),
    kind: v.union(
      v.literal("brief"),
      v.literal("strength"),
      v.literal("thesis"),
      v.literal("risk")
    ),
    title: v.string(),
    body: v.string(),
    status: v.optional(v.union(v.literal("complete"), v.literal("open"))),
    createdAt: v.number(),
  })
    .index("by_ticker", ["ticker"])
    .index("by_ticker_kind", ["ticker", "kind"]),

  aiReports: defineTable({
    ticker: v.string(),
    summary: v.string(),
    bullPoints: v.array(v.string()),
    bearPoints: v.array(v.string()),
    thesisPoints: v.array(v.string()),
    watchItems: v.array(v.string()),
    provider: v.string(),
    model: v.string(),
    signalScore: v.optional(v.number()),
    signalRationale: v.optional(v.string()),
    generatedAt: v.number(),
  }).index("by_ticker", ["ticker"]),

  dailyPriceBars: defineTable({
    ticker: v.string(),
    tradingDate: v.string(),
    close: v.number(),
    adjustedClose: v.number(),
    volume: v.optional(v.number()),
    source: v.string(),
    fetchedAt: v.number(),
  })
    .index("by_ticker_and_tradingDate", ["ticker", "tradingDate"])
    .index("by_fetchedAt", ["fetchedAt"]),

  signalObservations: defineTable({
    modelVersion: v.string(),
    ticker: v.string(),
    observationDate: v.string(),
    features: v.object({
      return1m: v.number(),
      return3m: v.number(),
      return6m: v.number(),
      return12m: v.number(),
      relativeReturn6m: v.number(),
      sma200Distance: v.number(),
      volatility63d: v.number(),
      maxDrawdown126d: v.number(),
    }),
    forwardReturn: v.number(),
    forwardExcessReturn: v.number(),
    win: v.boolean(),
    outperform: v.boolean(),
  })
    .index("by_modelVersion_and_observationDate", [
      "modelVersion",
      "observationDate",
    ])
    .index("by_ticker_and_observationDate", ["ticker", "observationDate"]),

  stockSignals: defineTable({
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
    factorScores: v.object({
      market: v.number(),
      growth: v.number(),
      profitability: v.number(),
      balanceSheet: v.number(),
      valuation: v.number(),
      ai: v.number(),
    }),
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
  })
    .index("by_ticker", ["ticker"])
    .index("by_computedAt", ["computedAt"]),

  investmentTheses: defineTable({
    ticker: v.string(),
    summary: v.string(),
    thesisPoints: v.array(v.string()),
    watchItems: v.array(v.string()),
    source: v.string(),
    updatedAt: v.number(),
  }).index("by_ticker", ["ticker"]),

  financialReports: defineTable({
    ticker: v.string(),
    source: v.string(),
    numericVersion: v.optional(v.number()),
    sourceUrl: v.optional(v.string()),
    filedAt: v.optional(v.string()),
    accessionNumber: v.optional(v.string()),
    validationStatus: v.optional(
      v.union(v.literal("verified"), v.literal("partial"), v.literal("fallback"))
    ),
    warnings: v.optional(v.array(v.string())),
    qualityScore: v.optional(v.number()),
    currency: v.string(),
    fiscalYearEnd: v.string(),
    latestQuarter: v.string(),
    profitMargin: v.string(),
    operatingMarginTtm: v.string(),
    returnOnEquityTtm: v.string(),
    priceToBookRatio: v.string(),
    evToRevenue: v.string(),
    evToEbitda: v.string(),
    beta: v.string(),
    analystTargetPrice: v.string(),
    quarterly: v.array(
      v.object({
        fiscalDateEnding: v.string(),
        derived: v.optional(v.boolean()),
        derivation: v.optional(v.string()),
        currency: v.optional(v.string()),
        normalized: v.optional(
          v.object({
            totalRevenue: v.optional(v.number()),
            grossProfit: v.optional(v.number()),
            operatingIncome: v.optional(v.number()),
            netIncome: v.optional(v.number()),
            dilutedEps: v.optional(v.number()),
            operatingCashflow: v.optional(v.number()),
            capitalExpenditures: v.optional(v.number()),
            freeCashFlow: v.optional(v.number()),
            totalAssets: v.optional(v.number()),
            totalLiabilities: v.optional(v.number()),
            totalShareholderEquity: v.optional(v.number()),
          })
        ),
        filedAt: v.optional(v.string()),
        accessionNumber: v.optional(v.string()),
        sourceUrl: v.optional(v.string()),
        totalRevenue: v.string(),
        grossProfit: v.string(),
        operatingIncome: v.string(),
        netIncome: v.string(),
        dilutedEps: v.string(),
        operatingCashflow: v.string(),
        capitalExpenditures: v.string(),
        freeCashFlow: v.string(),
        totalAssets: v.string(),
        totalLiabilities: v.string(),
        totalShareholderEquity: v.string(),
      })
    ),
    annual: v.array(
      v.object({
        fiscalDateEnding: v.string(),
        derived: v.optional(v.boolean()),
        derivation: v.optional(v.string()),
        currency: v.optional(v.string()),
        normalized: v.optional(
          v.object({
            totalRevenue: v.optional(v.number()),
            grossProfit: v.optional(v.number()),
            operatingIncome: v.optional(v.number()),
            netIncome: v.optional(v.number()),
            dilutedEps: v.optional(v.number()),
            operatingCashflow: v.optional(v.number()),
            capitalExpenditures: v.optional(v.number()),
            freeCashFlow: v.optional(v.number()),
            totalAssets: v.optional(v.number()),
            totalLiabilities: v.optional(v.number()),
            totalShareholderEquity: v.optional(v.number()),
          })
        ),
        filedAt: v.optional(v.string()),
        accessionNumber: v.optional(v.string()),
        sourceUrl: v.optional(v.string()),
        totalRevenue: v.string(),
        grossProfit: v.string(),
        operatingIncome: v.string(),
        netIncome: v.string(),
        dilutedEps: v.string(),
        operatingCashflow: v.string(),
        capitalExpenditures: v.string(),
        freeCashFlow: v.string(),
        totalAssets: v.string(),
        totalLiabilities: v.string(),
        totalShareholderEquity: v.string(),
      })
    ),
    updatedAt: v.number(),
  }).index("by_ticker", ["ticker"]),

  companySnapshots: defineTable({
    ticker: v.string(),
    companyName: v.string(),
    exchange: v.string(),
    sector: v.string(),
    price: v.number(),
    change: v.number(),
    changePercent: v.number(),
    marketCap: v.string(),
    peRatio: v.string(),
    revenueTtm: v.string(),
    epsTtm: v.string(),
    dividendYield: v.string(),
    summary: v.string(),
    aiBriefSummary: v.optional(v.string()),
    aiBullPoints: v.optional(v.array(v.string())),
    aiBearPoints: v.optional(v.array(v.string())),
    thesisSummary: v.optional(v.string()),
    thesisPoints: v.optional(v.array(v.string())),
    thesisWatchItems: v.optional(v.array(v.string())),
    syncedAt: v.number(),
  })
    .index("by_ticker", ["ticker"])
    .index("by_ticker_and_syncedAt", ["ticker", "syncedAt"]),

  dataSourceEvents: defineTable({
    service: v.string(),
    operation: v.string(),
    status: v.union(v.literal("success"), v.literal("error"), v.literal("fallback")),
    provider: v.string(),
    fallbackProvider: v.optional(v.string()),
    ticker: v.optional(v.string()),
    message: v.optional(v.string()),
    requestUrl: v.optional(v.string()),
    requestedAt: v.optional(v.number()),
    dateKey: v.string(),
    calledAt: v.number(),
  })
    .index("by_dateKey", ["dateKey"])
    .index("by_service_and_dateKey", ["service", "dateKey"])
    .index("by_calledAt", ["calledAt"]),

  dailyApiUsage: defineTable({
    service: v.string(),
    dateKey: v.string(),
    count: v.number(),
    successCount: v.number(),
    errorCount: v.number(),
    fallbackCount: v.number(),
    lastStatus: v.union(v.literal("success"), v.literal("error"), v.literal("fallback")),
    lastProvider: v.string(),
    lastFallbackProvider: v.optional(v.string()),
    lastMessage: v.optional(v.string()),
    lastRequestUrl: v.optional(v.string()),
    lastRequestedAt: v.optional(v.number()),
    lastCalledAt: v.number(),
  })
    .index("by_dateKey", ["dateKey"])
    .index("by_service_and_dateKey", ["service", "dateKey"]),
});
