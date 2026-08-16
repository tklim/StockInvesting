import { execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";
import { promisify, stripVTControlCharacters } from "node:util";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin, ViteDevServer } from "vite";
import {
  type AdminTarget,
  convexRunArguments,
  validateAdminRequest,
} from "../src/admin/operations";
import {
  validateSettingsReadRequest,
  validateSettingsSaveRequest,
} from "../src/admin/llmSettings";
import {
  readLlmSettingsStatus,
  saveLlmSettings,
} from "./convexEnv";
import {
  normalizeWatchlistTickers,
  validateWatchlistRequest,
} from "../src/admin/watchlist";
import {
  managementFunctionName,
  validateManagementRequest,
} from "../src/admin/management";

const execFileAsync = promisify(execFile);
const maxRequestBytes = 16 * 1024;
const maxOutputCharacters = 80_000;

const adminHtml = (token: string) => `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="local-admin-token" content="${token}" />
    <meta name="robots" content="noindex,nofollow" />
    <title>StockInvesting Local Admin</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/admin/main.tsx"></script>
  </body>
</html>`;

const isLoopbackAddress = (address?: string) =>
  address === "127.0.0.1" ||
  address === "::1" ||
  address === "::ffff:127.0.0.1";

const isLocalHost = (host?: string) => {
  if (!host) return false;
  const hostname = host.startsWith("[")
    ? host.slice(1, host.indexOf("]"))
    : host.split(":", 1)[0];
  return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1";
};

const isAllowedOrigin = (origin: string | undefined, host: string | undefined) => {
  if (!origin || !host || !isLocalHost(host)) return false;
  try {
    const url = new URL(origin);
    return (url.protocol === "http:" || url.protocol === "https:") && url.host === host;
  } catch {
    return false;
  }
};

const sendJson = (
  res: ServerResponse<IncomingMessage>,
  status: number,
  body: Record<string, unknown>,
) => {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.end(JSON.stringify(body));
};

const readJsonBody = async (req: IncomingMessage) => {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > maxRequestBytes) {
      throw new Error("Admin request is too large.");
    }
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
};

const redactOutput = (value: string) =>
  value
    .replace(/(api[_-]?key|authorization|token)(["']?\s*[:=]\s*["']?)([^\s,"'}]+)/gi, "$1$2[redacted]")
    .replace(/(Bearer\s+)[^\s,"'}]+/gi, "$1[redacted]")
    .slice(0, maxOutputCharacters);

const workflowResultFromOutput = (value: string) => {
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return undefined;
    const result = parsed as {
      ticker?: unknown;
      status?: unknown;
      stages?: unknown;
    };
    if (
      typeof result.ticker !== "string" ||
      (result.status !== "complete" && result.status !== "partial" && result.status !== "failed") ||
      !Array.isArray(result.stages)
    ) {
      return undefined;
    }
    const stages = result.stages.flatMap((stage) => {
      if (!stage || typeof stage !== "object" || Array.isArray(stage)) return [];
      const item = stage as Record<string, unknown>;
      if (
        (item.stage !== "report" && item.stage !== "thesis" && item.stage !== "notes") ||
        (item.status !== "completed" && item.status !== "failed" && item.status !== "skipped")
      ) {
        return [];
      }
      return [{
        stage: item.stage,
        status: item.status,
        provider: typeof item.provider === "string" ? redactOutput(item.provider) : undefined,
        model: typeof item.model === "string" ? redactOutput(item.model) : undefined,
        generatedAt: typeof item.generatedAt === "number" ? item.generatedAt : undefined,
        createdNotes: typeof item.createdNotes === "number" ? item.createdNotes : undefined,
        replacedNotes: typeof item.replacedNotes === "number" ? item.replacedNotes : undefined,
        error: typeof item.error === "string" ? redactOutput(item.error) : undefined,
      }];
    });
    return stages.length === 3 ? { ticker: result.ticker, status: result.status, stages } : undefined;
  } catch {
    return undefined;
  }
};

type JsonRecord = Record<string, unknown>;

const asRecord = (value: unknown): JsonRecord | undefined =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : undefined;

const asTimestamp = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const deploymentForTarget = (target: AdminTarget) =>
  target === "production" ? "prod" : "dev";

const isMissingConvexFunction = (error: unknown) => {
  const candidate = error as Error & { stdout?: string; stderr?: string };
  return (candidate.stderr || candidate.stdout || candidate.message || "").includes(
    "Could not find function",
  );
};

const runWatchlistQuery = async (
  convexCliPath: string,
  target: AdminTarget,
  functionName: string,
  args: Record<string, unknown>,
) => {
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      convexCliPath,
      "run",
      functionName,
      JSON.stringify(args),
      "--deployment",
      deploymentForTarget(target),
      "--typecheck",
      "disable",
      "--codegen",
      "disable",
    ],
    {
      cwd: process.cwd(),
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      timeout: 60_000,
      windowsHide: true,
    },
  );
  return JSON.parse(stripVTControlCharacters(stdout).trim()) as unknown;
};

const readManagementData = async (convexCliPath: string, target: AdminTarget, portfolioId?: string) => {
  const [watchlists, tickers, portfolios] = await Promise.all([
    runWatchlistQuery(convexCliPath, target, "stocks:watchlists", {}),
    runWatchlistQuery(convexCliPath, target, "stocks:portfolio", {}),
    runWatchlistQuery(convexCliPath, target, "portfolios:list", { includeArchived: true } as never),
  ]);
  const dashboard = portfolioId
    ? await runWatchlistQuery(convexCliPath, target, "portfolios:getDashboard", { portfolioId } as never)
    : null;
  return { watchlists, tickers, portfolios, dashboard };
};

const mapWithConcurrency = async <T, R>(
  values: readonly T[],
  limit: number,
  mapper: (value: T) => Promise<R>,
) => {
  const results: R[] = new Array(values.length);
  let nextIndex = 0;
  const worker = async () => {
    while (nextIndex < values.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await mapper(values[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, values.length) }, worker));
  return results;
};

const fallbackWatchlistStatuses = async (convexCliPath: string, target: AdminTarget) => {
  const portfolio = await runWatchlistQuery(convexCliPath, target, "stocks:portfolio", {});
  if (!Array.isArray(portfolio)) {
    throw new Error("Convex returned an invalid watchlist response.");
  }

  const statuses = await mapWithConcurrency(portfolio, 4, async (entry) => {
    const saved = asRecord(entry);
    const ticker = typeof saved?.ticker === "string" ? saved.ticker.trim().toUpperCase() : "";
    if (!ticker) return undefined;

    const savedStock = asRecord(saved?.stock);
    const savedSignal = asRecord(saved?.stockSignal);
    let research: JsonRecord | undefined;
    try {
      research = asRecord(
        await runWatchlistQuery(convexCliPath, target, "stocks:researchBundle", { ticker }),
      );
    } catch {
      // Keep the saved-stock timestamps visible if a single research bundle cannot be read.
    }

    const stock = asRecord(research?.stock) ?? savedStock;
    const snapshots = Array.isArray(research?.snapshots) ? research.snapshots : [];
    const latestSnapshot = asRecord(snapshots[0]);
    const financialReport = asRecord(research?.financialReport);
    const aiReport = asRecord(research?.aiReport);
    const investmentThesis = asRecord(research?.investmentThesis);
    const signal = asRecord(research?.stockSignal) ?? savedSignal;
    const notes = Array.isArray(research?.notes) ? research.notes : [];
    const latestAdminNote = notes
      .map(asRecord)
      .find((note) => note?.generatedBy === "admin-ai-workflow");

    return {
      ticker,
      listName: typeof saved?.listName === "string" ? saved.listName : "Watchlist",
      companyName: typeof stock?.companyName === "string" ? stock.companyName : undefined,
      marketDataAt: asTimestamp(latestSnapshot?.syncedAt) ?? asTimestamp(stock?.updatedAt),
      financialsAt: asTimestamp(financialReport?.updatedAt),
      aiReportAt: asTimestamp(aiReport?.generatedAt),
      thesisAt: asTimestamp(investmentThesis?.updatedAt),
      aiNotesAt: asTimestamp(latestAdminNote?.createdAt),
      signalsAt: asTimestamp(signal?.computedAt),
    };
  });

  return statuses.filter((status): status is NonNullable<typeof status> => Boolean(status));
};

const handleAdminPage = async (
  server: ViteDevServer,
  req: IncomingMessage,
  res: ServerResponse<IncomingMessage>,
  token: string,
) => {
  if (req.method !== "GET") {
    res.statusCode = 405;
    res.end("Method not allowed");
    return;
  }

  const host = req.headers.host;
  if (!isLoopbackAddress(req.socket.remoteAddress) || !isLocalHost(host)) {
    res.statusCode = 404;
    res.end("Not found");
    return;
  }

  const html = await server.transformIndexHtml("/admin", adminHtml(token));
  res.statusCode = 200;
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("Referrer-Policy", "no-referrer");
  res.end(html);
};

export function localAdminPlugin(): Plugin {
  const token = randomBytes(32).toString("hex");
  const convexCliPath = resolve(process.cwd(), "node_modules/convex/dist/cli.bundle.cjs");
  let operationRunning = false;

  return {
    name: "stockinvesting-local-admin",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/admin", async (req, res) => {
        await handleAdminPage(server, req, res, token);
      });

      server.middlewares.use("/__local_admin/run", async (req, res) => {
        const host = req.headers.host;
        if (
          !isLoopbackAddress(req.socket.remoteAddress) ||
          !isLocalHost(host) ||
          !isAllowedOrigin(req.headers.origin, host)
        ) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }
        if (operationRunning) {
          sendJson(res, 409, { error: "Another admin operation is already running." });
          return;
        }

        try {
          const request = validateAdminRequest(await readJsonBody(req));
          operationRunning = true;
          const startedAt = Date.now();
          const { stdout, stderr } = await execFileAsync(
            process.execPath,
            [convexCliPath, ...convexRunArguments(request)],
            {
              cwd: process.cwd(),
              encoding: "utf8",
              maxBuffer: 1024 * 1024,
              timeout: 10 * 60 * 1000,
              windowsHide: true,
            },
          );
          sendJson(res, 200, {
            ok: true,
            operation: request.operation.id,
            target: request.target,
            durationMs: Date.now() - startedAt,
            output: redactOutput(stdout || stderr || "Operation completed."),
            workflow:
              request.operation.id === "generateAiReport"
                ? workflowResultFromOutput(stdout)
                : undefined,
          });
        } catch (error) {
          const candidate = error as Error & { stdout?: string; stderr?: string };
          sendJson(res, 400, {
            error: redactOutput(candidate.stderr || candidate.stdout || candidate.message),
          });
        } finally {
          operationRunning = false;
        }
      });

      server.middlewares.use("/__local_admin/watchlist", async (req, res) => {
        const host = req.headers.host;
        if (
          !isLoopbackAddress(req.socket.remoteAddress) ||
          !isLocalHost(host) ||
          !isAllowedOrigin(req.headers.origin, host)
        ) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }

        try {
          const { target } = validateWatchlistRequest(await readJsonBody(req));
          const rows = await runWatchlistQuery(convexCliPath, target, "stocks:portfolio", {});
          sendJson(res, 200, {
            ok: true,
            target,
            tickers: normalizeWatchlistTickers(rows),
          });
        } catch (error) {
          const candidate = error as Error & { stdout?: string; stderr?: string };
          sendJson(res, 400, {
            error: redactOutput(
              candidate.stderr || candidate.stdout || candidate.message || "Unable to load watchlist.",
            ),
          });
        }
      });

      server.middlewares.use("/__local_admin/watchlist-status", async (req, res) => {
        const host = req.headers.host;
        if (
          !isLoopbackAddress(req.socket.remoteAddress) ||
          !isLocalHost(host) ||
          !isAllowedOrigin(req.headers.origin, host)
        ) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }

        try {
          const { target } = validateWatchlistRequest(await readJsonBody(req));
          let rows: unknown;
          try {
            rows = await runWatchlistQuery(
              convexCliPath,
              target,
              "stocks:adminWatchlistStatus",
              {},
            );
          } catch (error) {
            if (!isMissingConvexFunction(error)) throw error;
            rows = await fallbackWatchlistStatuses(convexCliPath, target);
          }
          sendJson(res, 200, {
            ok: true,
            target,
            tickers: normalizeWatchlistTickers(rows),
            statuses: rows,
          });
        } catch (error) {
          const candidate = error as Error & { stdout?: string; stderr?: string };
          sendJson(res, 400, {
            error: redactOutput(
              candidate.stderr || candidate.stdout || candidate.message || "Unable to load watchlist status.",
            ),
          });
        }
      });

      server.middlewares.use("/__local_admin/manage/read", async (req, res) => {
        const host = req.headers.host;
        if (!isLoopbackAddress(req.socket.remoteAddress) || !isLocalHost(host) || !isAllowedOrigin(req.headers.origin, host)) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }
        try {
          const body = await readJsonBody(req);
          const { target } = validateWatchlistRequest(body);
          const record = asRecord(body);
          const portfolioId = typeof record?.portfolioId === "string" ? record.portfolioId : undefined;
          sendJson(res, 200, { ok: true, ...(await readManagementData(convexCliPath, target, portfolioId)) });
        } catch (error) {
          const candidate = error as Error & { stdout?: string; stderr?: string };
          sendJson(res, 400, { error: redactOutput(candidate.stderr || candidate.stdout || candidate.message || "Unable to load management data.") });
        }
      });

      server.middlewares.use("/__local_admin/manage/write", async (req, res) => {
        const host = req.headers.host;
        if (!isLoopbackAddress(req.socket.remoteAddress) || !isLocalHost(host) || !isAllowedOrigin(req.headers.origin, host)) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }
        if (operationRunning) {
          sendJson(res, 409, { error: "Another admin operation is already running." });
          return;
        }
        try {
          const request = validateManagementRequest(await readJsonBody(req));
          operationRunning = true;
          const { stdout, stderr } = await execFileAsync(
            process.execPath,
            [convexCliPath, "run", managementFunctionName[request.action], JSON.stringify(request.args), "--deployment", deploymentForTarget(request.target), "--typecheck", "disable", "--codegen", "disable"],
            { cwd: process.cwd(), encoding: "utf8", maxBuffer: 1024 * 1024, timeout: 60_000, windowsHide: true },
          );
          sendJson(res, 200, { ok: true, output: redactOutput(stdout || stderr || "Saved.") });
        } catch (error) {
          const candidate = error as Error & { stdout?: string; stderr?: string };
          sendJson(res, 400, { error: redactOutput(candidate.stderr || candidate.stdout || candidate.message || "Unable to save changes.") });
        } finally {
          operationRunning = false;
        }
      });

      server.middlewares.use("/__local_admin/manage/search-symbols", async (req, res) => {
        const host = req.headers.host;
        if (!isLoopbackAddress(req.socket.remoteAddress) || !isLocalHost(host) || !isAllowedOrigin(req.headers.origin, host)) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }
        try {
          const body = asRecord(await readJsonBody(req));
          const { target } = validateWatchlistRequest(body);
          const query = typeof body?.query === "string" ? body.query.trim() : "";
          if (query.length < 2 || query.length > 80) {
            throw new Error("Enter at least two characters to search symbols.");
          }
          const results = await runWatchlistQuery(
            convexCliPath,
            target,
            "marketData:searchSymbols",
            { query },
          );
          sendJson(res, 200, { ok: true, results });
        } catch (error) {
          const candidate = error as Error & { stdout?: string; stderr?: string };
          sendJson(res, 400, { error: redactOutput(candidate.stderr || candidate.stdout || candidate.message || "Unable to search symbols.") });
        }
      });

      server.middlewares.use("/__local_admin/llm-settings/read", async (req, res) => {
        const host = req.headers.host;
        if (
          !isLoopbackAddress(req.socket.remoteAddress) ||
          !isLocalHost(host) ||
          !isAllowedOrigin(req.headers.origin, host)
        ) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }
        try {
          const { target } = validateSettingsReadRequest(await readJsonBody(req));
          const settings = await readLlmSettingsStatus(convexCliPath, target);
          sendJson(res, 200, { ok: true, settings });
        } catch (error) {
          sendJson(res, 400, {
            error: redactOutput(error instanceof Error ? error.message : "Unable to read settings."),
          });
        }
      });

      server.middlewares.use("/__local_admin/llm-settings/save", async (req, res) => {
        const host = req.headers.host;
        if (
          !isLoopbackAddress(req.socket.remoteAddress) ||
          !isLocalHost(host) ||
          !isAllowedOrigin(req.headers.origin, host)
        ) {
          sendJson(res, 404, { error: "Not found" });
          return;
        }
        if (req.method !== "POST") {
          sendJson(res, 405, { error: "Method not allowed" });
          return;
        }
        if (req.headers["x-local-admin-token"] !== token) {
          sendJson(res, 403, { error: "Invalid local admin session." });
          return;
        }
        if (operationRunning) {
          sendJson(res, 409, { error: "Another admin operation is already running." });
          return;
        }
        try {
          const request = validateSettingsSaveRequest(await readJsonBody(req));
          operationRunning = true;
          const settings = await saveLlmSettings(convexCliPath, request);
          sendJson(res, 200, { ok: true, settings });
        } catch (error) {
          sendJson(res, 400, {
            error: redactOutput(error instanceof Error ? error.message : "Unable to save settings."),
          });
        } finally {
          operationRunning = false;
        }
      });
    },
  };
}
