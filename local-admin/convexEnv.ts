import { spawn } from "node:child_process";
import { stripVTControlCharacters } from "node:util";
import {
  llmEnvironmentNames,
  type LlmSettingsSaveRequest,
  type LlmSettingsStatus,
} from "../src/admin/llmSettings";
import type { AdminTarget } from "../src/admin/operations";

const maxOutputBytes = 1024 * 1024;

const deploymentReference = (target: AdminTarget) =>
  target === "production" ? "prod" : "dev";

const runCli = (
  convexCliPath: string,
  args: string[],
  stdinValue?: string,
) =>
  new Promise<{ stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(process.execPath, [convexCliPath, ...args], {
      cwd: process.cwd(),
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let outputBytes = 0;
    const timer = setTimeout(() => child.kill(), 60_000);

    const collect = (target: Buffer[]) => (chunk: Buffer) => {
      outputBytes += chunk.length;
      if (outputBytes > maxOutputBytes) {
        child.kill();
        return;
      }
      target.push(chunk);
    };
    child.stdout.on("data", collect(stdout));
    child.stderr.on("data", collect(stderr));
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const result = {
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      };
      if (outputBytes > maxOutputBytes) {
        reject(new Error("Convex environment command returned too much output."));
      } else if (code !== 0) {
        reject(new Error(result.stderr || result.stdout || "Convex environment command failed."));
      } else {
        resolve(result);
      }
    });

    child.stdin.end(stdinValue === undefined ? undefined : `${stdinValue}\n`);
  });

const listEnvironment = async (convexCliPath: string, target: AdminTarget) => {
  const { stdout } = await runCli(convexCliPath, [
    "env",
    "list",
    "--deployment",
    deploymentReference(target),
  ]);
  const values = new Map<string, string>();
  for (const rawLine of stripVTControlCharacters(stdout).split(/\r?\n/)) {
    const separator = rawLine.indexOf("=");
    if (separator <= 0) continue;
    values.set(rawLine.slice(0, separator).trim(), rawLine.slice(separator + 1));
  }
  return values;
};

export const readLlmSettingsStatus = async (
  convexCliPath: string,
  target: AdminTarget,
): Promise<LlmSettingsStatus> => {
  const values = await listEnvironment(convexCliPath, target);
  const primary = llmEnvironmentNames.primary;
  const fallback = llmEnvironmentNames.fallback;
  const fallbackKeyConfigured = Boolean(values.get(fallback.apiKey));
  return {
    target,
    primary: {
      keyConfigured: Boolean(values.get(primary.apiKey)),
      baseUrl: values.get(primary.baseUrl) || "https://api.openai.com/v1",
      model: values.get(primary.model) || "gpt-5-mini",
    },
    fallback: {
      enabled:
        fallbackKeyConfigured ||
        Boolean(values.get(fallback.baseUrl)) ||
        Boolean(values.get(fallback.model)),
      keyConfigured: fallbackKeyConfigured,
      baseUrl: values.get(fallback.baseUrl) || "https://openrouter.ai/api/v1",
      model: values.get(fallback.model) || "",
    },
  };
};

const setEnvironmentValue = async (
  convexCliPath: string,
  target: AdminTarget,
  name: string,
  value: string,
) => {
  await runCli(
    convexCliPath,
    ["env", "set", name, "--deployment", deploymentReference(target)],
    value,
  );
};

const removeEnvironmentValue = async (
  convexCliPath: string,
  target: AdminTarget,
  name: string,
) => {
  await runCli(convexCliPath, [
    "env",
    "remove",
    name,
    "--deployment",
    deploymentReference(target),
  ]);
};

export const saveLlmSettings = async (
  convexCliPath: string,
  request: LlmSettingsSaveRequest,
) => {
  const existing = await listEnvironment(convexCliPath, request.target);
  const primary = llmEnvironmentNames.primary;
  const fallback = llmEnvironmentNames.fallback;

  if (!request.primary.apiKey && !existing.get(primary.apiKey)) {
    throw new Error("Enter a primary API key before saving.");
  }
  if (
    request.fallbackEnabled &&
    !request.fallback.apiKey &&
    !existing.get(fallback.apiKey)
  ) {
    throw new Error("Enter a fallback API key before enabling fallback.");
  }

  if (request.primary.apiKey) {
    await setEnvironmentValue(
      convexCliPath,
      request.target,
      primary.apiKey,
      request.primary.apiKey,
    );
  }
  await setEnvironmentValue(
    convexCliPath,
    request.target,
    primary.baseUrl,
    request.primary.baseUrl,
  );
  await setEnvironmentValue(
    convexCliPath,
    request.target,
    primary.model,
    request.primary.model,
  );

  if (request.fallbackEnabled) {
    if (request.fallback.apiKey) {
      await setEnvironmentValue(
        convexCliPath,
        request.target,
        fallback.apiKey,
        request.fallback.apiKey,
      );
    }
    await setEnvironmentValue(
      convexCliPath,
      request.target,
      fallback.baseUrl,
      request.fallback.baseUrl,
    );
    await setEnvironmentValue(
      convexCliPath,
      request.target,
      fallback.model,
      request.fallback.model,
    );
  } else {
    await removeEnvironmentValue(convexCliPath, request.target, fallback.apiKey);
    await removeEnvironmentValue(convexCliPath, request.target, fallback.baseUrl);
    await removeEnvironmentValue(convexCliPath, request.target, fallback.model);
  }

  return await readLlmSettingsStatus(convexCliPath, request.target);
};
