export const SIGNAL_MODEL_VERSION = "signal-v1-6m";
export const SIGNAL_HORIZON_DAYS = 126;

export type DailyPriceBar = {
  ticker: string;
  tradingDate: string;
  close: number;
  adjustedClose: number;
  volume?: number;
  source: string;
  fetchedAt: number;
};

export type SignalFeatures = {
  return1m: number;
  return3m: number;
  return6m: number;
  return12m: number;
  relativeReturn6m: number;
  sma200Distance: number;
  volatility63d: number;
  maxDrawdown126d: number;
};

export type SignalObservation = {
  ticker: string;
  observationDate: string;
  features: SignalFeatures;
  forwardReturn: number;
  forwardExcessReturn: number;
  win: boolean;
  outperform: boolean;
};

export type AnalogForecast = {
  winProbability?: number;
  lossProbability?: number;
  outperformProbability?: number;
  expectedReturn?: number;
  expectedExcessReturn?: number;
  downsideP10?: number;
  sampleSize: number;
  tickerCount: number;
  calibrationSampleSize: number;
  brierScore?: number;
  outperformBrierScore?: number;
  calibrated: boolean;
  confidence: "low" | "medium" | "high";
};

export type FactorScores = {
  market: number;
  growth: number;
  profitability: number;
  balanceSheet: number;
  valuation: number;
  ai: number;
};

export const SIGNAL_FACTOR_WEIGHTS: Record<keyof FactorScores, number> = {
  market: 0.4,
  growth: 0.15,
  profitability: 0.12,
  balanceSheet: 0.08,
  valuation: 0.15,
  ai: 0.1,
};

const featureKeys: Array<keyof SignalFeatures> = [
  "return1m",
  "return3m",
  "return6m",
  "return12m",
  "relativeReturn6m",
  "sma200Distance",
  "volatility63d",
  "maxDrawdown126d",
];

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

const mean = (values: number[]) =>
  values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;

const median = (values: number[]) => {
  if (!values.length) return 0;
  const ordered = [...values].sort((left, right) => left - right);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2
    ? ordered[middle]
    : (ordered[middle - 1] + ordered[middle]) / 2;
};

const quantile = (values: number[], percentile: number) => {
  if (!values.length) return 0;
  const ordered = [...values].sort((left, right) => left - right);
  const index = clamp(percentile, 0, 1) * (ordered.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  const fraction = index - lower;
  return ordered[lower] * (1 - fraction) + ordered[upper] * fraction;
};

const returnOver = (values: number[], endIndex: number, lookback: number) => {
  const start = values[endIndex - lookback];
  const end = values[endIndex];
  return start > 0 && end > 0 ? end / start - 1 : 0;
};

const standardDeviation = (values: number[]) => {
  if (values.length < 2) return 0;
  const average = mean(values);
  const variance = mean(values.map((value) => (value - average) ** 2));
  return Math.sqrt(variance);
};

const maximumDrawdown = (values: number[]) => {
  let peak = values[0] ?? 0;
  let drawdown = 0;
  for (const value of values) {
    peak = Math.max(peak, value);
    if (peak > 0) drawdown = Math.max(drawdown, 1 - value / peak);
  }
  return drawdown;
};

const toAlignedSeries = (bars: DailyPriceBar[], spyBars: DailyPriceBar[]) => {
  const spyByDate = new Map(
    spyBars.map((bar) => [bar.tradingDate, bar.adjustedClose] as const)
  );
  return bars
    .filter((bar) => Number.isFinite(bar.adjustedClose) && spyByDate.has(bar.tradingDate))
    .sort((left, right) => left.tradingDate.localeCompare(right.tradingDate))
    .map((bar) => ({
      date: bar.tradingDate,
      stock: bar.adjustedClose,
      spy: spyByDate.get(bar.tradingDate) as number,
    }));
};

const featuresAt = (
  stockValues: number[],
  spyValues: number[],
  endIndex: number
): SignalFeatures | null => {
  if (endIndex < 252) return null;
  const recentReturns = stockValues
    .slice(endIndex - 63, endIndex + 1)
    .slice(1)
    .map((value, index) => Math.log(value / stockValues[endIndex - 63 + index]))
    .filter(Number.isFinite);
  const sma200 = mean(stockValues.slice(endIndex - 199, endIndex + 1));
  const current = stockValues[endIndex];
  if (!current || !sma200 || recentReturns.length < 40) return null;

  return {
    return1m: returnOver(stockValues, endIndex, 21),
    return3m: returnOver(stockValues, endIndex, 63),
    return6m: returnOver(stockValues, endIndex, 126),
    return12m: returnOver(stockValues, endIndex, 252),
    relativeReturn6m:
      returnOver(stockValues, endIndex, 126) -
      returnOver(spyValues, endIndex, 126),
    sma200Distance: current / sma200 - 1,
    volatility63d: standardDeviation(recentReturns) * Math.sqrt(252),
    maxDrawdown126d: maximumDrawdown(
      stockValues.slice(endIndex - 125, endIndex + 1)
    ),
  };
};

export const buildHistoricalObservations = (
  ticker: string,
  bars: DailyPriceBar[],
  spyBars: DailyPriceBar[]
): SignalObservation[] => {
  const aligned = toAlignedSeries(bars, spyBars);
  const stockValues = aligned.map((item) => item.stock);
  const spyValues = aligned.map((item) => item.spy);
  const observations: SignalObservation[] = [];

  for (
    let endIndex = 252;
    endIndex + SIGNAL_HORIZON_DAYS < aligned.length;
    endIndex += 21
  ) {
    const features = featuresAt(stockValues, spyValues, endIndex);
    if (!features) continue;
    const forwardReturn =
      stockValues[endIndex + SIGNAL_HORIZON_DAYS] / stockValues[endIndex] - 1;
    const spyForwardReturn =
      spyValues[endIndex + SIGNAL_HORIZON_DAYS] / spyValues[endIndex] - 1;
    if (!Number.isFinite(forwardReturn) || !Number.isFinite(spyForwardReturn)) continue;

    observations.push({
      ticker,
      observationDate: aligned[endIndex].date,
      features,
      forwardReturn,
      forwardExcessReturn: forwardReturn - spyForwardReturn,
      win: forwardReturn > 0,
      outperform: forwardReturn > spyForwardReturn,
    });
  }

  return observations;
};

export const buildCurrentFeatures = (
  bars: DailyPriceBar[],
  spyBars: DailyPriceBar[]
) => {
  const aligned = toAlignedSeries(bars, spyBars);
  if (aligned.length < 253) return null;
  return featuresAt(
    aligned.map((item) => item.stock),
    aligned.map((item) => item.spy),
    aligned.length - 1
  );
};

export const buildFallbackFeatures = (points: number[]) => {
  const valid = points.filter((point) => Number.isFinite(point) && point > 0);
  if (valid.length < 21) return null;
  const endIndex = valid.length - 1;
  const fallbackReturn = (lookback: number) =>
    returnOver(valid, endIndex, Math.min(lookback, endIndex));
  const returns = valid
    .slice(Math.max(0, valid.length - 64))
    .slice(1)
    .map((value, index) =>
      Math.log(value / valid[Math.max(0, valid.length - 64) + index])
    )
    .filter(Number.isFinite);
  const sma = mean(valid.slice(-Math.min(200, valid.length)));

  return {
    return1m: fallbackReturn(21),
    return3m: fallbackReturn(63),
    return6m: fallbackReturn(126),
    return12m: fallbackReturn(252),
    relativeReturn6m: 0,
    sma200Distance: sma ? valid[endIndex] / sma - 1 : 0,
    volatility63d: standardDeviation(returns) * Math.sqrt(252),
    maxDrawdown126d: maximumDrawdown(valid.slice(-Math.min(126, valid.length))),
  } satisfies SignalFeatures;
};

type WeightedNeighbor = SignalObservation & { distance: number; weight: number };

const robustStats = (observations: SignalObservation[]) =>
  Object.fromEntries(
    featureKeys.map((key) => {
      const values = observations.map((item) => item.features[key]);
      const center = median(values);
      const spread = Math.max(quantile(values, 0.75) - quantile(values, 0.25), 0.0001);
      return [key, { center, spread }];
    })
  ) as Record<keyof SignalFeatures, { center: number; spread: number }>;

const rawAnalogForecast = (
  current: SignalFeatures,
  observations: SignalObservation[],
  nowDate: string
) => {
  if (observations.length < 75) return null;
  const stats = robustStats(observations);
  const currentVector = featureKeys.map((key) =>
    clamp((current[key] - stats[key].center) / stats[key].spread, -3, 3)
  );
  const now = Date.parse(`${nowDate}T00:00:00Z`);
  const neighbors: WeightedNeighbor[] = observations
    .map((item) => {
      const vector = featureKeys.map((key) =>
        clamp((item.features[key] - stats[key].center) / stats[key].spread, -3, 3)
      );
      const distance = Math.sqrt(
        mean(vector.map((value, index) => (value - currentVector[index]) ** 2))
      );
      const ageYears = Math.max(
        0,
        (now - Date.parse(`${item.observationDate}T00:00:00Z`)) /
          (365.25 * 24 * 60 * 60 * 1000)
      );
      return {
        ...item,
        distance,
        weight: Math.exp(-distance) * Math.pow(0.5, ageYears / 5),
      };
    })
    .sort((left, right) => left.distance - right.distance)
    .slice(0, 75);

  const byTicker = new Map<string, number>();
  for (const neighbor of neighbors) {
    byTicker.set(
      neighbor.ticker,
      (byTicker.get(neighbor.ticker) ?? 0) + neighbor.weight
    );
  }

  const allocations = new Map<string, number>();
  const remaining = new Set(byTicker.keys());
  const canCapTickerShare = byTicker.size >= 5;
  let remainingShare = 1;
  while (remaining.size) {
    const remainingWeight = Array.from(remaining).reduce(
      (total, ticker) => total + (byTicker.get(ticker) ?? 0),
      0
    );
    const newlyCapped = Array.from(remaining).filter((ticker) =>
      canCapTickerShare
        ? (remainingShare * (byTicker.get(ticker) ?? 0)) / Math.max(remainingWeight, 1e-12) >
          0.2
        : false
    );
    if (!newlyCapped.length) {
      for (const ticker of remaining) {
        allocations.set(
          ticker,
          (remainingShare * (byTicker.get(ticker) ?? 0)) /
            Math.max(remainingWeight, 1e-12)
        );
      }
      break;
    }
    for (const ticker of newlyCapped) {
      allocations.set(ticker, 0.2);
      remaining.delete(ticker);
      remainingShare -= 0.2;
    }
  }

  const scaled = neighbors.map((item) => ({
    ...item,
    weight:
      ((allocations.get(item.ticker) ?? 0) * item.weight * neighbors.length) /
      Math.max(byTicker.get(item.ticker) ?? 0, 1e-12),
  }));
  const weightTotal = scaled.reduce((total, item) => total + item.weight, 0);
  const weighted = (pick: (item: WeightedNeighbor) => number) =>
    scaled.reduce((total, item) => total + pick(item) * item.weight, 0) / weightTotal;
  const forwardReturns = scaled.map((item) => item.forwardReturn);
  const lower = quantile(forwardReturns, 0.05);
  const upper = quantile(forwardReturns, 0.95);

  return {
    winProbability:
      (2 + scaled.reduce((total, item) => total + (item.win ? item.weight : 0), 0)) /
      (4 + weightTotal),
    outperformProbability:
      (2 +
        scaled.reduce((total, item) => total + (item.outperform ? item.weight : 0), 0)) /
      (4 + weightTotal),
    expectedReturn: weighted((item) => clamp(item.forwardReturn, lower, upper)),
    expectedExcessReturn: weighted((item) => item.forwardExcessReturn),
    downsideP10: quantile(forwardReturns, 0.1),
    sampleSize: scaled.length,
  };
};

const logit = (probability: number) =>
  Math.log(clamp(probability, 0.001, 0.999) / (1 - clamp(probability, 0.001, 0.999)));
const sigmoid = (value: number) => 1 / (1 + Math.exp(-clamp(value, -30, 30)));

const fitPlatt = (rows: Array<{ probability: number; outcome: boolean }>) => {
  let slope = 1;
  let intercept = 0;
  const learningRate = 0.02;
  for (let iteration = 0; iteration < 600; iteration += 1) {
    let slopeGradient = 0;
    let interceptGradient = 0;
    for (const row of rows) {
      const x = logit(row.probability);
      const predicted = sigmoid(slope * x + intercept);
      const error = predicted - (row.outcome ? 1 : 0);
      slopeGradient += error * x;
      interceptGradient += error;
    }
    const denominator = Math.max(rows.length, 1);
    slope -= learningRate * (slopeGradient / denominator + 0.001 * slope);
    intercept -= learningRate * (interceptGradient / denominator);
  }
  return { slope, intercept };
};

const applyPlatt = (probability: number, model: { slope: number; intercept: number }) =>
  sigmoid(model.slope * logit(probability) + model.intercept);

export const calculateAnalogForecast = (
  current: SignalFeatures,
  observations: SignalObservation[],
  targetHistoryYears: number,
  asOfDate: string
): AnalogForecast => {
  const ordered = [...observations].sort((left, right) =>
    left.observationDate.localeCompare(right.observationDate)
  );
  const tickerCount = new Set(ordered.map((item) => item.ticker)).size;
  const raw = rawAnalogForecast(current, ordered, asOfDate);
  const fallback: AnalogForecast = {
    sampleSize: raw?.sampleSize ?? 0,
    tickerCount,
    calibrationSampleSize: 0,
    calibrated: false,
    confidence: "low",
    expectedReturn: raw?.expectedReturn,
    expectedExcessReturn: raw?.expectedExcessReturn,
    downsideP10: raw?.downsideP10,
  };
  if (!raw || ordered.length < 300 || tickerCount < 8 || targetHistoryYears < 5) {
    return fallback;
  }

  const candidateRows: Array<{
    winProbability: number;
    outperformProbability: number;
    win: boolean;
    outperform: boolean;
  }> = [];
  const validationPool = ordered.slice(-Math.min(360, Math.floor(ordered.length * 0.4)));
  for (const item of validationPool) {
    const prior = ordered.filter(
      (candidate) => candidate.observationDate < item.observationDate
    );
    if (prior.length < 300) continue;
    const prediction = rawAnalogForecast(item.features, prior, item.observationDate);
    if (!prediction) continue;
    candidateRows.push({
      winProbability: prediction.winProbability,
      outperformProbability: prediction.outperformProbability,
      win: item.win,
      outperform: item.outperform,
    });
  }
  if (candidateRows.length < 200) return fallback;

  const split = Math.floor(candidateRows.length / 2);
  const calibrationRows = candidateRows.slice(0, split);
  const evaluationRows = candidateRows.slice(split);
  if (evaluationRows.length < 100) return fallback;
  const winModel = fitPlatt(
    calibrationRows.map((row) => ({ probability: row.winProbability, outcome: row.win }))
  );
  const outperformModel = fitPlatt(
    calibrationRows.map((row) => ({
      probability: row.outperformProbability,
      outcome: row.outperform,
    }))
  );
  const brierScore = mean(
    evaluationRows.map((row) =>
      (applyPlatt(row.winProbability, winModel) - (row.win ? 1 : 0)) ** 2
    )
  );
  const outperformBrierScore = mean(
    evaluationRows.map((row) =>
      (applyPlatt(row.outperformProbability, outperformModel) -
        (row.outperform ? 1 : 0)) ** 2
    )
  );
  if (brierScore > 0.24 || outperformBrierScore > 0.24) {
    return {
      ...fallback,
      calibrationSampleSize: evaluationRows.length,
      brierScore,
      outperformBrierScore,
    };
  }

  const winProbability = applyPlatt(raw.winProbability, winModel);
  const confidence =
    evaluationRows.length >= 250 && tickerCount >= 12 && targetHistoryYears >= 8 && brierScore <= 0.21
      ? "high"
      : "medium";
  return {
    winProbability,
    lossProbability: 1 - winProbability,
    outperformProbability: applyPlatt(raw.outperformProbability, outperformModel),
    expectedReturn: raw.expectedReturn,
    expectedExcessReturn: raw.expectedExcessReturn,
    downsideP10: raw.downsideP10,
    sampleSize: raw.sampleSize,
    tickerCount,
    calibrationSampleSize: evaluationRows.length,
    brierScore,
    outperformBrierScore,
    calibrated: true,
    confidence,
  };
};

const linearScore = (value: number, weak: number, strong: number) =>
  clamp(((value - weak) / (strong - weak)) * 100, 0, 100);

export const scoreMarketFeatures = (features: SignalFeatures | null) => {
  if (!features) return { score: 50, coverage: 0 };
  return {
    score: mean([
      linearScore(features.return6m, -0.2, 0.3),
      linearScore(features.return12m, -0.3, 0.5),
      linearScore(features.relativeReturn6m, -0.2, 0.2),
      linearScore(features.sma200Distance, -0.25, 0.25),
      linearScore(features.volatility63d, 0.65, 0.15),
      linearScore(features.maxDrawdown126d, 0.45, 0.05),
    ]),
    coverage: 100,
  };
};

export const classifyAggressiveSignal = (input: {
  compositeScore: number;
  coverage: number;
  forecast: AnalogForecast;
}) => {
  const { compositeScore, coverage, forecast } = input;
  if (coverage < 70) {
    return { rating: "HOLD" as const, provisional: !forecast.calibrated };
  }
  if (!forecast.calibrated) {
    if (compositeScore >= 70) return { rating: "BUY" as const, provisional: true };
    if (compositeScore <= 30) return { rating: "SELL" as const, provisional: true };
    return { rating: "HOLD" as const, provisional: true };
  }
  if (
    compositeScore >= 62 &&
    (forecast.winProbability ?? 0) >= 0.55 &&
    (forecast.outperformProbability ?? 0) >= 0.5 &&
    (forecast.expectedReturn ?? 0) > 0
  ) {
    return { rating: "BUY" as const, provisional: false };
  }
  if (
    compositeScore <= 38 &&
    ((forecast.winProbability ?? 1) <= 0.45 || (forecast.expectedReturn ?? 0) < 0)
  ) {
    return { rating: "SELL" as const, provisional: false };
  }
  return { rating: "HOLD" as const, provisional: false };
};

export const roundScore = (value: number) => Math.round(clamp(value, 0, 100));

export const calculateCompositeScore = (scores: FactorScores) =>
  roundScore(
    (Object.keys(SIGNAL_FACTOR_WEIGHTS) as Array<keyof FactorScores>).reduce(
      (total, key) => total + scores[key] * SIGNAL_FACTOR_WEIGHTS[key],
      0
    )
  );

export const calculateDataCoverage = (coverage: FactorScores) =>
  roundScore(
    (Object.keys(SIGNAL_FACTOR_WEIGHTS) as Array<keyof FactorScores>).reduce(
      (total, key) => total + coverage[key] * SIGNAL_FACTOR_WEIGHTS[key],
      0
    )
  );

export const isAiSignalFresh = (input: {
  signalScore?: number;
  generatedAt?: number;
  latestMarketSync: number;
  latestFinancialSync?: number;
  now: number;
}) =>
  input.signalScore !== undefined &&
  input.generatedAt !== undefined &&
  input.generatedAt >=
    Math.max(input.latestMarketSync, input.latestFinancialSync ?? 0) &&
  input.now - input.generatedAt <= 14 * 24 * 60 * 60 * 1000;

export const roundProbabilityPercent = (probability: number) =>
  Math.round(clamp(probability, 0, 1) * 100);
