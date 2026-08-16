import { describe, expect, test } from "vitest";
import {
  normalizeWatchlistStatuses,
  normalizeWatchlistTickers,
  sortWatchlistStatuses,
  validateWatchlistRequest,
} from "./watchlist";

describe("admin watchlist loading", () => {
  test("accepts only known Convex targets", () => {
    expect(validateWatchlistRequest({ target: "development" })).toEqual({
      target: "development",
    });
    expect(validateWatchlistRequest({ target: "production" })).toEqual({
      target: "production",
    });
    expect(() => validateWatchlistRequest({ target: "preview" })).toThrow(
      "valid Convex target",
    );
  });

  test("normalizes, groups, sorts, and deduplicates saved watchlist tickers", () => {
    expect(
      normalizeWatchlistTickers([
        {
          ticker: " nvda ",
          listName: "Growth",
          stock: { companyName: "NVIDIA Corporation" },
        },
        { ticker: "AAPL", listName: "Core", stock: { companyName: "Apple Inc." } },
        { ticker: "NVDA", listName: "Other" },
        { ticker: "invalid ticker", listName: "Core" },
      ]),
    ).toEqual([
      { ticker: "AAPL", listName: "Core", companyName: "Apple Inc." },
      {
        ticker: "NVDA",
        listName: "Growth",
        companyName: "NVIDIA Corporation",
      },
    ]);
  });

  test("rejects a non-array Convex response", () => {
    expect(() => normalizeWatchlistTickers({ ticker: "NVDA" })).toThrow(
      "invalid watchlist response",
    );
  });

  test("normalizes saved refresh timestamps and preserves unavailable stages", () => {
    expect(
      normalizeWatchlistStatuses([
        {
          ticker: "NVDA",
          listName: "Mag7",
          companyName: "NVIDIA Corp",
          marketDataAt: 1_700_000_000_000,
          financialsAt: null,
          aiReportAt: 1_700_000_100_000,
          thesisAt: "missing",
          aiNotesAt: 1_700_000_200_000,
          signalsAt: 1_700_000_300_000,
        },
      ]),
    ).toEqual([
      {
        ticker: "NVDA",
        listName: "Mag7",
        companyName: "NVIDIA Corp",
        marketDataAt: 1_700_000_000_000,
        financialsAt: null,
        aiReportAt: 1_700_000_100_000,
        thesisAt: null,
        aiNotesAt: 1_700_000_200_000,
        signalsAt: 1_700_000_300_000,
      },
    ]);
  });

  test("sorts text and timestamps while leaving unavailable timestamps last", () => {
    const rows = [
      {
        ticker: "MSFT",
        listName: "Core",
        marketDataAt: 30,
        financialsAt: null,
        aiReportAt: null,
        thesisAt: null,
        aiNotesAt: null,
        signalsAt: null,
      },
      {
        ticker: "AAPL",
        listName: "Growth",
        marketDataAt: null,
        financialsAt: null,
        aiReportAt: null,
        thesisAt: null,
        aiNotesAt: null,
        signalsAt: null,
      },
      {
        ticker: "NVDA",
        listName: "AI Leaders",
        marketDataAt: 10,
        financialsAt: null,
        aiReportAt: null,
        thesisAt: null,
        aiNotesAt: null,
        signalsAt: null,
      },
    ];

    expect(sortWatchlistStatuses(rows, "ticker", "ascending").map((row) => row.ticker)).toEqual([
      "AAPL",
      "MSFT",
      "NVDA",
    ]);
    expect(sortWatchlistStatuses(rows, "marketDataAt", "descending").map((row) => row.ticker)).toEqual([
      "MSFT",
      "NVDA",
      "AAPL",
    ]);
  });
});
