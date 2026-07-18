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
    generatedAt: v.number(),
  }).index("by_ticker", ["ticker"]),

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
