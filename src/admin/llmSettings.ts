import {
  productionConfirmation,
  type AdminTarget,
} from "./operations";

export const llmEnvironmentNames = {
  primary: {
    apiKey: "OPENAI_API_KEY",
    baseUrl: "OPENAI_BASE_URL",
    model: "OPENAI_MODEL",
  },
  fallback: {
    apiKey: "OPENAI_FALLBACK_API_KEY",
    baseUrl: "OPENAI_FALLBACK_BASE_URL",
    model: "OPENAI_FALLBACK_MODEL",
  },
} as const;

export type LlmProviderSettings = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export type LlmSettingsSaveRequest = {
  target: AdminTarget;
  confirmation?: string;
  fallbackEnabled: boolean;
  primary: LlmProviderSettings;
  fallback: LlmProviderSettings;
};

export type LlmSettingsStatus = {
  target: AdminTarget;
  primary: {
    keyConfigured: boolean;
    baseUrl: string;
    model: string;
  };
  fallback: {
    enabled: boolean;
    keyConfigured: boolean;
    baseUrl: string;
    model: string;
  };
};

const validateTarget = (value: unknown): AdminTarget => {
  if (value !== "development" && value !== "production") {
    throw new Error("Choose a valid Convex deployment target.");
  }
  return value;
};

export function validateSettingsReadRequest(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid settings request.");
  }
  return { target: validateTarget((value as { target?: unknown }).target) };
}

const validateBaseUrl = (value: unknown, label: string) => {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} server URL is required.`);
  }
  const normalized = value.trim().replace(/\/+$/, "");
  if (normalized.length > 2048) {
    throw new Error(`${label} server URL is too long.`);
  }
  let url: URL;
  try {
    url = new URL(normalized);
  } catch {
    throw new Error(`${label} server URL is invalid.`);
  }
  if ((url.protocol !== "https:" && url.protocol !== "http:") || url.username || url.password) {
    throw new Error(`${label} server URL must be HTTP(S) and cannot contain credentials.`);
  }
  return normalized;
};

const validateModel = (value: unknown, label: string) => {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} model is required.`);
  }
  const model = value.trim();
  if (model.length > 200 || /\s/.test(model)) {
    throw new Error(`${label} model must be a single value of at most 200 characters.`);
  }
  return model;
};

const validateApiKey = (value: unknown) => {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value !== "string" || value.length > 8192 || !value.trim()) {
    throw new Error("API keys must be non-empty and at most 8192 characters.");
  }
  return value.trim();
};

export function validateSettingsSaveRequest(value: unknown): LlmSettingsSaveRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid settings request.");
  }
  const request = value as Partial<LlmSettingsSaveRequest>;
  const target = validateTarget(request.target);
  if (target === "production" && request.confirmation !== productionConfirmation) {
    throw new Error(`Type ${productionConfirmation} to change production settings.`);
  }
  if (!request.primary || typeof request.primary !== "object") {
    throw new Error("Primary provider settings are required.");
  }
  if (!request.fallback || typeof request.fallback !== "object") {
    throw new Error("Fallback provider settings are required.");
  }

  const fallbackEnabled = request.fallbackEnabled === true;
  return {
    target,
    confirmation: request.confirmation,
    fallbackEnabled,
    primary: {
      apiKey: validateApiKey(request.primary.apiKey),
      baseUrl: validateBaseUrl(request.primary.baseUrl, "Primary"),
      model: validateModel(request.primary.model, "Primary"),
    },
    fallback: {
      apiKey: validateApiKey(request.fallback.apiKey),
      baseUrl: fallbackEnabled
        ? validateBaseUrl(request.fallback.baseUrl, "Fallback")
        : "",
      model: fallbackEnabled
        ? validateModel(request.fallback.model, "Fallback")
        : "",
    },
  };
}
