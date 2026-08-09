export type RankingSignal = {
  rating: "BUY" | "HOLD" | "SELL";
  compositeScore: number;
  dataCoverage?: number;
  winProbability?: number;
  outperformProbability?: number;
  computedAt: number;
};

export type SignalRankingItem = {
  ticker: string;
  listName: string;
  stock?: {
    changePercent?: number;
    companyName?: string;
    price?: number;
  } | null;
  stockSignal?: RankingSignal | null;
};

export type SignalSortKey =
  | "company"
  | "price"
  | "score"
  | "coverage"
  | "winProbability"
  | "outperformProbability"
  | "dailyChange"
  | "updatedAt";

export type SignalSortDirection = "asc" | "desc";

export type SignalSort = {
  key: SignalSortKey;
  direction: SignalSortDirection;
};

export const defaultSignalSort: SignalSort = {
  key: "score",
  direction: "desc",
};

function getSortValue(item: SignalRankingItem, key: SignalSortKey) {
  switch (key) {
    case "company":
      return item.stock?.companyName ?? item.ticker;
    case "price":
      return item.stock?.price;
    case "score":
      return item.stockSignal?.compositeScore;
    case "coverage":
      return item.stockSignal?.dataCoverage;
    case "winProbability":
      return item.stockSignal?.winProbability;
    case "outperformProbability":
      return item.stockSignal?.outperformProbability;
    case "dailyChange":
      return item.stock?.changePercent;
    case "updatedAt":
      return item.stockSignal?.computedAt;
  }
}

export function compareSignalRankingItems(
  left: SignalRankingItem,
  right: SignalRankingItem,
  sort: SignalSort = defaultSignalSort
) {
  const leftValue = getSortValue(left, sort.key);
  const rightValue = getSortValue(right, sort.key);

  if (leftValue === undefined && rightValue !== undefined) {
    return 1;
  }
  if (leftValue !== undefined && rightValue === undefined) {
    return -1;
  }

  if (leftValue !== undefined && rightValue !== undefined && leftValue !== rightValue) {
    if (typeof leftValue === "string" && typeof rightValue === "string") {
      const companyDifference = leftValue.localeCompare(rightValue);
      return sort.direction === "asc" ? companyDifference : -companyDifference;
    }
    return sort.direction === "asc"
      ? Number(leftValue) - Number(rightValue)
      : Number(rightValue) - Number(leftValue);
  }

  const updateDifference =
    (right.stockSignal?.computedAt ?? 0) - (left.stockSignal?.computedAt ?? 0);
  if (updateDifference !== 0) {
    return updateDifference;
  }

  return left.ticker.localeCompare(right.ticker);
}

export function rankSignalItems<T extends SignalRankingItem>(
  items: T[],
  selectedList: string,
  sort: SignalSort = defaultSignalSort
) {
  return items
    .filter((item) => selectedList === "All" || item.listName === selectedList)
    .slice()
    .sort((left, right) => compareSignalRankingItems(left, right, sort)) as T[];
}
