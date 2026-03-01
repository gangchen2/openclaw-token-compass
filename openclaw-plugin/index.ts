import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

type PluginConfig = {
  binPath?: string;
  dbPath?: string;
};

const pluginDir = path.dirname(fileURLToPath(import.meta.url));

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function maybePathLike(value: string): boolean {
  return value.includes("/") || value.includes("\\") || value.includes(":");
}

function fileExists(p: string): boolean {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

function unique(items: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    if (!item) {
      continue;
    }
    if (seen.has(item)) {
      continue;
    }
    seen.add(item);
    out.push(item);
  }
  return out;
}

function candidateBinaries(config: PluginConfig): string[] {
  const fromEnv = process.env.TOKEN_COMPASS_BIN;
  const fromConfig = config.binPath;

  const localVenvInRepo = path.resolve(pluginDir, "..", ".venv", "bin", "openclaw-token-compass");
  const localVenvInWorkspace = path.resolve(pluginDir, "..", "..", ".venv", "bin", "openclaw-token-compass");

  const candidates = [
    isNonEmptyString(fromEnv) ? fromEnv.trim() : "",
    isNonEmptyString(fromConfig) ? fromConfig.trim() : "",
    "openclaw-token-compass",
    "openclaw-token",
    localVenvInRepo,
    localVenvInWorkspace,
  ];

  return unique(candidates);
}

function resolveBinary(config: PluginConfig): string {
  const candidates = candidateBinaries(config);
  for (const candidate of candidates) {
    if (!maybePathLike(candidate)) {
      return candidate;
    }
    if (fileExists(candidate)) {
      return candidate;
    }
  }

  return "openclaw-token-compass";
}

function resolveDbPath(config: PluginConfig): string {
  if (isNonEmptyString(process.env.TOKEN_COMPASS_DB)) {
    return process.env.TOKEN_COMPASS_DB.trim();
  }
  if (isNonEmptyString(config.dbPath)) {
    return config.dbPath.trim();
  }
  return path.join(os.homedir(), ".openclaw", "token_compass.db");
}

function runCommand(bin: string, args: string[]): string {
  const result = spawnSync(bin, args, { encoding: "utf8" });
  if (result.error) {
    throw new Error(`Failed to run ${bin}: ${String(result.error.message || result.error)}`);
  }

  if ((result.status ?? 1) !== 0) {
    const details = `${result.stdout || ""}\n${result.stderr || ""}`.trim();
    throw new Error(`${bin} ${args.join(" ")} failed: ${details || `exit ${result.status}`}`);
  }

  return (result.stdout || "").trim() || "OK";
}

function runCompass(config: PluginConfig, command: string, args: string[]): string {
  const bin = resolveBinary(config);
  const dbPath = resolveDbPath(config);

  runCommand(bin, ["init-db", "--db", dbPath]);

  const dbCommands = new Set(["estimate", "record", "stats", "init-db"]);
  const fullArgs = [command, ...args];
  if (dbCommands.has(command) && !fullArgs.includes("--db")) {
    fullArgs.push("--db", dbPath);
  }

  return runCommand(bin, fullArgs);
}

function asPath(params: Record<string, unknown>, key: string, required = false): string {
  const value = params[key];
  if (!isNonEmptyString(value)) {
    if (required) {
      throw new Error(`${key} is required`);
    }
    return "";
  }
  return value.trim();
}

function asOptional(params: Record<string, unknown>, key: string): string {
  const value = params[key];
  return isNonEmptyString(value) ? value.trim() : "";
}

function toTextResult(text: string, details?: Record<string, unknown>) {
  return {
    content: [{ type: "text", text }],
    ...(details ? { details } : {}),
  };
}

export default function register(api: any) {
  const pluginConfig = (api?.pluginConfig ?? {}) as PluginConfig;

  api.registerTool(
    {
      name: "token_compass_estimate",
      description: "Estimate token usage for an OpenClaw workflow before execution.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          workflow_path: { type: "string" },
          out_path: { type: "string" },
          provider: { type: "string" },
          db_path: { type: "string" },
        },
        required: ["workflow_path"],
      },
      async execute(_id: string, params: Record<string, unknown>) {
        const workflowPath = asPath(params, "workflow_path", true);
        const outPath = asOptional(params, "out_path");
        const provider = asOptional(params, "provider");
        const dbPathOverride = asOptional(params, "db_path");

        const args: string[] = ["--workflow", workflowPath];
        if (outPath) {
          args.push("--out", outPath);
        }
        if (provider) {
          args.push("--provider", provider);
        }
        if (dbPathOverride) {
          args.push("--db", dbPathOverride);
        }

        const output = runCompass(pluginConfig, "estimate", args);
        return toTextResult(output, { workflow_path: workflowPath, out_path: outPath || undefined });
      },
    },
    { optional: true },
  );

  api.registerTool(
    {
      name: "token_compass_extract_actual",
      description: "Extract actual token usage JSON from OpenClaw logs.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          log_path: { type: "string" },
          out_path: { type: "string" },
          run_id: { type: "string" },
          project: { type: "string" },
          provider: { type: "string" },
          default_model: { type: "string" },
        },
        required: ["log_path", "out_path"],
      },
      async execute(_id: string, params: Record<string, unknown>) {
        const logPath = asPath(params, "log_path", true);
        const outPath = asPath(params, "out_path", true);
        const runId = asOptional(params, "run_id");
        const project = asOptional(params, "project");
        const provider = asOptional(params, "provider");
        const defaultModel = asOptional(params, "default_model");

        const args: string[] = ["--log", logPath, "--out", outPath];
        if (runId) {
          args.push("--run-id", runId);
        }
        if (project) {
          args.push("--project", project);
        }
        if (provider) {
          args.push("--provider", provider);
        }
        if (defaultModel) {
          args.push("--default-model", defaultModel);
        }

        const output = runCompass(pluginConfig, "extract-actual", args);
        return toTextResult(output, { log_path: logPath, out_path: outPath });
      },
    },
    { optional: true },
  );

  api.registerTool(
    {
      name: "token_compass_record",
      description: "Record actual usage, calibrate estimates, and print error percentages.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          actual_path: { type: "string" },
          estimate_path: { type: "string" },
          provider: { type: "string" },
          db_path: { type: "string" },
        },
        required: ["actual_path"],
      },
      async execute(_id: string, params: Record<string, unknown>) {
        const actualPath = asPath(params, "actual_path", true);
        const estimatePath = asOptional(params, "estimate_path");
        const provider = asOptional(params, "provider");
        const dbPathOverride = asOptional(params, "db_path");

        const args: string[] = ["--actual", actualPath];
        if (estimatePath) {
          args.push("--estimate", estimatePath);
        }
        if (provider) {
          args.push("--provider", provider);
        }
        if (dbPathOverride) {
          args.push("--db", dbPathOverride);
        }

        const output = runCompass(pluginConfig, "record", args);
        return toTextResult(output, { actual_path: actualPath, estimate_path: estimatePath || undefined });
      },
    },
    { optional: true },
  );

  api.registerTool(
    {
      name: "token_compass_stats",
      description: "Show provider-aware calibration statistics.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          db_path: { type: "string" },
        },
      },
      async execute(_id: string, params: Record<string, unknown>) {
        const dbPathOverride = asOptional(params, "db_path");
        const args: string[] = [];
        if (dbPathOverride) {
          args.push("--db", dbPathOverride);
        }

        const output = runCompass(pluginConfig, "stats", args);
        return toTextResult(output);
      },
    },
    { optional: true },
  );
}
