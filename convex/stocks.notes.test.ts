/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { internal } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

const workflowNotes = Array.from({ length: 5 }, (_, index) => ({
  title: `Fresh workflow note ${index + 1}`,
  body: `Fresh practical workflow note body ${index + 1}.`,
  tag: "AI Note",
}));

test("replacing admin workflow notes preserves manual and legacy notes", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    await ctx.db.insert("notes", {
      ticker: "TSM",
      title: "Manual note",
      body: "A user-authored research note.",
      tag: "Thesis",
      createdAt: 1,
    });
    await ctx.db.insert("notes", {
      ticker: "TSM",
      title: "Legacy generated note",
      body: "An older unmarked note.",
      tag: "AI Note",
      createdAt: 2,
    });
    for (const index of [1, 2]) {
      await ctx.db.insert("notes", {
        ticker: "TSM",
        title: `Old workflow note ${index}`,
        body: "This one may be replaced.",
        tag: "AI Note",
        generatedBy: "admin-ai-workflow",
        createdAt: index + 2,
      });
    }
  });

  const result = await t.mutation(internal.stocks.replaceAdminGeneratedNotes, {
    ticker: "tsm",
    notes: workflowNotes,
  });

  expect(result).toEqual({ replacedCount: 2, createdCount: 5 });
  const notes = await t.run(async (ctx) =>
    await ctx.db
      .query("notes")
      .withIndex("by_ticker", (q) => q.eq("ticker", "TSM"))
      .collect(),
  );
  expect(notes.map((note) => note.title)).toContain("Manual note");
  expect(notes.map((note) => note.title)).toContain("Legacy generated note");
  expect(notes.map((note) => note.title)).not.toContain("Old workflow note 1");
  expect(notes.filter((note) => note.generatedBy === "admin-ai-workflow")).toHaveLength(5);
});
