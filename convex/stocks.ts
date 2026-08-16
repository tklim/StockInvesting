import { v } from "convex/values";
import { internalMutation, query } from "./_generated/server";
import { internal } from "./_generated/api";

const normalizeTicker = (ticker: string) => ticker.trim().toUpperCase();

const stockPatchValidator = {
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
};

const financialPeriodValidator = v.object({
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
});

const financialReportValidator = v.object({
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
  quarterly: v.array(financialPeriodValidator),
  annual: v.array(financialPeriodValidator),
  updatedAt: v.number(),
});

const companySnapshotFields = {
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
};

const companySnapshotValidator = v.object(companySnapshotFields);

const snapshotToStock = (
  snapshot: {
    ticker: string;
    companyName: string;
    exchange: string;
    sector: string;
    price: number;
    change: number;
    changePercent: number;
    marketCap: string;
    peRatio: string;
    revenueTtm: string;
    epsTtm: string;
    dividendYield: string;
    summary: string;
    syncedAt: number;
  } | null
) => {
  if (!snapshot) {
    return null;
  }

  return {
    ticker: snapshot.ticker,
    companyName: snapshot.companyName,
    exchange: snapshot.exchange,
    sector: snapshot.sector,
    logoUrl: undefined,
    price: snapshot.price,
    change: snapshot.change,
    changePercent: snapshot.changePercent,
    marketCap: snapshot.marketCap,
    peRatio: snapshot.peRatio,
    revenueTtm: snapshot.revenueTtm,
    epsTtm: snapshot.epsTtm,
    dividendYield: snapshot.dividendYield,
    summary: snapshot.summary,
    chartPoints: undefined,
    updatedAt: snapshot.syncedAt,
  };
};

const snapshotToAiReport = (
  snapshot: {
    aiBriefSummary?: string;
    aiBullPoints?: string[];
    aiBearPoints?: string[];
    thesisPoints?: string[];
    thesisWatchItems?: string[];
    syncedAt: number;
  } | null
) => {
  if (!snapshot?.aiBriefSummary) {
    return null;
  }

  return {
    summary: snapshot.aiBriefSummary,
    bullPoints: snapshot.aiBullPoints ?? [],
    bearPoints: snapshot.aiBearPoints ?? [],
    thesisPoints: snapshot.thesisPoints ?? [],
    watchItems: snapshot.thesisWatchItems ?? [],
    provider: "Snapshot",
    model: "Persisted sync snapshot",
    generatedAt: snapshot.syncedAt,
  };
};

const snapshotToInvestmentThesis = (
  snapshot: {
    thesisSummary?: string;
    thesisPoints?: string[];
    thesisWatchItems?: string[];
    syncedAt: number;
  } | null
) => {
  if (!snapshot?.thesisSummary) {
    return null;
  }

  return {
    summary: snapshot.thesisSummary,
    thesisPoints: snapshot.thesisPoints ?? [],
    watchItems: snapshot.thesisWatchItems ?? [],
    source: "Snapshot",
    updatedAt: snapshot.syncedAt,
  };
};

export const list = query({
  args: {},
  returns: v.any(),
  handler: async (ctx) => {
    return await ctx.db.query("stocks").order("asc").take(100);
  },
});

export const search = query({
  args: { query: v.string() },
  returns: v.any(),
  handler: async (ctx, args) => {
    const searchText = args.query.trim().toLowerCase();
    const stocks = await ctx.db.query("stocks").order("asc").take(100);
    const matches = searchText
      ? stocks.filter((stock) => {
          return (
            stock.ticker.toLowerCase().includes(searchText) ||
            stock.companyName.toLowerCase().includes(searchText) ||
            stock.sector.toLowerCase().includes(searchText)
          );
        })
      : stocks;

    return matches.slice(0, 8).map((stock) => ({
      ticker: stock.ticker,
      companyName: stock.companyName,
      exchange: stock.exchange,
      sector: stock.sector,
      price: stock.price,
      changePercent: stock.changePercent,
    }));
  },
});

export const getByTicker = query({
  args: { ticker: v.string() },
  returns: v.any(),
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    return await ctx.db
      .query("stocks")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();
  },
});

export const getFinancialReportByTicker = query({
  args: { ticker: v.string() },
  returns: v.any(),
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    return await ctx.db
      .query("financialReports")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();
  },
});

export const snapshotHistory = query({
  args: { ticker: v.string() },
  returns: v.any(),
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    return await ctx.db
      .query("companySnapshots")
      .withIndex("by_ticker_and_syncedAt", (q) => q.eq("ticker", ticker))
      .order("desc")
      .take(12);
  },
});

export const watchlists = query({
  args: {},
  returns: v.any(),
  handler: async (ctx) => {
    return await ctx.db.query("watchlists").order("asc").take(100);
  },
});

export const initializeWatchlists = internalMutation({
  args: { listNames: v.array(v.string()) },
  handler: async (ctx, args) => {
    const existing = await ctx.db.query("watchlists").collect();
    const existingNames = new Set(existing.map((item) => item.name));

    for (const rawName of args.listNames) {
      const name = rawName.trim();
      if (!name || existingNames.has(name)) {
        continue;
      }

      await ctx.db.insert("watchlists", {
        name,
        createdAt: Date.now(),
      });
    }

    return true;
  },
});

export const createWatchlist = internalMutation({
  args: { name: v.string() },
  handler: async (ctx, args) => {
    const name = args.name.trim();
    if (!name) {
      throw new Error("List name cannot be empty.");
    }

    const existing = await ctx.db
      .query("watchlists")
      .withIndex("by_name", (q) => q.eq("name", name))
      .unique();
    if (existing) {
      throw new Error(`${name} already exists.`);
    }

    return await ctx.db.insert("watchlists", {
      name,
      createdAt: Date.now(),
    });
  },
});

export const renameWatchlist = internalMutation({
  args: {
    currentName: v.string(),
    nextName: v.string(),
  },
  handler: async (ctx, args) => {
    const currentName = args.currentName.trim();
    const nextName = args.nextName.trim();

    if (!currentName || !nextName) {
      throw new Error("Both the current and new list names are required.");
    }

    const list = await ctx.db
      .query("watchlists")
      .withIndex("by_name", (q) => q.eq("name", currentName))
      .unique();
    if (!list) {
      throw new Error(`${currentName} was not found.`);
    }

    const duplicate = await ctx.db
      .query("watchlists")
      .withIndex("by_name", (q) => q.eq("name", nextName))
      .unique();
    if (duplicate && duplicate._id !== list._id) {
      throw new Error(`${nextName} already exists.`);
    }

    await ctx.db.patch(list._id, { name: nextName });

    const portfolioItems = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_listName", (q) => q.eq("listName", currentName))
      .collect();

    for (const item of portfolioItems) {
      await ctx.db.patch(item._id, { listName: nextName });
    }

    return nextName;
  },
});

export const deleteWatchlist = internalMutation({
  args: {
    name: v.string(),
    fallbackListName: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const name = args.name.trim();
    if (!name) {
      throw new Error("List name is required.");
    }

    const list = await ctx.db
      .query("watchlists")
      .withIndex("by_name", (q) => q.eq("name", name))
      .unique();
    if (!list) {
      throw new Error(`${name} was not found.`);
    }

    const portfolioItems = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_listName", (q) => q.eq("listName", name))
      .collect();

    if (portfolioItems.length > 0) {
      const fallbackListName = args.fallbackListName?.trim();
      if (!fallbackListName || fallbackListName === name) {
        throw new Error("Choose another list to move existing holdings into.");
      }

      const fallbackList = await ctx.db
        .query("watchlists")
        .withIndex("by_name", (q) => q.eq("name", fallbackListName))
        .unique();
      if (!fallbackList) {
        throw new Error(`${fallbackListName} was not found.`);
      }

      for (const item of portfolioItems) {
        await ctx.db.patch(item._id, { listName: fallbackListName });
      }
    }

    await ctx.db.delete(list._id);
    return true;
  },
});

export const saveToPortfolio = internalMutation({
  args: {
    ticker: v.string(),
    listName: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    if (existing) {
      if (args.listName && existing.listName !== args.listName) {
        await ctx.db.patch(existing._id, { listName: args.listName });
      }
      return existing._id;
    }

    return await ctx.db.insert("portfolioStocks", {
      ticker,
      listName: args.listName ?? "Core Watchlist",
      savedAt: Date.now(),
    });
  },
});

export const removeFromPortfolio = internalMutation({
  args: { ticker: v.string() },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    if (!existing) {
      return false;
    }

    await ctx.db.delete(existing._id);
    return true;
  },
});

export const portfolio = query({
  args: {},
  returns: v.any(),
  handler: async (ctx) => {
    const saved = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_savedAt")
      .order("desc")
      .take(100);
    const stocks = await Promise.all(
      saved.map(async (item) => {
        const [stock, stockSignal] = await Promise.all([
          ctx.db
            .query("stocks")
            .withIndex("by_ticker", (q) => q.eq("ticker", item.ticker))
            .unique(),
          ctx.db
            .query("stockSignals")
            .withIndex("by_ticker", (q) => q.eq("ticker", item.ticker))
            .unique(),
        ]);
        return { ...item, stock, stockSignal };
      })
    );

    return stocks;
  },
});

export const adminWatchlistStatus = query({
  args: {},
  returns: v.any(),
  handler: async (ctx) => {
    const saved = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_savedAt")
      .order("desc")
      .take(100);

    return await Promise.all(
      saved.map(async (item) => {
        const ticker = normalizeTicker(item.ticker);
        const [stock, snapshot, financialReport, aiReport, investmentThesis, aiNote, stockSignal] =
          await Promise.all([
            ctx.db
              .query("stocks")
              .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
              .unique(),
            ctx.db
              .query("companySnapshots")
              .withIndex("by_ticker_and_syncedAt", (q) => q.eq("ticker", ticker))
              .order("desc")
              .take(1),
            ctx.db
              .query("financialReports")
              .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
              .unique(),
            ctx.db
              .query("aiReports")
              .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
              .unique(),
            ctx.db
              .query("investmentTheses")
              .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
              .unique(),
            ctx.db
              .query("notes")
              .withIndex("by_ticker_and_generatedBy", (q) =>
                q.eq("ticker", ticker).eq("generatedBy", "admin-ai-workflow")
              )
              .order("desc")
              .take(1),
            ctx.db
              .query("stockSignals")
              .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
              .unique(),
          ]);

        return {
          ticker,
          listName: item.listName,
          companyName: stock?.companyName ?? ticker,
          // Use the persisted snapshot time, not the quote's market timestamp.
          // The latter may be the previous market close and would make a
          // 24-hour refresh guard re-run over a weekend or holiday.
          marketDataAt: snapshot[0]?._creationTime ?? stock?._creationTime ?? stock?.updatedAt ?? null,
          financialsAt: financialReport?.updatedAt ?? null,
          aiReportAt: aiReport?.generatedAt ?? null,
          thesisAt: investmentThesis?.updatedAt ?? null,
          aiNotesAt: aiNote[0]?.createdAt ?? null,
          signalsAt: stockSignal?.computedAt ?? null,
        };
      })
    );
  },
});

export const updatePortfolioList = internalMutation({
  args: {
    ticker: v.string(),
    listName: v.string(),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    if (!existing) {
      return await ctx.db.insert("portfolioStocks", {
        ticker,
        listName: args.listName,
        savedAt: Date.now(),
      });
    }

    await ctx.db.patch(existing._id, { listName: args.listName });
    return existing._id;
  },
});

export const updatePortfolioPosition = internalMutation({
  args: {
    ticker: v.string(),
    shares: v.number(),
    averageCost: v.number(),
    targetAllocation: v.number(),
    positionNotes: v.string(),
    listName: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const shares = Math.max(args.shares, 0);
    const averageCost = Math.max(args.averageCost, 0);
    const targetAllocation = Math.max(args.targetAllocation, 0);
    const existing = await ctx.db
      .query("portfolioStocks")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    const positionPatch = {
      shares,
      averageCost,
      targetAllocation,
      positionNotes: args.positionNotes.trim(),
      updatedAt: Date.now(),
    };

    if (!existing) {
      return await ctx.db.insert("portfolioStocks", {
        ticker,
        listName: args.listName ?? "Core Watchlist",
        savedAt: Date.now(),
        ...positionPatch,
      });
    }

    await ctx.db.patch(existing._id, positionPatch);
    return existing._id;
  },
});

export const researchBundle = query({
  args: { ticker: v.string() },
  returns: v.any(),
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const [
      stock,
      news,
      notes,
      researchItems,
      aiReport,
      investmentThesis,
      financialReport,
      saved,
      snapshots,
      stockSignal,
    ] = await Promise.all([
      ctx.db
        .query("stocks")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
      ctx.db
        .query("news")
        .withIndex("by_ticker_publishedAt", (q) => q.eq("ticker", ticker))
        .order("desc")
        .take(5),
      ctx.db
        .query("notes")
        .withIndex("by_ticker_createdAt", (q) => q.eq("ticker", ticker))
        .order("desc")
        .take(5),
      ctx.db
        .query("researchItems")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .take(20),
      ctx.db
        .query("aiReports")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
      ctx.db
        .query("investmentTheses")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
      ctx.db
        .query("financialReports")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
      ctx.db
        .query("portfolioStocks")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
      ctx.db
        .query("companySnapshots")
        .withIndex("by_ticker_and_syncedAt", (q) => q.eq("ticker", ticker))
        .order("desc")
        .take(12),
      ctx.db
        .query("stockSignals")
        .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
        .unique(),
    ]);
    const latestSnapshot = snapshots[0] ?? null;

    return {
      stock: stock ?? snapshotToStock(latestSnapshot),
      news,
      notes,
      researchItems,
      aiReport: aiReport ?? snapshotToAiReport(latestSnapshot),
      investmentThesis:
        investmentThesis ?? snapshotToInvestmentThesis(latestSnapshot),
      financialReport,
      snapshots,
      stockSignal,
      isSaved: Boolean(saved),
    };
  },
});

export const compareCompanies = query({
  args: { tickers: v.array(v.string()) },
  returns: v.any(),
  handler: async (ctx, args) => {
    const tickers = Array.from(
      new Set(args.tickers.map((ticker) => normalizeTicker(ticker)).filter(Boolean))
    ).slice(0, 4);

    return await Promise.all(
      tickers.map(async (ticker) => {
        const [
          stock,
          aiReport,
          investmentThesis,
          financialReport,
          snapshots,
        ] = await Promise.all([
          ctx.db
            .query("stocks")
            .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
            .unique(),
          ctx.db
            .query("aiReports")
            .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
            .unique(),
          ctx.db
            .query("investmentTheses")
            .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
            .unique(),
          ctx.db
            .query("financialReports")
            .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
            .unique(),
          ctx.db
            .query("companySnapshots")
            .withIndex("by_ticker_and_syncedAt", (q) => q.eq("ticker", ticker))
            .order("desc")
            .take(12),
        ]);

        const latestSnapshot = snapshots[0] ?? null;
        const baselineSnapshot = snapshots[snapshots.length - 1] ?? latestSnapshot;
        const performanceSinceFirstSnapshot =
          latestSnapshot && baselineSnapshot && baselineSnapshot.price > 0
            ? ((latestSnapshot.price - baselineSnapshot.price) / baselineSnapshot.price) *
              100
            : null;

        return {
          ticker,
          stock: stock ?? snapshotToStock(latestSnapshot),
          aiReport: aiReport ?? snapshotToAiReport(latestSnapshot),
          investmentThesis:
            investmentThesis ?? snapshotToInvestmentThesis(latestSnapshot),
          financialReport,
          latestSnapshot,
          performanceSinceFirstSnapshot,
          snapshotCount: snapshots.length,
        };
      })
    );
  },
});

export const upsertMarketData = internalMutation({
  args: {
    stock: v.object(stockPatchValidator),
    news: v.array(
      v.object({
        headline: v.string(),
        source: v.string(),
        url: v.optional(v.string()),
        publishedAt: v.number(),
      })
    ),
    researchItems: v.array(
      v.object({
        kind: v.union(
          v.literal("brief"),
          v.literal("strength"),
          v.literal("thesis"),
          v.literal("risk")
        ),
        title: v.string(),
        body: v.string(),
        status: v.optional(v.union(v.literal("complete"), v.literal("open"))),
      })
    ),
    snapshot: companySnapshotValidator,
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.stock.ticker);
    const existing = await ctx.db
      .query("stocks")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    const stockDoc = {
      ...args.stock,
      ticker,
    };

    if (existing) {
      await ctx.db.patch(existing._id, stockDoc);
    } else {
      await ctx.db.insert("stocks", stockDoc);
    }

    const existingNews = await ctx.db
      .query("news")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .take(100);
    const incomingHeadlines = new Set(args.news.map((item) => item.headline));
    const existingHeadlines = new Set<string>();

    for (const item of existingNews) {
      if (!incomingHeadlines.has(item.headline)) {
        await ctx.db.delete(item._id);
        continue;
      }
      existingHeadlines.add(item.headline);
    }

    for (const item of args.news) {
      if (existingHeadlines.has(item.headline)) {
        continue;
      }

      await ctx.db.insert("news", {
        ticker,
        ...item,
      });
    }

    const existingResearchItems = await ctx.db
      .query("researchItems")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .collect();

    for (const item of existingResearchItems) {
      await ctx.db.delete(item._id);
    }

    for (const item of args.researchItems) {
      await ctx.db.insert("researchItems", {
        ticker,
        ...item,
        createdAt: Date.now(),
      });
    }

    // A market snapshot is a point-in-time record of the sync payload. Do not
    // copy the most recently generated AI report or thesis into it: those may
    // have been created against an older quote and would make the snapshot
    // appear internally inconsistent.
    await ctx.db.insert("companySnapshots", {
      ...args.snapshot,
      ticker,
    });

    const snapshots = await ctx.db
      .query("companySnapshots")
      .withIndex("by_ticker_and_syncedAt", (q) => q.eq("ticker", ticker))
      .order("desc")
      .take(60);
    for (const snapshot of snapshots.slice(30)) {
      await ctx.db.delete(snapshot._id);
    }

    return ticker;
  },
});

export const upsertFinancialReport = internalMutation({
  args: {
    ticker: v.string(),
    financialReport: financialReportValidator,
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("financialReports")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();
    const scoreReport = (report: {
      source: string;
      quarterly: Array<Record<string, unknown>>;
      annual: Array<Record<string, unknown>>;
      qualityScore?: number;
    }) => {
      if (report.qualityScore !== undefined) {
        return report.qualityScore;
      }
      const rows = [...report.quarterly, ...report.annual];
      const populatedValues = rows.reduce(
        (total, row) =>
          total +
          Object.entries(row).filter(
            ([key, value]) =>
              key !== "fiscalDateEnding" &&
              typeof value === "string" &&
              value !== "N/A" &&
              value !== "None"
          ).length,
        0
      );
      const sourceBonus = report.source.includes("SEC")
        ? 20
        : report.source.includes("Financial Modeling Prep")
          ? 10
          : 5;
      return sourceBonus + rows.length * 2 + populatedValues;
    };
    const qualityScore = scoreReport(args.financialReport);
    const financialReportDoc = {
      ticker,
      ...args.financialReport,
      qualityScore,
    };

    if (existing) {
      const previousQualityScore = scoreReport(existing);
      const existingIsRecent = Date.now() - existing.updatedAt < 30 * 24 * 60 * 60 * 1000;
      if (existingIsRecent && qualityScore + 10 < previousQualityScore) {
        if (args.financialReport.source.includes("SEC")) {
          const parseValue = (value?: string) => {
            if (!value || value === "N/A" || value === "None") return undefined;
            const normalized = value.replace(/[$,%]/g, "");
            const multiplier = normalized.endsWith("T")
              ? 1e12
              : normalized.endsWith("B")
                ? 1e9
                : normalized.endsWith("M")
                  ? 1e6
                  : 1;
            const parsed = Number(normalized.replace(/[TBM]$/, ""));
            return Number.isFinite(parsed) ? parsed * multiplier : undefined;
          };
          const comparisonFields = [
            "totalRevenue",
            "netIncome",
            "totalAssets",
            "totalShareholderEquity",
          ] as const;
          let comparable = 0;
          let mismatches = 0;
          for (const [secRows, existingRows] of [
            [args.financialReport.quarterly, existing.quarterly],
            [args.financialReport.annual, existing.annual],
          ] as const) {
            for (const secRow of secRows) {
              const existingRow = existingRows.find(
                (row) => row.fiscalDateEnding === secRow.fiscalDateEnding
              );
              if (!existingRow) continue;
              for (const field of comparisonFields) {
                const secValue = parseValue(secRow[field]);
                const existingValue = parseValue(existingRow[field]);
                if (secValue === undefined || existingValue === undefined) continue;
                comparable += 1;
                const scale = Math.max(Math.abs(secValue), Math.abs(existingValue), 1);
                if (Math.abs(secValue - existingValue) / scale > 0.015) {
                  mismatches += 1;
                }
              }
            }
          }
          const verified = comparable >= 3 && mismatches === 0;
          const verifiedSource = Array.from(
            new Set(
              [...existing.source.split(" + "), "SEC EDGAR"].filter(Boolean)
            )
          ).join(" + ");
          const addedQuarterlyRows = args.financialReport.quarterly.filter(
            (candidate) =>
              !existing.quarterly.some(
                (row) => row.fiscalDateEnding === candidate.fiscalDateEnding
              )
          );
          const mergedQuarterly = [...existing.quarterly, ...addedQuarterlyRows]
            .sort((left, right) =>
              right.fiscalDateEnding.localeCompare(left.fiscalDateEnding)
            )
            .slice(0, 8);
          await ctx.db.patch(existing._id, {
            source: verified
              ? verifiedSource
              : existing.source,
            sourceUrl: args.financialReport.sourceUrl,
            filedAt: args.financialReport.filedAt,
            accessionNumber: args.financialReport.accessionNumber,
            validationStatus: verified ? "verified" : "partial",
            warnings: verified
              ? args.financialReport.warnings
              : [
                  ...(args.financialReport.warnings ?? []),
                  `SEC comparison found ${mismatches} mismatch${mismatches === 1 ? "" : "es"} across ${comparable} comparable core facts.`,
                ],
            quarterly: verified ? mergedQuarterly : existing.quarterly,
            qualityScore: previousQualityScore,
          });
          return {
            id: existing._id,
            saved: verified,
            qualityScore,
            previousQualityScore,
          };
        }
        return {
          id: existing._id,
          saved: false,
          qualityScore,
          previousQualityScore,
        };
      }
      await ctx.db.patch(existing._id, financialReportDoc);
      return {
        id: existing._id,
        saved: true,
        qualityScore,
        previousQualityScore,
      };
    }

    const id = await ctx.db.insert("financialReports", financialReportDoc);
    return { id, saved: true, qualityScore, previousQualityScore: null };
  },
});

export const upsertAiReport = internalMutation({
  args: {
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
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("aiReports")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    const reportDoc = {
      ...args,
      ticker,
    };

    let id;
    if (existing) {
      await ctx.db.patch(existing._id, reportDoc);
      id = existing._id;
    } else {
      id = await ctx.db.insert("aiReports", reportDoc);
    }
    await ctx.scheduler.runAfter(0, internal.signals.recalculateTickerInternal, {
      ticker,
    });
    return id;
  },
});

export const saveAiReport = internalMutation({
  args: {
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
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("aiReports")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    const reportDoc = {
      ...args,
      ticker,
    };

    let id;
    if (existing) {
      await ctx.db.patch(existing._id, reportDoc);
      id = existing._id;
    } else {
      id = await ctx.db.insert("aiReports", reportDoc);
    }
    await ctx.scheduler.runAfter(0, internal.signals.recalculateTickerInternal, {
      ticker,
    });
    return id;
  },
});

export const saveInvestmentThesis = internalMutation({
  args: {
    ticker: v.string(),
    summary: v.string(),
    thesisPoints: v.array(v.string()),
    watchItems: v.array(v.string()),
    source: v.string(),
    updatedAt: v.number(),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const existing = await ctx.db
      .query("investmentTheses")
      .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
      .unique();

    const thesisDoc = {
      ...args,
      ticker,
    };

    if (existing) {
      await ctx.db.patch(existing._id, thesisDoc);
      return existing._id;
    }

    return await ctx.db.insert("investmentTheses", thesisDoc);
  },
});

export const createNote = internalMutation({
  args: {
    ticker: v.string(),
    title: v.string(),
    body: v.string(),
    tag: v.string(),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const title = args.title.trim();
    const body = args.body.trim();
    const tag = args.tag.trim() || "General";

    if (!title || !body) {
      throw new Error("Note title and body are required.");
    }

    return await ctx.db.insert("notes", {
      ticker,
      title,
      body,
      tag,
      createdAt: Date.now(),
    });
  },
});

export const replaceAdminGeneratedNotes = internalMutation({
  args: {
    ticker: v.string(),
    notes: v.array(
      v.object({
        title: v.string(),
        body: v.string(),
        tag: v.string(),
      }),
    ),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    if (args.notes.length !== 5) {
      throw new Error("The admin AI workflow must replace exactly five notes.");
    }

    const existing = await ctx.db
      .query("notes")
      .withIndex("by_ticker_and_generatedBy", (q) =>
        q.eq("ticker", ticker).eq("generatedBy", "admin-ai-workflow"),
      )
      .take(6);
    if (existing.length > 5) {
      throw new Error(
        "Too many admin AI workflow notes exist for this ticker; refusing an unbounded replacement.",
      );
    }

    const normalizedNotes = args.notes.map((note) => ({
      title: note.title.trim().slice(0, 120),
      body: note.body.trim().slice(0, 520),
      tag: note.tag.trim().slice(0, 40) || "AI Note",
    }));
    if (normalizedNotes.some((note) => !note.title || !note.body)) {
      throw new Error("Each admin AI workflow note needs a title and body.");
    }

    const titles = new Set<string>();
    for (const note of normalizedNotes) {
      const normalizedTitle = note.title.toLocaleLowerCase();
      if (titles.has(normalizedTitle)) {
        throw new Error("Admin AI workflow notes must have unique titles.");
      }
      titles.add(normalizedTitle);
    }

    for (const note of existing) {
      await ctx.db.delete(note._id);
    }

    const createdAt = Date.now();
    for (const note of normalizedNotes) {
      await ctx.db.insert("notes", {
        ticker,
        ...note,
        generatedBy: "admin-ai-workflow",
        createdAt,
      });
    }

    return { replacedCount: existing.length, createdCount: normalizedNotes.length };
  },
});

export const deleteNote = internalMutation({
  args: {
    noteId: v.id("notes"),
  },
  handler: async (ctx, args) => {
    const note = await ctx.db.get(args.noteId);
    if (!note) {
      throw new Error("Note not found.");
    }

    await ctx.db.delete(args.noteId);
    return { deleted: true };
  },
});

export const generateAiNotes = internalMutation({
  args: {
    ticker: v.string(),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const [stock, news, aiReport, financialReport, existingNotes] =
      await Promise.all([
        ctx.db
          .query("stocks")
          .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
          .unique(),
        ctx.db
          .query("news")
          .withIndex("by_ticker_publishedAt", (q) => q.eq("ticker", ticker))
          .order("desc")
          .take(5),
        ctx.db
          .query("aiReports")
          .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
          .unique(),
        ctx.db
          .query("financialReports")
          .withIndex("by_ticker", (q) => q.eq("ticker", ticker))
          .unique(),
        ctx.db
          .query("notes")
          .withIndex("by_ticker_createdAt", (q) => q.eq("ticker", ticker))
          .order("desc")
          .take(50),
      ]);

    const companyName = stock?.companyName ?? ticker;
    const latestAnnual = financialReport?.annual[0];
    const latestQuarter = financialReport?.quarterly[0];
    const candidates: Array<{ title: string; body: string; tag: string }> = [];

    if (aiReport?.summary) {
      candidates.push({
        title: "AI report summary",
        body: aiReport.summary,
        tag: "AI Note",
      });
    }

    for (const point of aiReport?.bullPoints.slice(0, 2) ?? []) {
      candidates.push({
        title: point,
        body: `Upside angle from the latest AI report for ${companyName}. Validate it against news, filings, and financial trend data.`,
        tag: "AI Note",
      });
    }

    for (const point of aiReport?.bearPoints.slice(0, 1) ?? []) {
      candidates.push({
        title: point,
        body: `Downside factor from the latest AI report for ${companyName}. Track whether new headlines or filings confirm this risk.`,
        tag: "Risk",
      });
    }

    if (news[0]) {
      candidates.push({
        title: `Latest headline: ${news[0].headline}`,
        body: `${news[0].source} published this on ${new Date(
          news[0].publishedAt
        ).toLocaleDateString("en-US")}. Check whether it strengthens or weakens the current thesis.`,
        tag: "News",
      });
    }

    if (financialReport) {
      const revenue = latestQuarter?.totalRevenue ?? latestAnnual?.totalRevenue ?? "N/A";
      const netIncome = latestQuarter?.netIncome ?? latestAnnual?.netIncome ?? "N/A";
      candidates.push({
        title: "Financial trend checkpoint",
        body: `Latest period ${financialReport.latestQuarter || latestQuarter?.fiscalDateEnding || latestAnnual?.fiscalDateEnding || "N/A"}: revenue ${revenue}, net income ${netIncome}, profit margin ${financialReport.profitMargin}, operating margin ${financialReport.operatingMarginTtm}, price/book ${financialReport.priceToBookRatio}.`,
        tag: "Financials",
      });
      candidates.push({
        title: "Check next earnings call margin guidance",
        body: `Follow up on whether management guidance supports the current operating margin (${financialReport.operatingMarginTtm}) and revenue trajectory.`,
        tag: "Follow-up",
      });
    }

    for (const item of aiReport?.watchItems.slice(0, 2) ?? []) {
      candidates.push({
        title: `Follow up: ${item}`,
        body: `Reminder for ${companyName}: revisit this watch item after the next earnings call, filing, or major news update.`,
        tag: "Follow-up",
      });
    }

    if (!candidates.length) {
      candidates.push({
        title: "Build the first research checkpoint",
        body: `Sync live data, generate an AI report, and refresh financials for ${companyName}; then rerun AI notes to create a stronger research trail.`,
        tag: "Follow-up",
      });
    }

    const existingTitles = new Set(
      existingNotes.map((note) => note.title.trim().toLowerCase())
    );
    let insertedCount = 0;

    for (const candidate of candidates.slice(0, 6)) {
      const title = candidate.title.trim();
      const body = candidate.body.trim();
      if (!title || !body || existingTitles.has(title.toLowerCase())) {
        continue;
      }

      await ctx.db.insert("notes", {
        ticker,
        title,
        body,
        tag: candidate.tag,
        createdAt: Date.now(),
      });
      existingTitles.add(title.toLowerCase());
      insertedCount += 1;
    }

    return { insertedCount };
  },
});
