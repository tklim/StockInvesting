import { describe, expect, test } from "vitest";
import {
  convexRunArguments,
  validateAdminRequest,
} from "./operations";

describe("local admin operation validation", () => {
  test("normalizes a ticker and targets the development deployment by default request", () => {
    const request = validateAdminRequest({
      operation: "syncTicker",
      target: "development",
      ticker: " brk.b ",
    });

    expect(request.args).toEqual({ ticker: "BRK.B" });
    expect(convexRunArguments(request)).toEqual([
      "run",
      "marketData:syncTicker",
      '{"ticker":"BRK.B"}',
      "--deployment",
      "dev",
      "--typecheck",
      "disable",
      "--codegen",
      "disable",
    ]);
  });

  test("allows production jobs without a typed confirmation", () => {
    const request = validateAdminRequest({
      operation: "generateAiReport",
      target: "production",
      ticker: "NVDA",
    });
    expect(convexRunArguments(request)).toContain("prod");
  });

  test("rejects arbitrary functions and shell-like ticker input", () => {
    expect(() =>
      validateAdminRequest({ operation: "stocks:deleteEverything", target: "development" }),
    ).toThrow("not allowed");
    expect(() =>
      validateAdminRequest({
        operation: "syncTicker",
        target: "development",
        ticker: "NVDA; whoami",
      }),
    ).toThrow("letters, numbers, dots, and hyphens");
  });

  test("passes no ticker argument to universe and portfolio operations", () => {
    const request = validateAdminRequest({
      operation: "refreshUniverseSignals",
      target: "development",
      ticker: "SHOULD-NOT-BE-FORWARDED",
    });
    expect(request.args).toEqual({});
  });

  test("allowlists the hidden LLM connection test without showing it as a job card", () => {
    const request = validateAdminRequest({
      operation: "testLlmProviders",
      target: "development",
    });
    expect(request.operation.functionName).toBe("aiResearch:testProviders");
    expect(request.operation.showInJobs).toBe(false);
  });
});
