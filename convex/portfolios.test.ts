/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api, internal } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

const insertStock = async (
  t: ReturnType<typeof convexTest>,
  ticker: string,
  price: number,
  sector = "Technology"
) =>
  await t.run(async (ctx) => {
    await ctx.db.insert("stocks", {
      ticker,
      companyName: `${ticker} Company`,
      exchange: "NASDAQ",
      sector,
      price,
      change: 1,
      changePercent: 1,
      marketCap: "$1B",
      peRatio: "20",
      revenueTtm: "$100M",
      epsTtm: "1",
      dividendYield: "0%",
      summary: "Test company",
      updatedAt: Date.now(),
    });
  });

test("the same ticker can belong to portfolios with independent allocations", async () => {
  const t = convexTest(schema, modules);
  await insertStock(t, "AAA", 100);
  const first = await t.mutation(internal.portfolios.create, {
    name: "Growth",
    type: "actual",
  });
  const second = await t.mutation(internal.portfolios.create, {
    name: "Income",
    type: "actual",
  });

  await t.mutation(internal.portfolios.upsertHolding, {
    portfolioId: first,
    ticker: "aaa",
    shares: 10,
    averageCost: 80,
    targetAllocation: 60,
  });
  await t.mutation(internal.portfolios.upsertHolding, {
    portfolioId: second,
    ticker: "AAA",
    shares: 2,
    averageCost: 95,
    targetAllocation: 25,
  });

  const growth = await t.query(api.portfolios.getDashboard, {
    portfolioId: first,
  });
  const income = await t.query(api.portfolios.getDashboard, {
    portfolioId: second,
  });
  expect(growth.holdings).toHaveLength(1);
  expect(income.holdings).toHaveLength(1);
  expect(growth.holdings[0].targetAllocation).toBe(60);
  expect(income.holdings[0].targetAllocation).toBe(25);
  expect(growth.totalValue).toBe(1000);
  expect(income.totalValue).toBe(200);
});

test("target allocations above 100 percent are rejected", async () => {
  const t = convexTest(schema, modules);
  const portfolioId = await t.mutation(internal.portfolios.create, {
    name: "Allocation Guard",
    type: "actual",
  });
  await t.mutation(internal.portfolios.upsertHolding, {
    portfolioId,
    ticker: "AAA",
    shares: 1,
    averageCost: 10,
    targetAllocation: 70,
  });

  await expect(
    t.mutation(internal.portfolios.upsertHolding, {
      portfolioId,
      ticker: "BBB",
      shares: 1,
      averageCost: 10,
      targetAllocation: 31,
    })
  ).rejects.toThrow("101.00%");
});

test("model initialization converts targets into fractional units and cash", async () => {
  const t = convexTest(schema, modules);
  await insertStock(t, "AAA", 100);
  await insertStock(t, "BBB", 50);
  const portfolioId = await t.mutation(internal.portfolios.create, {
    name: "Model",
    type: "model",
    startingValue: 10000,
  });
  await t.mutation(internal.portfolios.upsertHolding, {
    portfolioId,
    ticker: "AAA",
    shares: 0,
    averageCost: 0,
    targetAllocation: 60,
  });
  await t.mutation(internal.portfolios.upsertHolding, {
    portfolioId,
    ticker: "BBB",
    shares: 0,
    averageCost: 0,
    targetAllocation: 30,
  });

  await t.mutation(internal.portfolios.initializeModel, { portfolioId });
  const dashboard = await t.query(api.portfolios.getDashboard, {
    portfolioId,
  });
  expect(dashboard.portfolio.cashBalance).toBe(1000);
  expect(dashboard.totalValue).toBe(10000);
  expect(dashboard.holdings.find((item) => item.ticker === "AAA")?.shares).toBe(
    60
  );
  expect(dashboard.holdings.find((item) => item.ticker === "BBB")?.shares).toBe(
    60
  );
});

test("capturing a snapshot updates the same market date instead of duplicating it", async () => {
  const t = convexTest(schema, modules);
  await insertStock(t, "AAA", 100);
  await insertStock(t, "SPY", 600, "ETF");
  const portfolioId = await t.mutation(internal.portfolios.create, {
    name: "Snapshot",
    type: "actual",
  });
  await t.mutation(internal.portfolios.upsertHolding, {
    portfolioId,
    ticker: "AAA",
    shares: 10,
    averageCost: 80,
    targetAllocation: 100,
  });
  const quotedAt = Date.parse("2026-07-24T20:30:00Z");
  const first = await t.mutation(internal.portfolios.captureSnapshot, {
    portfolioId,
    quotes: [
      {
        ticker: "AAA",
        price: 101,
        change: 1,
        changePercent: 1,
        quotedAt,
        fresh: true,
      },
      {
        ticker: "SPY",
        price: 600,
        change: 2,
        changePercent: 0.3,
        quotedAt,
        fresh: true,
      },
    ],
  });
  const second = await t.mutation(internal.portfolios.captureSnapshot, {
    portfolioId,
    quotes: [
      {
        ticker: "AAA",
        price: 102,
        change: 2,
        changePercent: 2,
        quotedAt,
        fresh: true,
      },
      {
        ticker: "SPY",
        price: 601,
        change: 3,
        changePercent: 0.5,
        quotedAt,
        fresh: true,
      },
    ],
  });
  const history = await t.query(api.portfolios.history, { portfolioId });
  expect(first.marketDate).toBe("2026-07-24");
  expect(second.marketDate).toBe("2026-07-24");
  expect(history).toHaveLength(1);
  expect(history[0].totalValue).toBe(1020);
});

test("duplicating and archiving preserve holdings and exclude archived portfolios", async () => {
  const t = convexTest(schema, modules);
  const original = await t.mutation(internal.portfolios.create, {
    name: "Original",
    type: "actual",
  });
  await t.mutation(internal.portfolios.upsertHolding, {
    portfolioId: original,
    ticker: "AAA",
    shares: 5,
    averageCost: 10,
    targetAllocation: 50,
  });
  const copy = await t.mutation(internal.portfolios.duplicate, {
    portfolioId: original,
    name: "Copy",
  });
  await t.mutation(internal.portfolios.archive, { portfolioId: original });

  const active = await t.query(api.portfolios.list, {});
  const all = await t.query(api.portfolios.list, { includeArchived: true });
  const copyDashboard = await t.query(api.portfolios.getDashboard, {
    portfolioId: copy,
  });
  expect(active.map((item) => item.name)).toEqual(["Copy"]);
  expect(all).toHaveLength(2);
  expect(copyDashboard.holdings).toHaveLength(1);
});
