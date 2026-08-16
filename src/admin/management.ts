import type { AdminTarget } from "./operations";

export type ManagementAction =
  | "createWatchlist"
  | "renameWatchlist"
  | "deleteWatchlist"
  | "saveTicker"
  | "removeTicker"
  | "createPortfolio"
  | "updatePortfolio"
  | "duplicatePortfolio"
  | "archivePortfolio"
  | "upsertHolding"
  | "removeHolding";

export type ManagementRequest = {
  action: ManagementAction;
  target: AdminTarget;
  args: Record<string, unknown>;
};

const tickerPattern = /^[A-Z0-9][A-Z0-9.-]{0,14}$/;

const requiredText = (value: unknown, label: string, maximum = 160) => {
  if (typeof value !== "string") throw new Error(`${label} is required.`);
  const text = value.trim();
  if (!text) throw new Error(`${label} is required.`);
  if (text.length > maximum) throw new Error(`${label} is too long.`);
  return text;
};

const optionalText = (value: unknown, maximum = 1_000) =>
  value === undefined ? undefined : requiredText(value, "Text", maximum);

const nonNegativeNumber = (value: unknown, label: string) => {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be a non-negative number.`);
  }
  return value;
};

const ticker = (value: unknown) => {
  const normalized = requiredText(value, "Ticker", 15).toUpperCase();
  if (!tickerPattern.test(normalized)) throw new Error("Enter a valid ticker symbol.");
  return normalized;
};

const target = (value: unknown): AdminTarget => {
  if (value !== "development" && value !== "production") {
    throw new Error("Choose a valid Convex target.");
  }
  return value;
};

export const validateManagementRequest = (value: unknown): ManagementRequest => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid management request.");
  }
  const request = value as Record<string, unknown>;
  const action = request.action;
  const args = request.args;
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    throw new Error("Invalid management action arguments.");
  }
  const input = args as Record<string, unknown>;
  const requestTarget = target(request.target);

  switch (action) {
    case "createWatchlist":
      return { action, target: requestTarget, args: { name: requiredText(input.name, "Watchlist name") } };
    case "renameWatchlist":
      return { action, target: requestTarget, args: { currentName: requiredText(input.currentName, "Current watchlist"), nextName: requiredText(input.nextName, "New watchlist name") } };
    case "deleteWatchlist":
      return { action, target: requestTarget, args: { name: requiredText(input.name, "Watchlist name"), ...(input.fallbackListName ? { fallbackListName: requiredText(input.fallbackListName, "Fallback watchlist") } : {}) } };
    case "saveTicker":
      return { action, target: requestTarget, args: { ticker: ticker(input.ticker), listName: requiredText(input.listName, "Watchlist") } };
    case "removeTicker":
      return { action, target: requestTarget, args: { ticker: ticker(input.ticker) } };
    case "createPortfolio": {
      const type = input.type;
      if (type !== "actual" && type !== "model") throw new Error("Choose a portfolio type.");
      const base = { name: requiredText(input.name, "Portfolio name"), type, description: optionalText(input.description), benchmarkTicker: ticker(input.benchmarkTicker ?? "SPY") };
      return { action, target: requestTarget, args: type === "model" ? { ...base, startingValue: nonNegativeNumber(input.startingValue, "Starting value") } : { ...base, cashBalance: nonNegativeNumber(input.cashBalance ?? 0, "Cash balance") } };
    }
    case "updatePortfolio":
      return { action, target: requestTarget, args: { portfolioId: requiredText(input.portfolioId, "Portfolio"), name: requiredText(input.name, "Portfolio name"), description: typeof input.description === "string" ? input.description.trim().slice(0, 1_000) : "", benchmarkTicker: ticker(input.benchmarkTicker), cashBalance: nonNegativeNumber(input.cashBalance, "Cash balance") } };
    case "duplicatePortfolio":
      return { action, target: requestTarget, args: { portfolioId: requiredText(input.portfolioId, "Portfolio"), name: requiredText(input.name, "New portfolio name") } };
    case "archivePortfolio":
      return { action, target: requestTarget, args: { portfolioId: requiredText(input.portfolioId, "Portfolio") } };
    case "upsertHolding":
      return { action, target: requestTarget, args: { portfolioId: requiredText(input.portfolioId, "Portfolio"), ticker: ticker(input.ticker), shares: nonNegativeNumber(input.shares, "Shares"), averageCost: nonNegativeNumber(input.averageCost, "Average cost"), targetAllocation: nonNegativeNumber(input.targetAllocation, "Target allocation"), notes: typeof input.notes === "string" ? input.notes.trim().slice(0, 1_000) : "" } };
    case "removeHolding":
      return { action, target: requestTarget, args: { portfolioId: requiredText(input.portfolioId, "Portfolio"), ticker: ticker(input.ticker) } };
    default:
      throw new Error("That management action is not allowed.");
  }
};

export const managementFunctionName: Record<ManagementAction, string> = {
  createWatchlist: "stocks:createWatchlist",
  renameWatchlist: "stocks:renameWatchlist",
  deleteWatchlist: "stocks:deleteWatchlist",
  saveTicker: "stocks:saveToPortfolio",
  removeTicker: "stocks:removeFromPortfolio",
  createPortfolio: "portfolios:create",
  updatePortfolio: "portfolios:update",
  duplicatePortfolio: "portfolios:duplicate",
  archivePortfolio: "portfolios:archive",
  upsertHolding: "portfolios:upsertHolding",
  removeHolding: "portfolios:removeHolding",
};
