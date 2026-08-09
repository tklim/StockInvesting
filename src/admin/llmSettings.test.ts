import { describe, expect, test } from "vitest";
import {
  validateSettingsReadRequest,
  validateSettingsSaveRequest,
} from "./llmSettings";
import { productionConfirmation } from "./operations";

describe("local LLM settings validation", () => {
  test("accepts primary and fallback OpenAI-compatible providers", () => {
    const settings = validateSettingsSaveRequest({
      target: "development",
      fallbackEnabled: true,
      primary: {
        apiKey: "primary-secret",
        baseUrl: "https://api.openai.com/v1/",
        model: "gpt-5-mini",
      },
      fallback: {
        apiKey: "fallback-secret",
        baseUrl: "https://openrouter.ai/api/v1/",
        model: "anthropic/claude-sonnet-4",
      },
    });

    expect(settings.primary.baseUrl).toBe("https://api.openai.com/v1");
    expect(settings.fallback.baseUrl).toBe("https://openrouter.ai/api/v1");
    expect(settings.fallbackEnabled).toBe(true);
  });

  test("allows blank write-only keys so existing deployment secrets are preserved", () => {
    const settings = validateSettingsSaveRequest({
      target: "development",
      fallbackEnabled: false,
      primary: { apiKey: "", baseUrl: "http://127.0.0.1:11434/v1", model: "local-model" },
      fallback: { apiKey: "", baseUrl: "", model: "" },
    });
    expect(settings.primary.apiKey).toBe("");
    expect(settings.fallback).toEqual({ apiKey: "", baseUrl: "", model: "" });
  });

  test("requires production confirmation", () => {
    expect(() =>
      validateSettingsSaveRequest({
        target: "production",
        fallbackEnabled: false,
        primary: { apiKey: "key", baseUrl: "https://api.openai.com/v1", model: "gpt-5-mini" },
        fallback: { apiKey: "", baseUrl: "", model: "" },
      }),
    ).toThrow(`Type ${productionConfirmation}`);
  });

  test("rejects credential-bearing URLs and whitespace in model names", () => {
    expect(() =>
      validateSettingsSaveRequest({
        target: "development",
        fallbackEnabled: false,
        primary: { apiKey: "key", baseUrl: "https://user:pass@example.com/v1", model: "gpt-5-mini" },
        fallback: { apiKey: "", baseUrl: "", model: "" },
      }),
    ).toThrow("cannot contain credentials");
    expect(() =>
      validateSettingsSaveRequest({
        target: "development",
        fallbackEnabled: false,
        primary: { apiKey: "key", baseUrl: "https://example.com/v1", model: "bad model" },
        fallback: { apiKey: "", baseUrl: "", model: "" },
      }),
    ).toThrow("single value");
  });

  test("validates read targets without accepting arbitrary deployments", () => {
    expect(validateSettingsReadRequest({ target: "development" })).toEqual({
      target: "development",
    });
    expect(() => validateSettingsReadRequest({ target: "other-project" })).toThrow(
      "valid Convex deployment target",
    );
  });
});
