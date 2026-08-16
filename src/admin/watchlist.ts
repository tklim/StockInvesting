import type { AdminTarget } from "./operations";

export type WatchlistTicker = {
  ticker: string;
  listName: string;
  companyName?: string;
};

export type WatchlistStatus = WatchlistTicker & {
  marketDataAt: number | null;
  financialsAt: number | null;
  aiReportAt: number | null;
  thesisAt: number | null;
  aiNotesAt: number | null;
  signalsAt: number | null;
};

export type WatchlistSortKey =
  | "ticker"
  | "listName"
  | "marketDataAt"
  | "financialsAt"
  | "aiReportAt"
  | "thesisAt"
  | "aiNotesAt"
  | "signalsAt";

export type WatchlistSortDirection = "ascending" | "descending";

const tickerPattern = /^[A-Z0-9][A-Z0-9.-]{0,14}$/;

export const validateWatchlistRequest = (value: unknown): { target: AdminTarget } => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid watchlist request.");
  }

  const target = (value as Record<string, unknown>).target;
  if (target !== "development" && target !== "production") {
    throw new Error("Select a valid Convex target.");
  }

  return { target };
};

export const normalizeWatchlistTickers = (value: unknown): WatchlistTicker[] => {
  if (!Array.isArray(value)) {
    throw new Error("Convex returned an invalid watchlist response.");
  }

  const byTicker = new Map<string, WatchlistTicker>();
  for (const row of value) {
    if (!row || typeof row !== "object" || Array.isArray(row)) continue;
    const item = row as Record<string, unknown>;
    const ticker = typeof item.ticker === "string" ? item.ticker.trim().toUpperCase() : "";
    if (!tickerPattern.test(ticker)) continue;

    const listName =
      typeof item.listName === "string" && item.listName.trim()
        ? item.listName.trim().slice(0, 120)
        : "Watchlist";
    const stock =
      item.stock && typeof item.stock === "object" && !Array.isArray(item.stock)
        ? (item.stock as Record<string, unknown>)
        : undefined;
    const rawCompanyName =
      typeof item.companyName === "string"
        ? item.companyName
        : typeof stock?.companyName === "string"
          ? stock.companyName
          : undefined;
    const companyName =
      rawCompanyName && rawCompanyName.trim() ? rawCompanyName.trim().slice(0, 160) : undefined;

    if (!byTicker.has(ticker)) {
      byTicker.set(ticker, { ticker, listName, companyName });
    }
  }

  return [...byTicker.values()].sort(
    (left, right) =>
      left.listName.localeCompare(right.listName) || left.ticker.localeCompare(right.ticker),
  );
};

const normalizeTimestamp = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

export const normalizeWatchlistStatuses = (value: unknown): WatchlistStatus[] => {
  if (!Array.isArray(value)) {
    throw new Error("Convex returned an invalid watchlist status response.");
  }

  const byTicker = new Map<string, WatchlistStatus>();
  for (const row of value) {
    if (!row || typeof row !== "object" || Array.isArray(row)) continue;
    const item = row as Record<string, unknown>;
    const ticker = typeof item.ticker === "string" ? item.ticker.trim().toUpperCase() : "";
    if (!tickerPattern.test(ticker) || byTicker.has(ticker)) continue;
    const listName =
      typeof item.listName === "string" && item.listName.trim()
        ? item.listName.trim().slice(0, 120)
        : "Watchlist";
    const companyName =
      typeof item.companyName === "string" && item.companyName.trim()
        ? item.companyName.trim().slice(0, 160)
        : undefined;

    byTicker.set(ticker, {
      ticker,
      listName,
      companyName,
      marketDataAt: normalizeTimestamp(item.marketDataAt),
      financialsAt: normalizeTimestamp(item.financialsAt),
      aiReportAt: normalizeTimestamp(item.aiReportAt),
      thesisAt: normalizeTimestamp(item.thesisAt),
      aiNotesAt: normalizeTimestamp(item.aiNotesAt),
      signalsAt: normalizeTimestamp(item.signalsAt),
    });
  }

  return [...byTicker.values()].sort(
    (left, right) =>
      left.listName.localeCompare(right.listName) || left.ticker.localeCompare(right.ticker),
  );
};

export const sortWatchlistStatuses = (
  rows: readonly WatchlistStatus[],
  key: WatchlistSortKey,
  direction: WatchlistSortDirection,
) => {
  const multiplier = direction === "ascending" ? 1 : -1;
  return [...rows].sort((left, right) => {
    if (key === "ticker" || key === "listName") {
      const comparison = left[key].localeCompare(right[key]);
      return comparison === 0 ? left.ticker.localeCompare(right.ticker) : comparison * multiplier;
    }

    const leftTimestamp = left[key];
    const rightTimestamp = right[key];
    if (leftTimestamp === null || rightTimestamp === null) {
      if (leftTimestamp === rightTimestamp) return left.ticker.localeCompare(right.ticker);
      return leftTimestamp === null ? 1 : -1;
    }

    const comparison = leftTimestamp - rightTimestamp;
    return comparison === 0 ? left.ticker.localeCompare(right.ticker) : comparison * multiplier;
  });
};
