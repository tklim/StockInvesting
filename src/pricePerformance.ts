export type PriceRange =
  | "1D"
  | "5D"
  | "1M"
  | "3M"
  | "6M"
  | "YTD"
  | "1Y"
  | "5Y"
  | "MAX";

const LOOKBACK_INTERVALS: Record<Exclude<PriceRange, "MAX">, number> = {
  "1D": 1,
  "5D": 5,
  "1M": 21,
  "3M": 63,
  "6M": 126,
  YTD: 180,
  "1Y": 252,
  "5Y": 1_260,
};

export function getLookbackIntervals(range: PriceRange, pointCount: number) {
  return range === "MAX"
    ? Math.max(pointCount - 1, 0)
    : LOOKBACK_INTERVALS[range];
}

export function getChartPointsForRange(points: number[], range: PriceRange) {
  // A return over N intervals needs N + 1 daily observations.
  const observationCount = getLookbackIntervals(range, points.length) + 1;
  return points.slice(-Math.min(observationCount, points.length));
}

export function getReturnPercent(
  points: number[],
  lookbackIntervals: number,
  requireFullHistory = false
) {
  if (
    lookbackIntervals < 1 ||
    (requireFullHistory && points.length <= lookbackIntervals)
  ) {
    return null;
  }

  const latest = points[points.length - 1];
  const baseline = points[Math.max(points.length - 1 - lookbackIntervals, 0)];

  if (!Number.isFinite(latest) || !Number.isFinite(baseline) || baseline === 0) {
    return null;
  }

  return ((latest - baseline) / baseline) * 100;
}

export function formatReturn(
  points: number[],
  lookbackIntervals: number,
  requireFullHistory = false
) {
  const changePercent = getReturnPercent(
    points,
    lookbackIntervals,
    requireFullHistory
  );

  if (changePercent === null) {
    return "N/A";
  }

  return `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%`;
}
