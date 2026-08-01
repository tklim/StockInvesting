import { describe, expect, test } from "vitest";
import {
  SIGNAL_HORIZON_DAYS,
  buildCurrentFeatures,
  buildHistoricalObservations,
  calculateAnalogForecast,
  calculateCompositeScore,
  calculateDataCoverage,
  classifyAggressiveSignal,
  isAiSignalFresh,
  roundProbabilityPercent,
  type AnalogForecast,
  type DailyPriceBar,
  type SignalObservation,
} from "./signalModel";

const day = 24 * 60 * 60 * 1000;

const makeBars = (
  ticker: string,
  count: number,
  dailyReturn: number,
  closeMultiplier = 1
): DailyPriceBar[] =>
  Array.from({ length: count }, (_, index) => {
    const adjustedClose = 100 * (1 + dailyReturn) ** index;
    return {
      ticker,
      tradingDate: new Date(Date.UTC(2018, 0, 1) + index * day)
        .toISOString()
        .slice(0, 10),
      close: adjustedClose * closeMultiplier,
      adjustedClose,
      source: "test adjusted",
      fetchedAt: 1,
    };
  });

const provisionalForecast: AnalogForecast = {
  sampleSize: 0,
  tickerCount: 0,
  calibrationSampleSize: 0,
  calibrated: false,
  confidence: "low",
};

describe("signal-v1-6m features", () => {
  test("uses adjusted prices and aligns stock dates with SPY", () => {
    const stock = makeBars("ABC", 400, 0.001, 10);
    const spy = makeBars("SPY", 400, 0.0004).filter((_, index) => index !== 100);
    const features = buildCurrentFeatures(stock, spy);

    expect(features).not.toBeNull();
    expect(features!.return6m).toBeCloseTo((1.001 ** 126) - 1, 8);
    expect(features!.relativeReturn6m).toBeCloseTo(
      1.001 ** 126 - 1.0004 ** 126,
      8
    );
  });

  test("requires a complete 12-month feature window", () => {
    expect(buildCurrentFeatures(makeBars("ABC", 252, 0.001), makeBars("SPY", 252, 0.001))).toBeNull();
  });

  test("uses exactly 126 trading observations for the forward target", () => {
    const stock = makeBars("ABC", 700, 0.001);
    const spy = makeBars("SPY", 700, 0.0005);
    const observations = buildHistoricalObservations("ABC", stock, spy);
    const first = observations[0];
    const endIndex = 252;

    expect(SIGNAL_HORIZON_DAYS).toBe(126);
    expect(first.forwardReturn).toBeCloseTo(
      stock[endIndex + 126].adjustedClose / stock[endIndex].adjustedClose - 1,
      10
    );
  });

  test("does not leak future prices into observation features", () => {
    const stock = makeBars("ABC", 700, 0.001);
    const spy = makeBars("SPY", 700, 0.0005);
    const original = buildHistoricalObservations("ABC", stock, spy)[0];
    const changed = stock.map((bar) => ({ ...bar }));
    changed[252 + SIGNAL_HORIZON_DAYS].adjustedClose *= 3;
    const recomputed = buildHistoricalObservations("ABC", changed, spy)[0];

    expect(recomputed.features).toEqual(original.features);
    expect(recomputed.forwardReturn).not.toEqual(original.forwardReturn);
  });
});

describe("signal weighting and gates", () => {
  test("applies the documented factor weights and neutral missing coverage", () => {
    expect(
      calculateCompositeScore({
        market: 100,
        growth: 0,
        profitability: 0,
        balanceSheet: 0,
        valuation: 0,
        ai: 0,
      })
    ).toBe(40);
    expect(
      calculateDataCoverage({
        market: 100,
        growth: 100,
        profitability: 100,
        balanceSheet: 100,
        valuation: 0,
        ai: 0,
      })
    ).toBe(75);
  });

  test("uses aggressive provisional and calibrated thresholds", () => {
    expect(
      classifyAggressiveSignal({ compositeScore: 70, coverage: 70, forecast: provisionalForecast })
    ).toEqual({ rating: "BUY", provisional: true });
    expect(
      classifyAggressiveSignal({ compositeScore: 30, coverage: 70, forecast: provisionalForecast })
    ).toEqual({ rating: "SELL", provisional: true });
    expect(
      classifyAggressiveSignal({ compositeScore: 90, coverage: 69, forecast: provisionalForecast })
    ).toEqual({ rating: "HOLD", provisional: true });

    const calibrated: AnalogForecast = {
      ...provisionalForecast,
      calibrated: true,
      confidence: "medium",
      winProbability: 0.55,
      lossProbability: 0.45,
      outperformProbability: 0.5,
      expectedReturn: 0.01,
    };
    expect(
      classifyAggressiveSignal({ compositeScore: 62, coverage: 70, forecast: calibrated })
    ).toEqual({ rating: "BUY", provisional: false });
    expect(
      classifyAggressiveSignal({ compositeScore: 90, coverage: 69, forecast: calibrated })
    ).toEqual({ rating: "HOLD", provisional: false });
  });

  test("rounds published probabilities and keeps loss complementary", () => {
    const win = 0.5549;
    expect(roundProbabilityPercent(win)).toBe(55);
    expect(roundProbabilityPercent(win) + roundProbabilityPercent(1 - win)).toBe(100);
  });

  test("marks AI stale when it predates either synchronized input", () => {
    const now = Date.UTC(2026, 6, 19);
    expect(
      isAiSignalFresh({
        signalScore: 72,
        generatedAt: now - day,
        latestMarketSync: now - 2 * day,
        latestFinancialSync: now - 3 * day,
        now,
      })
    ).toBe(true);
    expect(
      isAiSignalFresh({
        signalScore: 72,
        generatedAt: now - 3 * day,
        latestMarketSync: now - 2 * day,
        latestFinancialSync: now - day,
        now,
      })
    ).toBe(false);
  });

  test("withholds calibrated percentages below the evidence gates", () => {
    const observations: SignalObservation[] = Array.from({ length: 299 }, (_, index) => ({
      ticker: `T${index % 7}`,
      observationDate: new Date(Date.UTC(2010, 0, 1) + index * 21 * day)
        .toISOString()
        .slice(0, 10),
      features: {
        return1m: index / 1000,
        return3m: index / 800,
        return6m: index / 600,
        return12m: index / 400,
        relativeReturn6m: index / 1500,
        sma200Distance: index / 1200,
        volatility63d: 0.2 + (index % 10) / 100,
        maxDrawdown126d: 0.1 + (index % 7) / 100,
      },
      forwardReturn: index % 2 ? 0.1 : -0.05,
      forwardExcessReturn: index % 3 ? 0.03 : -0.02,
      win: index % 2 === 1,
      outperform: index % 3 !== 0,
    }));
    const forecast = calculateAnalogForecast(
      observations[0].features,
      observations,
      10,
      "2026-07-19"
    );
    expect(forecast.calibrated).toBe(false);
    expect(forecast.winProbability).toBeUndefined();
  });
});
