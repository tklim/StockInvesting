import { v } from "convex/values";
import {
  internalMutation,
  internalQuery,
  mutation,
  query,
  type MutationCtx,
} from "./_generated/server";

const usageStatusValidator = v.union(
  v.literal("success"),
  v.literal("error"),
  v.literal("fallback")
);

const dateKeyFor = (timestamp: number) => new Date(timestamp).toISOString().slice(0, 10);

const redactSensitiveText = (value?: string) =>
  value
    ?.replace(/(api key(?: as)?\s+)[a-z0-9_-]+/gi, "$1[redacted]")
    .replace(/([?&](?:apikey|token)=)[^&\s]+/gi, "$1[redacted]");

const dataSourceEventArgs = {
  service: v.string(),
  operation: v.string(),
  status: usageStatusValidator,
  provider: v.string(),
  fallbackProvider: v.optional(v.string()),
  ticker: v.optional(v.string()),
  message: v.optional(v.string()),
  requestUrl: v.optional(v.string()),
  requestedAt: v.optional(v.number()),
  calledAt: v.optional(v.number()),
};

const recordEvent = async (
  ctx: MutationCtx,
  args: {
    service: string;
    operation: string;
    status: "success" | "error" | "fallback";
    provider: string;
    fallbackProvider?: string;
    ticker?: string;
    message?: string;
    requestUrl?: string;
    requestedAt?: number;
    calledAt?: number;
  }
) => {
  const calledAt = args.calledAt ?? Date.now();
  const dateKey = dateKeyFor(calledAt);
  const service = args.service.trim();
  const provider = args.provider.trim();
  const message = redactSensitiveText(args.message?.trim());
  const requestUrl = redactSensitiveText(args.requestUrl?.trim());

  await ctx.db.insert("dataSourceEvents", {
    service,
    operation: args.operation.trim(),
    status: args.status,
    provider,
    fallbackProvider: args.fallbackProvider?.trim() || undefined,
    ticker: args.ticker?.trim().toUpperCase() || undefined,
    message: message || undefined,
    requestUrl: requestUrl || undefined,
    requestedAt: args.requestedAt,
    dateKey,
    calledAt,
  });

  const usage = await ctx.db
    .query("dailyApiUsage")
    .withIndex("by_service_and_dateKey", (q) =>
      q.eq("service", service).eq("dateKey", dateKey)
    )
    .unique();

  const nextCounts = {
    count: (usage?.count ?? 0) + 1,
    successCount: (usage?.successCount ?? 0) + (args.status === "success" ? 1 : 0),
    errorCount: (usage?.errorCount ?? 0) + (args.status === "error" ? 1 : 0),
    fallbackCount: (usage?.fallbackCount ?? 0) + (args.status === "fallback" ? 1 : 0),
  };

  const usageDoc = {
    service,
    dateKey,
    ...nextCounts,
    lastStatus: args.status,
    lastProvider: provider,
    lastFallbackProvider: args.fallbackProvider?.trim() || undefined,
    lastMessage: message || undefined,
    lastRequestUrl: requestUrl || undefined,
    lastRequestedAt: args.requestedAt,
    lastCalledAt: calledAt,
  };

  if (usage) {
    await ctx.db.patch(usage._id, usageDoc);
  } else {
    await ctx.db.insert("dailyApiUsage", usageDoc);
  }

  return true;
};

export const recordClientEvent = mutation({
  args: dataSourceEventArgs,
  handler: async (ctx, args) => {
    return await recordEvent(ctx, args);
  },
});

export const recordInternalEvent = internalMutation({
  args: dataSourceEventArgs,
  handler: async (ctx, args) => {
    return await recordEvent(ctx, args);
  },
});

export const healthDashboard = query({
  args: { dateKey: v.optional(v.string()) },
  handler: async (ctx, args) => {
    const dateKey = args.dateKey ?? dateKeyFor(Date.now());
    const [usage, events] = await Promise.all([
      ctx.db
        .query("dailyApiUsage")
        .withIndex("by_dateKey", (q) => q.eq("dateKey", dateKey))
        .take(50),
      ctx.db
        .query("dataSourceEvents")
        .withIndex("by_calledAt")
        .order("desc")
        .take(25),
    ]);

    return {
      dateKey,
      usage,
      events,
    };
  },
});

export const usageForServices = internalQuery({
  args: {
    dateKey: v.string(),
    services: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    return await Promise.all(
      args.services.map(async (service) => {
        const usage = await ctx.db
          .query("dailyApiUsage")
          .withIndex("by_service_and_dateKey", (q) =>
            q.eq("service", service).eq("dateKey", args.dateKey)
          )
          .unique();

        return {
          service,
          usage,
        };
      })
    );
  },
});

export const redactStoredSecrets = internalMutation({
  args: {},
  handler: async (ctx) => {
    const [events, usageRows] = await Promise.all([
      ctx.db.query("dataSourceEvents").take(500),
      ctx.db.query("dailyApiUsage").take(100),
    ]);
    let updated = 0;

    for (const event of events) {
      const message = redactSensitiveText(event.message);
      const requestUrl = redactSensitiveText(event.requestUrl);
      if (message !== event.message || requestUrl !== event.requestUrl) {
        await ctx.db.patch(event._id, { message, requestUrl });
        updated += 1;
      }
    }
    for (const usage of usageRows) {
      const lastMessage = redactSensitiveText(usage.lastMessage);
      const lastRequestUrl = redactSensitiveText(usage.lastRequestUrl);
      if (
        lastMessage !== usage.lastMessage ||
        lastRequestUrl !== usage.lastRequestUrl
      ) {
        await ctx.db.patch(usage._id, { lastMessage, lastRequestUrl });
        updated += 1;
      }
    }

    return { updated };
  },
});
