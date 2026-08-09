// @vitest-environment node
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

const projectFile = (relativePath: string) =>
  fileURLToPath(new URL(`../${relativePath}`, import.meta.url));

const readProjectFile = (relativePath: string) =>
  readFileSync(projectFile(relativePath), "utf8");

describe("public read-only surface", () => {
  test("Convex source exposes queries but no public writes or actions", () => {
    const convexDirectory = projectFile("convex");
    const source = readdirSync(convexDirectory)
      .filter((name) => name.endsWith(".ts") && !name.endsWith(".test.ts"))
      .map((name) => readFileSync(`${convexDirectory}/${name}`, "utf8"))
      .join("\n");

    expect(source).toMatch(/=\s*query\s*\(/);
    expect(source).not.toMatch(/=\s*mutation\s*\(/);
    expect(source).not.toMatch(/=\s*action\s*\(/);
  });

  test("browser code has no provider key or public write hooks", () => {
    const app = readProjectFile("src/App.tsx");
    const portfolio = readProjectFile("src/MultiPortfolioView.tsx");
    const browserSource = `${app}\n${portfolio}`;

    expect(browserSource).not.toMatch(/useMutation|useAction/);
    expect(browserSource).not.toMatch(/VITE_[A-Z0-9_]*API_KEY/);
    expect(browserSource).not.toContain("api.twelvedata.com");
    expect(app).toContain("readOnly");
    expect(app).toContain("https://tklim.github.io/StockInvesting/");
  });

  test("frontend uses anonymous Convex and Vercel builds the Vite site", () => {
    const main = readProjectFile("src/main.tsx");
    const vercel = JSON.parse(readProjectFile("vercel.json")) as {
      framework?: string;
      outputDirectory?: string;
    };

    expect(main).toContain("ConvexProvider");
    expect(main).not.toContain("ConvexAuthProvider");
    expect(vercel).toMatchObject({ framework: "vite", outputDirectory: "dist" });
  });

  test("local LLM settings stay out of the public entry and secrets use Convex env", () => {
    const publicMain = readProjectFile("src/main.tsx");
    const adminPlugin = readProjectFile("local-admin/plugin.ts");
    const convexEnv = readProjectFile("local-admin/convexEnv.ts");
    const aiResearch = readProjectFile("convex/aiResearch.ts");

    expect(publicMain).not.toContain("admin/main");
    expect(adminPlugin).toContain('apply: "serve"');
    expect(convexEnv).toContain("child.stdin.end");
    expect(aiResearch).toContain("OPENAI_FALLBACK_API_KEY");
    expect(aiResearch).toContain("internalAction");
  });
});
