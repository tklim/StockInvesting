import { v } from "convex/values";
import {
  action,
  internalAction,
  internalMutation,
  internalQuery,
  mutation,
  query,
  type QueryCtx,
} from "./_generated/server";
import { api, internal } from "./_generated/api";
import type { Doc, Id } from "./_generated/dataModel";

declare const process: {
  env: Record<string, string | undefined>;
};

const portfolioTypeValidator = v.union(
  v.literal("actual"),
  v.literal("model")
);

const portfolioStatusValidator = v.union(
  v.literal("active"),
  v.literal("archived")
);

const normalizeTicker = (ticker: string) => ticker.trim().toUpperCase();
const roundedMoney = (value: number) => Math.round(value * 100) / 100;
const safePercent = (value: number) =>
  Math.round(Math.max(value, 0) * 100) / 100;

type HoldingWithStock = Doc<"portfolioHoldings"> & {
  stock: Doc<"stocks"> | null;
  marketValue: number;
  costBasis: number;
  gainLoss: number;
  gainLossPercent: number;
  actualAllocation: number;
  allocationDrift: number;
  priceIsStale: boolean;
};

type ValuationInput = {
  portfolio: Doc<"portfolios">;
  holdings: Array<{
    holding: Doc<"portfolioHoldings">;
    stock: Doc<"stocks"> | null;
  }>;
  benchmarkStock: Doc<"stocks"> | null;
};

type QuoteResult = {
  ticker: string;
  price: number;
  change: number;
  changePercent: number;
  quotedAt: number;
  fresh: boolean;
};

const getPortfolioOrThrow = async (
  ctx: QueryCtx,
  portfolioId: Id<"portfolios">
) => {
  const portfolio = await ctx.db.get("portfolios", portfolioId);
  if (!portfolio) {
    throw new Error("Portfolio was not found.");
  }
  return portfolio;
};

const getHoldingsWithStocks = async (
  ctx: QueryCtx,
  portfolioId: Id<"portfolios">
) => {
  const holdings = await ctx.db
    .query("portfolioHoldings")
    .withIndex("by_portfolioId", (q) => q.eq("portfolioId", portfolioId))
    .take(50);

  return await Promise.all(
    holdings.map(async (holding) => ({
      holding,
      stock: await ctx.db
        .query("stocks")
        .withIndex("by_ticker", (q) => q.eq("ticker", holding.ticker))
        .unique(),
    }))
  );
};

const summarizeHoldings = (
  portfolio: Doc<"portfolios">,
  rows: Array<{
    holding: Doc<"portfolioHoldings">;
    stock: Doc<"stocks"> | null;
  }>
) => {
  const securitiesValue = rows.reduce(
    (sum, row) => sum + row.holding.shares * (row.stock?.price ?? 0),
    0
  );
  const costBasis = rows.reduce(
    (sum, row) => sum + row.holding.shares * row.holding.averageCost,
    0
  );
  const totalValue = securitiesValue + portfolio.cashBalance;
  const totalPnl =
    portfolio.type === "model" && portfolio.startingValue
      ? totalValue - portfolio.startingValue
      : securitiesValue - costBasis;
  const returnBase =
    portfolio.type === "model" && portfolio.startingValue
      ? portfolio.startingValue
      : costBasis;
  const totalReturnPercent =
    returnBase > 0 ? (totalPnl / returnBase) * 100 : 0;
  const totalTargetAllocation = rows.reduce(
    (sum, row) => sum + row.holding.targetAllocation,
    0
  );
  const dayChange = rows.reduce(
    (sum, row) => sum + row.holding.shares * (row.stock?.change ?? 0),
    0
  );
  const dayChangeBase = totalValue - dayChange;
  const dayChangePercent =
    dayChangeBase > 0 ? (dayChange / dayChangeBase) * 100 : 0;

  const holdings: HoldingWithStock[] = rows.map(({ holding, stock }) => {
    const marketValue = holding.shares * (stock?.price ?? 0);
    const holdingCostBasis = holding.shares * holding.averageCost;
    const gainLoss = marketValue - holdingCostBasis;
    const actualAllocation =
      totalValue > 0 ? (marketValue / totalValue) * 100 : 0;

    return {
      ...holding,
      stock,
      marketValue: roundedMoney(marketValue),
      costBasis: roundedMoney(holdingCostBasis),
      gainLoss: roundedMoney(gainLoss),
      gainLossPercent:
        holdingCostBasis > 0 ? (gainLoss / holdingCostBasis) * 100 : 0,
      actualAllocation,
      allocationDrift: actualAllocation - holding.targetAllocation,
      priceIsStale:
        !stock?.updatedAt ||
        Boolean(
          portfolio.lastValuedAt &&
            stock.updatedAt < portfolio.lastValuedAt - 1000
        ),
    };
  });

  return {
    holdings,
    securitiesValue: roundedMoney(securitiesValue),
    costBasis: roundedMoney(costBasis),
    totalValue: roundedMoney(totalValue),
    totalPnl: roundedMoney(totalPnl),
    totalReturnPercent,
    totalTargetAllocation,
    targetCashAllocation: Math.max(100 - totalTargetAllocation, 0),
    dayChange: roundedMoney(dayChange),
    dayChangePercent,
  };
};

export const list = query({
  args: { includeArchived: v.optional(v.boolean()) },
  handler: async (ctx, args) => {
    const active = await ctx.db
      .query("portfolios")
      .withIndex("by_status_and_updatedAt", (q) => q.eq("status", "active"))
      .order("desc")
      .take(100);
    const archived = args.includeArchived
      ? await ctx.db
          .query("portfolios")
          .withIndex("by_status_and_updatedAt", (q) =>
            q.eq("status", "archived")
          )
          .order("desc")
          .take(100)
      : [];

    return await Promise.all(
      [...active, ...archived].map(async (portfolio) => {
        const rows = await getHoldingsWithStocks(ctx, portfolio._id);
        const summary = summarizeHoldings(portfolio, rows);
        const recentSnapshots = await ctx.db
          .query("portfolioSnapshots")
          .withIndex("by_portfolioId_and_capturedAt", (q) =>
            q.eq("portfolioId", portfolio._id)
          )
          .order("desc")
          .take(2);
        const previousValue = recentSnapshots[1]?.totalValue;
        const snapshotChange =
          previousValue && previousValue > 0
            ? ((summary.totalValue - previousValue) / previousValue) * 100
            : summary.dayChangePercent;

        return {
          ...portfolio,
          ...summary,
          holdingCount: rows.length,
          snapshotChangePercent: snapshotChange,
        };
      })
    );
  },
});

export const getDashboard = query({
  args: { portfolioId: v.id("portfolios") },
  handler: async (ctx, args) => {
    const portfolio = await getPortfolioOrThrow(ctx, args.portfolioId);
    const rows = await getHoldingsWithStocks(ctx, args.portfolioId);
    const summary = summarizeHoldings(portfolio, rows);
    const sectors = new Map<string, number>();
    for (const holding of summary.holdings) {
      const sector = holding.stock?.sector || "Unknown";
      sectors.set(sector, (sectors.get(sector) ?? 0) + holding.marketValue);
    }
    const sectorBreakdown = Array.from(sectors.entries())
      .map(([sector, value]) => ({
        sector,
        value: roundedMoney(value),
        allocation:
          summary.totalValue > 0 ? (value / summary.totalValue) * 100 : 0,
      }))
      .sort((left, right) => right.value - left.value);
    const largestHolding =
      summary.holdings
        .slice()
        .sort((left, right) => right.marketValue - left.marketValue)[0] ?? null;
    const largestDrift =
      summary.holdings
        .slice()
        .sort(
          (left, right) =>
            Math.abs(right.allocationDrift) - Math.abs(left.allocationDrift)
        )[0] ?? null;
    const stalePriceCount = summary.holdings.filter(
      (holding) => holding.priceIsStale
    ).length;

    return {
      portfolio,
      ...summary,
      sectorBreakdown,
      health: {
        largestHolding,
        largestDrift,
        stalePriceCount,
        allocationStatus:
          summary.totalTargetAllocation > 100.001
            ? "over"
            : summary.totalTargetAllocation < 99.999
              ? "cash"
              : "balanced",
      },
    };
  },
});

export const history = query({
  args: {
    portfolioId: v.id("portfolios"),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const limit = Math.min(Math.max(Math.floor(args.limit ?? 1300), 1), 1300);
    const rows = await ctx.db
      .query("portfolioSnapshots")
      .withIndex("by_portfolioId_and_capturedAt", (q) =>
        q.eq("portfolioId", args.portfolioId)
      )
      .order("desc")
      .take(limit);
    return rows.reverse();
  },
});

export const activities = query({
  args: {
    portfolioId: v.id("portfolios"),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const limit = Math.min(Math.max(Math.floor(args.limit ?? 20), 1), 50);
    return await ctx.db
      .query("portfolioActivities")
      .withIndex("by_portfolioId_and_occurredAt", (q) =>
        q.eq("portfolioId", args.portfolioId)
      )
      .order("desc")
      .take(limit);
  },
});

export const rebalancePreview = query({
  args: { portfolioId: v.id("portfolios") },
  handler: async (ctx, args) => {
    const portfolio = await getPortfolioOrThrow(ctx, args.portfolioId);
    const rows = await getHoldingsWithStocks(ctx, args.portfolioId);
    const summary = summarizeHoldings(portfolio, rows);
    return {
      portfolioType: portfolio.type,
      totalValue: summary.totalValue,
      targetCashValue: roundedMoney(
        summary.totalValue * (summary.targetCashAllocation / 100)
      ),
      rows: summary.holdings.map((holding) => {
        const targetValue =
          summary.totalValue * (holding.targetAllocation / 100);
        const difference = targetValue - holding.marketValue;
        const price = holding.stock?.price ?? 0;
        return {
          ticker: holding.ticker,
          currentValue: holding.marketValue,
          targetValue: roundedMoney(targetValue),
          difference: roundedMoney(difference),
          estimatedShares: price > 0 ? difference / price : 0,
          price,
        };
      }),
    };
  },
});

export const ensureMainPortfolio = mutation({
  args: {},
  handler: async (ctx) => {
    const existing = await ctx.db
      .query("portfolios")
      .withIndex("by_name", (q) => q.eq("name", "Main Portfolio"))
      .unique();
    if (existing) {
      return existing._id;
    }
    const now = Date.now();
    const portfolioId = await ctx.db.insert("portfolios", {
      name: "Main Portfolio",
      type: "actual",
      description: "Your primary investment portfolio.",
      baseCurrency: "USD",
      benchmarkTicker: "SPY",
      cashBalance: 0,
      status: "active",
      createdAt: now,
      updatedAt: now,
    });
    await ctx.db.insert("portfolioActivities", {
      portfolioId,
      type: "created",
      summary: "Created Main Portfolio.",
      occurredAt: now,
    });
    return portfolioId;
  },
});

export const create = mutation({
  args: {
    name: v.string(),
    type: portfolioTypeValidator,
    description: v.optional(v.string()),
    startingValue: v.optional(v.number()),
    cashBalance: v.optional(v.number()),
    benchmarkTicker: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const name = args.name.trim();
    if (!name) {
      throw new Error("Portfolio name is required.");
    }
    const duplicate = await ctx.db
      .query("portfolios")
      .withIndex("by_name", (q) => q.eq("name", name))
      .unique();
    if (duplicate) {
      throw new Error(`${name} already exists.`);
    }
    const startingValue =
      args.type === "model" ? Math.max(args.startingValue ?? 0, 0) : undefined;
    if (args.type === "model" && !startingValue) {
      throw new Error("Model portfolios require a positive starting value.");
    }
    const now = Date.now();
    const portfolioId = await ctx.db.insert("portfolios", {
      name,
      type: args.type,
      description: args.description?.trim() ?? "",
      baseCurrency: "USD",
      benchmarkTicker: normalizeTicker(args.benchmarkTicker ?? "SPY"),
      startingValue,
      cashBalance:
        args.type === "model"
          ? startingValue ?? 0
          : Math.max(args.cashBalance ?? 0, 0),
      status: "active",
      createdAt: now,
      updatedAt: now,
    });
    await ctx.db.insert("portfolioActivities", {
      portfolioId,
      type: "created",
      summary: `Created ${args.type} portfolio.`,
      occurredAt: now,
    });
    return portfolioId;
  },
});

export const update = mutation({
  args: {
    portfolioId: v.id("portfolios"),
    name: v.optional(v.string()),
    description: v.optional(v.string()),
    benchmarkTicker: v.optional(v.string()),
    cashBalance: v.optional(v.number()),
    status: v.optional(portfolioStatusValidator),
  },
  handler: async (ctx, args) => {
    const portfolio = await ctx.db.get("portfolios", args.portfolioId);
    if (!portfolio) {
      throw new Error("Portfolio was not found.");
    }
    const patch: Partial<Doc<"portfolios">> = { updatedAt: Date.now() };
    if (args.name !== undefined) {
      const name = args.name.trim();
      if (!name) {
        throw new Error("Portfolio name is required.");
      }
      const duplicate = await ctx.db
        .query("portfolios")
        .withIndex("by_name", (q) => q.eq("name", name))
        .unique();
      if (duplicate && duplicate._id !== portfolio._id) {
        throw new Error(`${name} already exists.`);
      }
      patch.name = name;
    }
    if (args.description !== undefined) {
      patch.description = args.description.trim();
    }
    if (args.benchmarkTicker !== undefined) {
      patch.benchmarkTicker = normalizeTicker(args.benchmarkTicker);
    }
    if (args.cashBalance !== undefined) {
      patch.cashBalance = Math.max(args.cashBalance, 0);
    }
    if (args.status !== undefined) {
      patch.status = args.status;
    }
    await ctx.db.patch(args.portfolioId, patch);
    await ctx.db.insert("portfolioActivities", {
      portfolioId: args.portfolioId,
      type: args.status === "archived" ? "archived" : "updated",
      summary:
        args.status === "archived"
          ? "Archived portfolio."
          : "Updated portfolio settings.",
      occurredAt: Date.now(),
    });
    return args.portfolioId;
  },
});

export const duplicate = mutation({
  args: {
    portfolioId: v.id("portfolios"),
    name: v.string(),
  },
  handler: async (ctx, args) => {
    const source = await ctx.db.get("portfolios", args.portfolioId);
    if (!source) {
      throw new Error("Portfolio was not found.");
    }
    const name = args.name.trim();
    if (!name) {
      throw new Error("A name is required for the copy.");
    }
    const duplicateName = await ctx.db
      .query("portfolios")
      .withIndex("by_name", (q) => q.eq("name", name))
      .unique();
    if (duplicateName) {
      throw new Error(`${name} already exists.`);
    }
    const sourceHoldings = await ctx.db
      .query("portfolioHoldings")
      .withIndex("by_portfolioId", (q) => q.eq("portfolioId", source._id))
      .take(50);
    const now = Date.now();
    const portfolioId = await ctx.db.insert("portfolios", {
      name,
      type: source.type,
      description: source.description,
      baseCurrency: source.baseCurrency,
      benchmarkTicker: source.benchmarkTicker,
      startingValue: source.startingValue,
      cashBalance: source.cashBalance,
      status: "active",
      initializedAt: source.initializedAt,
      createdAt: now,
      updatedAt: now,
    });
    for (const holding of sourceHoldings) {
      await ctx.db.insert("portfolioHoldings", {
        portfolioId,
        ticker: holding.ticker,
        shares: holding.shares,
        averageCost: holding.averageCost,
        targetAllocation: holding.targetAllocation,
        notes: holding.notes,
        createdAt: now,
        updatedAt: now,
      });
    }
    await ctx.db.insert("portfolioActivities", {
      portfolioId,
      type: "duplicated",
      summary: `Duplicated from ${source.name}.`,
      occurredAt: now,
    });
    return portfolioId;
  },
});

export const archive = mutation({
  args: { portfolioId: v.id("portfolios") },
  handler: async (ctx, args) => {
    const portfolio = await ctx.db.get("portfolios", args.portfolioId);
    if (!portfolio) {
      throw new Error("Portfolio was not found.");
    }
    const now = Date.now();
    await ctx.db.patch(args.portfolioId, {
      status: "archived",
      updatedAt: now,
    });
    await ctx.db.insert("portfolioActivities", {
      portfolioId: args.portfolioId,
      type: "archived",
      summary: "Archived portfolio.",
      occurredAt: now,
    });
    return true;
  },
});

export const upsertHolding = mutation({
  args: {
    portfolioId: v.id("portfolios"),
    ticker: v.string(),
    shares: v.number(),
    averageCost: v.number(),
    targetAllocation: v.number(),
    notes: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const portfolio = await ctx.db.get("portfolios", args.portfolioId);
    if (!portfolio || portfolio.status !== "active") {
      throw new Error("An active portfolio is required.");
    }
    const ticker = normalizeTicker(args.ticker);
    if (!ticker) {
      throw new Error("Ticker is required.");
    }
    if (args.shares < 0 || args.averageCost < 0 || args.targetAllocation < 0) {
      throw new Error("Shares, cost, and allocation cannot be negative.");
    }
    const targetAllocation = safePercent(args.targetAllocation);
    if (targetAllocation > 100) {
      throw new Error("Target allocation cannot exceed 100%.");
    }
    const holdings = await ctx.db
      .query("portfolioHoldings")
      .withIndex("by_portfolioId", (q) => q.eq("portfolioId", args.portfolioId))
      .take(51);
    const existing = holdings.find((holding) => holding.ticker === ticker);
    if (!existing && holdings.length >= 50) {
      throw new Error("A portfolio supports up to 50 holdings.");
    }
    const otherTargets = holdings.reduce(
      (sum, holding) =>
        sum + (holding._id === existing?._id ? 0 : holding.targetAllocation),
      0
    );
    if (otherTargets + targetAllocation > 100.001) {
      throw new Error(
        `Target allocations would total ${(otherTargets + targetAllocation).toFixed(2)}%.`
      );
    }
    const now = Date.now();
    if (existing) {
      await ctx.db.patch(existing._id, {
        shares: args.shares,
        averageCost: args.averageCost,
        targetAllocation,
        notes: args.notes?.trim() ?? "",
        updatedAt: now,
      });
    } else {
      await ctx.db.insert("portfolioHoldings", {
        portfolioId: args.portfolioId,
        ticker,
        shares: args.shares,
        averageCost: args.averageCost,
        targetAllocation,
        notes: args.notes?.trim() ?? "",
        createdAt: now,
        updatedAt: now,
      });
    }
    await ctx.db.patch(args.portfolioId, { updatedAt: now });
    await ctx.db.insert("portfolioActivities", {
      portfolioId: args.portfolioId,
      type: existing ? "holding_updated" : "holding_added",
      ticker,
      summary: existing ? `Updated ${ticker}.` : `Added ${ticker}.`,
      occurredAt: now,
    });
    return true;
  },
});

export const removeHolding = mutation({
  args: {
    portfolioId: v.id("portfolios"),
    ticker: v.string(),
  },
  handler: async (ctx, args) => {
    const ticker = normalizeTicker(args.ticker);
    const holding = await ctx.db
      .query("portfolioHoldings")
      .withIndex("by_portfolioId_and_ticker", (q) =>
        q.eq("portfolioId", args.portfolioId).eq("ticker", ticker)
      )
      .unique();
    if (!holding) {
      return false;
    }
    await ctx.db.delete(holding._id);
    const now = Date.now();
    await ctx.db.patch(args.portfolioId, { updatedAt: now });
    await ctx.db.insert("portfolioActivities", {
      portfolioId: args.portfolioId,
      type: "holding_removed",
      ticker,
      summary: `Removed ${ticker}.`,
      occurredAt: now,
    });
    return true;
  },
});

export const initializeModel = mutation({
  args: { portfolioId: v.id("portfolios") },
  handler: async (ctx, args) => {
    const portfolio = await ctx.db.get("portfolios", args.portfolioId);
    if (!portfolio || portfolio.type !== "model" || !portfolio.startingValue) {
      throw new Error("A model portfolio with starting value is required.");
    }
    const holdings = await ctx.db
      .query("portfolioHoldings")
      .withIndex("by_portfolioId", (q) => q.eq("portfolioId", args.portfolioId))
      .take(50);
    if (!holdings.length) {
      throw new Error("Add at least one holding before initialization.");
    }
    const totalTarget = holdings.reduce(
      (sum, holding) => sum + holding.targetAllocation,
      0
    );
    if (totalTarget > 100.001) {
      throw new Error("Target allocations exceed 100%.");
    }
    const now = Date.now();
    for (const holding of holdings) {
      const stock = await ctx.db
        .query("stocks")
        .withIndex("by_ticker", (q) => q.eq("ticker", holding.ticker))
        .unique();
      if (!stock || stock.price <= 0) {
        throw new Error(`A current price is required for ${holding.ticker}.`);
      }
      const targetValue =
        portfolio.startingValue * (holding.targetAllocation / 100);
      await ctx.db.patch(holding._id, {
        shares: targetValue / stock.price,
        averageCost: stock.price,
        updatedAt: now,
      });
    }
    await ctx.db.patch(portfolio._id, {
      cashBalance: roundedMoney(
        portfolio.startingValue * ((100 - totalTarget) / 100)
      ),
      initializedAt: now,
      updatedAt: now,
    });
    await ctx.db.insert("portfolioActivities", {
      portfolioId: portfolio._id,
      type: "model_initialized",
      summary: "Initialized model units from target allocations.",
      occurredAt: now,
    });
    return true;
  },
});

export const applyModelRebalance = mutation({
  args: { portfolioId: v.id("portfolios") },
  handler: async (ctx, args) => {
    const portfolio = await ctx.db.get("portfolios", args.portfolioId);
    if (!portfolio || portfolio.type !== "model") {
      throw new Error("Only model portfolios can apply simulated rebalances.");
    }
    const rows = await Promise.all(
      (
        await ctx.db
          .query("portfolioHoldings")
          .withIndex("by_portfolioId", (q) =>
            q.eq("portfolioId", args.portfolioId)
          )
          .take(50)
      ).map(async (holding) => ({
        holding,
        stock: await ctx.db
          .query("stocks")
          .withIndex("by_ticker", (q) => q.eq("ticker", holding.ticker))
          .unique(),
      }))
    );
    const securitiesValue = rows.reduce(
      (sum, row) => sum + row.holding.shares * (row.stock?.price ?? 0),
      0
    );
    const totalValue = securitiesValue + portfolio.cashBalance;
    const totalTarget = rows.reduce(
      (sum, row) => sum + row.holding.targetAllocation,
      0
    );
    const now = Date.now();
    for (const row of rows) {
      const price = row.stock?.price ?? 0;
      if (price <= 0) {
        throw new Error(`A current price is required for ${row.holding.ticker}.`);
      }
      await ctx.db.patch(row.holding._id, {
        shares:
          (totalValue * (row.holding.targetAllocation / 100)) / price,
        averageCost: price,
        updatedAt: now,
      });
    }
    await ctx.db.patch(portfolio._id, {
      cashBalance: roundedMoney(totalValue * ((100 - totalTarget) / 100)),
      updatedAt: now,
    });
    await ctx.db.insert("portfolioActivities", {
      portfolioId: portfolio._id,
      type: "model_rebalanced",
      summary: "Applied simulated rebalance.",
      occurredAt: now,
    });
    return true;
  },
});

export const valuationInputs = internalQuery({
  args: { portfolioId: v.id("portfolios") },
  handler: async (ctx, args): Promise<ValuationInput> => {
    const portfolio = await getPortfolioOrThrow(ctx, args.portfolioId);
    const holdings = await getHoldingsWithStocks(ctx, args.portfolioId);
    const benchmarkStock = await ctx.db
      .query("stocks")
      .withIndex("by_ticker", (q) =>
        q.eq("ticker", portfolio.benchmarkTicker)
      )
      .unique();
    return { portfolio, holdings, benchmarkStock };
  },
});

const fetchQuote = async (
  ticker: string,
  fallback: Doc<"stocks"> | null
): Promise<QuoteResult> => {
  const apiKey = process.env.FINNHUB_API_KEY;
  if (apiKey) {
    try {
      const url = new URL("https://finnhub.io/api/v1/quote");
      url.searchParams.set("symbol", ticker);
      url.searchParams.set("token", apiKey);
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Quote request returned ${response.status}.`);
      }
      const value = (await response.json()) as {
        c?: number;
        d?: number;
        dp?: number;
        t?: number;
      };
      if (value.c && value.c > 0) {
        return {
          ticker,
          price: value.c,
          change: value.d ?? 0,
          changePercent: value.dp ?? 0,
          quotedAt: (value.t ?? Math.floor(Date.now() / 1000)) * 1000,
          fresh: true,
        };
      }
    } catch {
      // Stored prices remain a safe, explicit stale fallback.
    }
  }
  return {
    ticker,
    price: fallback?.price ?? 0,
    change: fallback?.change ?? 0,
    changePercent: fallback?.changePercent ?? 0,
    quotedAt: fallback?.updatedAt ?? Date.now(),
    fresh: false,
  };
};

export const captureSnapshot = internalMutation({
  args: {
    portfolioId: v.id("portfolios"),
    quotes: v.array(
      v.object({
        ticker: v.string(),
        price: v.number(),
        change: v.number(),
        changePercent: v.number(),
        quotedAt: v.number(),
        fresh: v.boolean(),
      })
    ),
  },
  handler: async (ctx, args) => {
    const portfolio = await ctx.db.get("portfolios", args.portfolioId);
    if (!portfolio) {
      throw new Error("Portfolio was not found.");
    }
    const holdings = await ctx.db
      .query("portfolioHoldings")
      .withIndex("by_portfolioId", (q) => q.eq("portfolioId", args.portfolioId))
      .take(50);
    const quoteMap = new Map(args.quotes.map((quote) => [quote.ticker, quote]));
    const portfolioQuotes = holdings.map((holding) => ({
      holding,
      quote: quoteMap.get(holding.ticker),
    }));
    const freshCount = portfolioQuotes.filter((row) => row.quote?.fresh).length;
    const staleTickerCount = portfolioQuotes.length - freshCount;
    const dataStatus: "fresh" | "partial" | "stale" =
      portfolioQuotes.length > 0 && freshCount === portfolioQuotes.length
        ? "fresh"
        : freshCount > 0
          ? "partial"
          : "stale";
    const freshTimes = portfolioQuotes
      .filter((row) => row.quote?.fresh)
      .map((row) => row.quote?.quotedAt ?? 0);
    const marketTime =
      freshTimes.length > 0
        ? Math.max(...freshTimes)
        : portfolio.lastValuedAt ?? Date.now();
    const marketDate = new Date(marketTime).toISOString().slice(0, 10);

    for (const quote of args.quotes) {
      if (!quote.fresh || quote.ticker === portfolio.benchmarkTicker) {
        continue;
      }
      const stock = await ctx.db
        .query("stocks")
        .withIndex("by_ticker", (q) => q.eq("ticker", quote.ticker))
        .unique();
      if (stock) {
        await ctx.db.patch(stock._id, {
          price: quote.price,
          change: quote.change,
          changePercent: quote.changePercent,
          updatedAt: quote.quotedAt,
        });
      }
    }

    const securitiesValue = portfolioQuotes.reduce(
      (sum, row) => sum + row.holding.shares * (row.quote?.price ?? 0),
      0
    );
    const costBasis = portfolioQuotes.reduce(
      (sum, row) => sum + row.holding.shares * row.holding.averageCost,
      0
    );
    const totalValue = securitiesValue + portfolio.cashBalance;
    const totalPnl =
      portfolio.type === "model" && portfolio.startingValue
        ? totalValue - portfolio.startingValue
        : securitiesValue - costBasis;
    const benchmarkQuote = quoteMap.get(portfolio.benchmarkTicker);
    const firstSnapshot = await ctx.db
      .query("portfolioSnapshots")
      .withIndex("by_portfolioId_and_capturedAt", (q) =>
        q.eq("portfolioId", portfolio._id)
      )
      .order("asc")
      .first();
    const benchmarkPrice =
      benchmarkQuote && benchmarkQuote.price > 0
        ? benchmarkQuote.price
        : firstSnapshot?.benchmarkPrice;
    const benchmarkValue =
      benchmarkPrice && firstSnapshot?.benchmarkPrice
        ? firstSnapshot.totalValue *
          (benchmarkPrice / firstSnapshot.benchmarkPrice)
        : benchmarkPrice
          ? totalValue
          : undefined;
    const snapshot = {
      portfolioId: portfolio._id,
      marketDate,
      capturedAt: Date.now(),
      securitiesValue: roundedMoney(securitiesValue),
      cashValue: roundedMoney(portfolio.cashBalance),
      totalValue: roundedMoney(totalValue),
      costBasis: roundedMoney(costBasis),
      totalPnl: roundedMoney(totalPnl),
      benchmarkPrice,
      benchmarkValue:
        benchmarkValue === undefined ? undefined : roundedMoney(benchmarkValue),
      dataStatus,
      staleTickerCount,
    };
    const existing = await ctx.db
      .query("portfolioSnapshots")
      .withIndex("by_portfolioId_and_marketDate", (q) =>
        q.eq("portfolioId", portfolio._id).eq("marketDate", marketDate)
      )
      .unique();
    if (existing) {
      await ctx.db.patch(existing._id, snapshot);
    } else {
      await ctx.db.insert("portfolioSnapshots", snapshot);
    }
    await ctx.db.patch(portfolio._id, {
      lastValuedAt: snapshot.capturedAt,
      lastValuationDate: marketDate,
      lastValuationStatus: dataStatus,
      updatedAt: snapshot.capturedAt,
    });
    await ctx.db.insert("portfolioActivities", {
      portfolioId: portfolio._id,
      type: "refreshed",
      summary:
        dataStatus === "fresh"
          ? `Refreshed ${holdings.length} holdings.`
          : `Refreshed with ${staleTickerCount} stale price${staleTickerCount === 1 ? "" : "s"}.`,
      occurredAt: snapshot.capturedAt,
    });
    return {
      marketDate,
      dataStatus,
      refreshedCount: freshCount,
      staleTickerCount,
      totalValue: snapshot.totalValue,
    };
  },
});

export const refreshValue = action({
  args: { portfolioId: v.id("portfolios") },
  handler: async (ctx, args): Promise<{
    marketDate: string;
    dataStatus: "fresh" | "partial" | "stale";
    refreshedCount: number;
    staleTickerCount: number;
    totalValue: number;
  }> => {
    const input: ValuationInput = await ctx.runQuery(
      internal.portfolios.valuationInputs,
      { portfolioId: args.portfolioId }
    );
    const quoteInputs = [
      ...input.holdings.map((row) => ({
        ticker: row.holding.ticker,
        stock: row.stock,
      })),
      {
        ticker: input.portfolio.benchmarkTicker,
        stock: input.benchmarkStock,
      },
    ];
    const uniqueInputs = Array.from(
      new Map(quoteInputs.map((row) => [row.ticker, row])).values()
    );
    const quotes = await Promise.all(
      uniqueInputs.map((row) => fetchQuote(row.ticker, row.stock))
    );
    return await ctx.runMutation(internal.portfolios.captureSnapshot, {
      portfolioId: args.portfolioId,
      quotes,
    });
  },
});

export const activePortfolioIds = internalQuery({
  args: {},
  handler: async (ctx) => {
    const portfolios = await ctx.db
      .query("portfolios")
      .withIndex("by_status_and_updatedAt", (q) => q.eq("status", "active"))
      .take(100);
    return portfolios.map((portfolio) => portfolio._id);
  },
});

export const refreshAllActive = internalAction({
  args: {},
  handler: async (
    ctx
  ): Promise<
    Array<
      | {
          marketDate: string;
          dataStatus: "fresh" | "partial" | "stale";
          refreshedCount: number;
          staleTickerCount: number;
          totalValue: number;
        }
      | { portfolioId: Id<"portfolios">; error: string }
    >
  > => {
    const portfolioIds: Id<"portfolios">[] = await ctx.runQuery(
      internal.portfolios.activePortfolioIds,
      {}
    );
    const results = [];
    for (const portfolioId of portfolioIds) {
      try {
        const result: {
          marketDate: string;
          dataStatus: "fresh" | "partial" | "stale";
          refreshedCount: number;
          staleTickerCount: number;
          totalValue: number;
        } = await ctx.runAction(api.portfolios.refreshValue, { portfolioId });
        results.push(result);
      } catch (error) {
        results.push({
          portfolioId,
          error:
            error instanceof Error ? error.message : "Portfolio refresh failed.",
        });
      }
    }
    return results;
  },
});

export const migrationStatus = query({
  args: {},
  handler: async (ctx) => {
    const legacy = await ctx.db.query("portfolioStocks").take(100);
    const positioned = legacy.filter(
      (item) =>
        (item.shares ?? 0) > 0 ||
        item.averageCost !== undefined ||
        item.targetAllocation !== undefined ||
        Boolean(item.positionNotes?.trim())
    );
    const mainPortfolio = await ctx.db
      .query("portfolios")
      .withIndex("by_name", (q) => q.eq("name", "Main Portfolio"))
      .unique();
    const migrated = mainPortfolio
      ? await ctx.db
          .query("portfolioHoldings")
          .withIndex("by_portfolioId", (q) =>
            q.eq("portfolioId", mainPortfolio._id)
          )
          .take(100)
      : [];
    return {
      legacyPositionCount: positioned.length,
      migratedHoldingCount: migrated.length,
      complete: positioned.length === migrated.length,
    };
  },
});
