/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api, internal } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

test("daily adjusted-bar backfills are idempotent", async () => {
  const t = convexTest(schema, modules);
  const bar = {
    ticker: "abc",
    tradingDate: "2026-07-17",
    close: 101,
    adjustedClose: 100,
    source: "test adjust=all",
    fetchedAt: 1,
  };

  expect(await t.mutation(internal.signals.upsertBarsBatch, { bars: [bar] })).toEqual({
    inserted: 1,
    updated: 0,
  });
  expect(await t.mutation(internal.signals.upsertBarsBatch, { bars: [bar] })).toEqual({
    inserted: 0,
    updated: 0,
  });
  const rows = await t.run(async (ctx) => await ctx.db.query("dailyPriceBars").collect());
  expect(rows).toHaveLength(1);
});

test("existing AI reports remain valid without optional signal fields", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    await ctx.db.insert("aiReports", {
      ticker: "ABC",
      summary: "Legacy report",
      bullPoints: ["A"],
      bearPoints: ["B"],
      thesisPoints: ["C"],
      watchItems: ["D"],
      provider: "Legacy",
      model: "legacy-model",
      generatedAt: 1,
    });
  });
  const report = await t.run(async (ctx) => await ctx.db.query("aiReports").unique());
  expect(report?.signalScore).toBeUndefined();
  expect(report?.signalRationale).toBeUndefined();
});

test("provider failure preserves the previous signal and marks it stale", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    await ctx.db.insert("stockSignals", {
      ticker: "ABC",
      rating: "BUY",
      provisional: true,
      compositeScore: 73,
      horizonDays: 126,
      factorScores: {
        market: 80,
        growth: 70,
        profitability: 70,
        balanceSheet: 60,
        valuation: 65,
        ai: 50,
      },
      confidence: "low",
      sampleSize: 0,
      tickerCount: 0,
      calibrationSampleSize: 0,
      dataCoverage: 82,
      topPositiveDrivers: ["Trend"],
      topNegativeDrivers: ["Valuation"],
      aiFresh: false,
      modelVersion: "signal-v1-6m",
      dataStatus: "insufficient",
      source: "test",
      computedAt: 10,
      inputsUpdatedAt: 9,
    });
  });

  await t.mutation(internal.signals.markSignalStale, { ticker: "abc" });
  const signal = await t.run(async (ctx) => await ctx.db.query("stockSignals").unique());
  expect(signal?.dataStatus).toBe("stale");
  expect(signal?.rating).toBe("BUY");
  expect(signal?.compositeScore).toBe(73);
  expect(signal?.computedAt).toBe(10);
});

test("portfolio returns saved stocks with present, provisional, stale, and missing signals", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    const tickers = ["BUY", "PROV", "STALE", "PENDING"];
    for (const [index, ticker] of tickers.entries()) {
      await ctx.db.insert("stocks", {
        ticker,
        companyName: `${ticker} Corp`,
        exchange: "NASDAQ",
        sector: "Technology",
        price: 100 + index,
        change: 1,
        changePercent: 1,
        marketCap: "100B",
        peRatio: "20",
        revenueTtm: "10B",
        epsTtm: "5",
        dividendYield: "N/A",
        summary: "Test stock",
        updatedAt: 100 + index,
      });
      await ctx.db.insert("portfolioStocks", {
        ticker,
        listName: index % 2 === 0 ? "Core" : "Growth",
        savedAt: 100 + index,
      });
    }

    const baseSignal = {
      horizonDays: 126,
      factorScores: {
        market: 60,
        growth: 60,
        profitability: 60,
        balanceSheet: 60,
        valuation: 60,
        ai: 50,
      },
      confidence: "medium" as const,
      sampleSize: 75,
      tickerCount: 8,
      calibrationSampleSize: 100,
      dataCoverage: 80,
      topPositiveDrivers: ["Trend"],
      topNegativeDrivers: ["Valuation"],
      aiFresh: false,
      modelVersion: "signal-v1-6m",
      source: "test",
      inputsUpdatedAt: 90,
    };

    await ctx.db.insert("stockSignals", {
      ...baseSignal,
      ticker: "BUY",
      rating: "BUY",
      provisional: false,
      compositeScore: 70,
      winProbability: 0.6,
      lossProbability: 0.4,
      outperformProbability: 0.55,
      dataStatus: "ready",
      computedAt: 100,
    });
    await ctx.db.insert("stockSignals", {
      ...baseSignal,
      ticker: "PROV",
      rating: "HOLD",
      provisional: true,
      compositeScore: 55,
      dataStatus: "insufficient",
      computedAt: 101,
    });
    await ctx.db.insert("stockSignals", {
      ...baseSignal,
      ticker: "STALE",
      rating: "SELL",
      provisional: false,
      compositeScore: 30,
      winProbability: 0.4,
      lossProbability: 0.6,
      outperformProbability: 0.35,
      dataStatus: "stale",
      computedAt: 102,
    });
  });

  const portfolio = await t.query(api.stocks.portfolio, {});
  expect(portfolio).toHaveLength(4);
  expect(portfolio.find((item) => item.ticker === "BUY")?.stockSignal?.rating).toBe(
    "BUY"
  );
  expect(portfolio.find((item) => item.ticker === "PROV")?.stockSignal?.provisional).toBe(
    true
  );
  expect(portfolio.find((item) => item.ticker === "STALE")?.stockSignal?.dataStatus).toBe(
    "stale"
  );
  expect(portfolio.find((item) => item.ticker === "PENDING")?.stockSignal).toBeNull();
});
