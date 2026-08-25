import { describe, expect, test } from "vitest";
import {
  formatReturn,
  getChartPointsForRange,
  getLookbackIntervals,
} from "./pricePerformance";

describe("price performance periods", () => {
  const points = Array.from({ length: 365 }, (_, index) => index + 100);

  test("uses the requested number of price intervals", () => {
    expect(getChartPointsForRange(points, "5D")).toHaveLength(6);
    expect(getChartPointsForRange(points, "1M")).toHaveLength(22);
    expect(getChartPointsForRange(points, "3M")).toHaveLength(64);
  });

  test("keeps period returns independent from the selected chart range", () => {
    const selectedThreeMonthSlice = getChartPointsForRange(points, "3M");
    const sixMonthLookback = getLookbackIntervals("6M", points.length);

    expect(formatReturn(points, sixMonthLookback, true)).toBe("+37.28%");
    expect(formatReturn(selectedThreeMonthSlice, sixMonthLookback, true)).toBe(
      "N/A"
    );
  });

  test("does not label a shorter history as a full period", () => {
    expect(formatReturn(points.slice(-42), 63, true)).toBe("N/A");
  });
});
