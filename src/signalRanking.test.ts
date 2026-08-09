import { describe, expect, test } from "vitest";
import {
  compareSignalRankingItems,
  defaultSignalSort,
  rankSignalItems,
  type SignalRankingItem,
  type SignalSortKey,
} from "./signalRanking";

const item = (
  ticker: string,
  listName: string,
  rating?: "BUY" | "HOLD" | "SELL",
  compositeScore = 50,
  computedAt = 1,
  values: {
    coverage?: number;
    winProbability?: number;
    outperformProbability?: number;
    dailyChange?: number;
    companyName?: string;
    price?: number;
  } = {}
): SignalRankingItem => ({
  ticker,
  listName,
  stock:
    values.dailyChange === undefined && values.companyName === undefined && values.price === undefined
      ? undefined
      : {
          changePercent: values.dailyChange,
          companyName: values.companyName,
          price: values.price,
        },
  stockSignal: rating
    ? {
        rating,
        compositeScore,
        computedAt,
        dataCoverage: values.coverage,
        winProbability: values.winProbability,
        outperformProbability: values.outperformProbability,
      }
    : undefined,
});

describe("six-month signal ranking", () => {
  test("globally sorts by composite score by default", () => {
    const ranked = rankSignalItems(
      [
        item("PENDING", "Core"),
        item("SELL", "Core", "SELL", 20),
        item("BUY", "Core", "BUY", 70),
        item("HOLD", "Core", "HOLD", 80),
      ],
      "All"
    );

    expect(ranked.map((entry) => entry.ticker)).toEqual([
      "HOLD",
      "BUY",
      "SELL",
      "PENDING",
    ]);
  });

  test("uses score, update time, and ticker as deterministic tie-breakers", () => {
    const ranked = [
      item("CCC", "Core", "BUY", 72, 10),
      item("BBB", "Core", "BUY", 75, 9),
      item("AAA", "Core", "BUY", 75, 9),
      item("DDD", "Core", "BUY", 75, 12),
    ].sort((left, right) => compareSignalRankingItems(left, right, defaultSignalSort));

    expect(ranked.map((entry) => entry.ticker)).toEqual([
      "DDD",
      "AAA",
      "BBB",
      "CCC",
    ]);
  });

  test("filters to a named watchlist before ranking", () => {
    const ranked = rankSignalItems(
      [
        item("AAA", "Core", "HOLD", 55),
        item("BBB", "Growth", "BUY", 80),
        item("CCC", "Core", "BUY", 65),
      ],
      "Core"
    );

    expect(ranked.map((entry) => entry.ticker)).toEqual(["CCC", "AAA"]);
  });

  test.each<{
    key: SignalSortKey;
    low: SignalRankingItem;
    high: SignalRankingItem;
  }>([
    {
      key: "company",
      low: item("LOW", "Core", "BUY", 80, 1, { companyName: "Acme" }),
      high: item("HIGH", "Core", "HOLD", 50, 1, { companyName: "Zenith" }),
    },
    {
      key: "price",
      low: item("LOW", "Core", "BUY", 80, 1, { price: 101.25 }),
      high: item("HIGH", "Core", "HOLD", 50, 1, { price: 480.5 }),
    },
    {
      key: "score",
      low: item("LOW", "Core", "SELL", 20),
      high: item("HIGH", "Core", "BUY", 80),
    },
    {
      key: "coverage",
      low: item("LOW", "Core", "BUY", 80, 1, { coverage: 60 }),
      high: item("HIGH", "Core", "HOLD", 50, 1, { coverage: 95 }),
    },
    {
      key: "winProbability",
      low: item("LOW", "Core", "BUY", 80, 1, { winProbability: 0.52 }),
      high: item("HIGH", "Core", "HOLD", 50, 1, { winProbability: 0.71 }),
    },
    {
      key: "outperformProbability",
      low: item("LOW", "Core", "BUY", 80, 1, { outperformProbability: 0.48 }),
      high: item("HIGH", "Core", "HOLD", 50, 1, { outperformProbability: 0.67 }),
    },
    {
      key: "dailyChange",
      low: item("LOW", "Core", "BUY", 80, 1, { dailyChange: -1.5 }),
      high: item("HIGH", "Core", "HOLD", 50, 1, { dailyChange: 2.25 }),
    },
    {
      key: "updatedAt",
      low: item("LOW", "Core", "BUY", 80, 10),
      high: item("HIGH", "Core", "HOLD", 50, 20),
    },
  ])("sorts $key in both directions", ({ key, low, high }) => {
    expect(rankSignalItems([low, high], "All", { key, direction: "desc" })).toEqual([
      high,
      low,
    ]);
    expect(rankSignalItems([low, high], "All", { key, direction: "asc" })).toEqual([
      low,
      high,
    ]);
  });

  test("keeps unavailable values last in both directions", () => {
    const present = item("PRESENT", "Core", "BUY", 80, 1, { winProbability: 0.6 });
    const provisional = item("PROV", "Core", "BUY", 75, 2);
    const pending = item("PENDING", "Core");

    expect(
      rankSignalItems([pending, provisional, present], "All", {
        key: "winProbability",
        direction: "desc",
      }).map((entry) => entry.ticker)
    ).toEqual(["PRESENT", "PROV", "PENDING"]);
    expect(
      rankSignalItems([pending, provisional, present], "All", {
        key: "winProbability",
        direction: "asc",
      }).map((entry) => entry.ticker)
    ).toEqual(["PRESENT", "PROV", "PENDING"]);
  });
});
