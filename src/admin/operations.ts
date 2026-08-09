export type AdminTarget = "development" | "production";

export type AdminOperationId =
  | "syncTicker"
  | "syncFinancials"
  | "generateAiReport"
  | "testLlmProviders"
  | "refreshTickerSignals"
  | "refreshUniverseSignals"
  | "refreshPortfolios";

export type AdminOperation = {
  id: AdminOperationId;
  label: string;
  description: string;
  functionName: string;
  requiresTicker: boolean;
  tone: "market" | "ai" | "signals" | "portfolio";
  showInJobs?: boolean;
};

export const productionConfirmation = "PRODUCTION";

export const adminOperations: readonly AdminOperation[] = [
  {
    id: "syncTicker",
    label: "Sync market data",
    description:
      "Refresh the quote, chart, news, fundamentals, and saved research snapshot for one ticker.",
    functionName: "marketData:syncTicker",
    requiresTicker: true,
    tone: "market",
  },
  {
    id: "syncFinancials",
    label: "Refresh financials",
    description:
      "Refresh and validate the stored financial statements for one ticker.",
    functionName: "marketData:syncFinancials",
    requiresTicker: true,
    tone: "market",
  },
  {
    id: "generateAiReport",
    label: "Generate AI report",
    description:
      "Generate and save the AI report, investment thesis, and five workflow AI notes in sequence.",
    functionName: "aiResearch:generateReport",
    requiresTicker: true,
    tone: "ai",
  },
  {
    id: "testLlmProviders",
    label: "Test LLM providers",
    description: "Test the saved primary and fallback provider connections.",
    functionName: "aiResearch:testProviders",
    requiresTicker: false,
    tone: "ai",
    showInJobs: false,
  },
  {
    id: "refreshTickerSignals",
    label: "Refresh ticker signals",
    description:
      "Download current price history and recalculate the saved signal for one ticker.",
    functionName: "signals:refreshTicker",
    requiresTicker: true,
    tone: "signals",
  },
  {
    id: "refreshUniverseSignals",
    label: "Refresh all signals",
    description:
      "Queue a background refresh and recalculation for the current stock universe.",
    functionName: "signals:refreshUniverse",
    requiresTicker: false,
    tone: "signals",
  },
  {
    id: "refreshPortfolios",
    label: "Refresh portfolios",
    description:
      "Refresh valuations and snapshots for every active portfolio.",
    functionName: "portfolios:refreshAllActive",
    requiresTicker: false,
    tone: "portfolio",
  },
] as const;

export type LocalAdminRequest = {
  operation: AdminOperationId;
  target: AdminTarget;
  ticker?: string;
  confirmation?: string;
};

export type ValidatedAdminRequest = {
  operation: AdminOperation;
  target: AdminTarget;
  args: { ticker: string } | Record<string, never>;
};

const normalizeTicker = (value: unknown) => {
  if (typeof value !== "string") {
    throw new Error("Enter a ticker symbol.");
  }

  const ticker = value.trim().toUpperCase();
  if (!/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(ticker)) {
    throw new Error("Ticker symbols may contain only letters, numbers, dots, and hyphens.");
  }
  return ticker;
};

export function validateAdminRequest(value: unknown): ValidatedAdminRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid admin request.");
  }

  const request = value as Partial<LocalAdminRequest>;
  const operation = adminOperations.find((item) => item.id === request.operation);
  if (!operation) {
    throw new Error("That admin operation is not allowed.");
  }

  if (request.target !== "development" && request.target !== "production") {
    throw new Error("Choose a valid Convex deployment target.");
  }

  if (
    request.target === "production" &&
    request.confirmation !== productionConfirmation
  ) {
    throw new Error(`Type ${productionConfirmation} to run against the public production data.`);
  }

  return {
    operation,
    target: request.target,
    args: operation.requiresTicker ? { ticker: normalizeTicker(request.ticker) } : {},
  };
}

export function convexRunArguments(request: ValidatedAdminRequest) {
  return [
    "run",
    request.operation.functionName,
    JSON.stringify(request.args),
    "--deployment",
    request.target === "production" ? "prod" : "dev",
    "--typecheck",
    "disable",
    "--codegen",
    "disable",
  ];
}
