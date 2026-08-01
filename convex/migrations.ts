import { Migrations } from "@convex-dev/migrations";
import { components } from "./_generated/api";
import type { DataModel } from "./_generated/dataModel";

export const migrations = new Migrations<DataModel>(components.migrations);

export const migrateLegacyPortfolioPositions = migrations.define({
  table: "portfolioStocks",
  batchSize: 25,
  migrateOne: async (ctx, legacy) => {
    const hasPositionData =
      (legacy.shares ?? 0) > 0 ||
      legacy.averageCost !== undefined ||
      legacy.targetAllocation !== undefined ||
      Boolean(legacy.positionNotes?.trim());

    if (!hasPositionData) {
      return;
    }

    let mainPortfolio = await ctx.db
      .query("portfolios")
      .withIndex("by_name", (q) => q.eq("name", "Main Portfolio"))
      .unique();

    if (!mainPortfolio) {
      const now = Date.now();
      const portfolioId = await ctx.db.insert("portfolios", {
        name: "Main Portfolio",
        type: "actual",
        description: "Migrated from the original portfolio positions.",
        baseCurrency: "USD",
        benchmarkTicker: "SPY",
        cashBalance: 0,
        status: "active",
        createdAt: now,
        updatedAt: now,
      });
      mainPortfolio = await ctx.db.get("portfolios", portfolioId);
      if (!mainPortfolio) {
        throw new Error("Unable to create Main Portfolio.");
      }
      await ctx.db.insert("portfolioActivities", {
        portfolioId,
        type: "created",
        summary: "Created Main Portfolio from legacy positions.",
        occurredAt: now,
      });
    }

    const existing = await ctx.db
      .query("portfolioHoldings")
      .withIndex("by_portfolioId_and_ticker", (q) =>
        q.eq("portfolioId", mainPortfolio._id).eq("ticker", legacy.ticker)
      )
      .unique();

    if (existing) {
      return;
    }

    await ctx.db.insert("portfolioHoldings", {
      portfolioId: mainPortfolio._id,
      ticker: legacy.ticker,
      shares: Math.max(legacy.shares ?? 0, 0),
      averageCost: Math.max(legacy.averageCost ?? 0, 0),
      targetAllocation: Math.max(legacy.targetAllocation ?? 0, 0),
      notes: legacy.positionNotes?.trim() ?? "",
      createdAt: legacy.savedAt,
      updatedAt: legacy.updatedAt ?? legacy.savedAt,
    });
  },
});

export const run = migrations.runner();
