import { describe, expect, test, vi } from "vitest";
import { runAiNotesWorkflow } from "./aiNotesWorkflow";

describe("AI notes prerequisite workflow", () => {
  test("runs report, thesis, and notes in order with fresh results", async () => {
    const calls: string[] = [];
    const report = { generatedAt: 2, summary: "Fresh report" };
    const thesis = { updatedAt: 3, summary: "Fresh thesis" };
    const refreshReport = vi.fn(async () => {
      calls.push("report");
      return report;
    });
    const proposeThesis = vi.fn(async (receivedReport: typeof report) => {
      calls.push("thesis");
      expect(receivedReport).toBe(report);
      return thesis;
    });
    const generateNotes = vi.fn(
      async (context: { report: typeof report; thesis: typeof thesis }) => {
        calls.push("notes");
        expect(context).toEqual({ report, thesis });
        return 4;
      }
    );

    const result = await runAiNotesWorkflow({
      refreshReport,
      proposeThesis,
      generateNotes,
    });

    expect(calls).toEqual(["report", "thesis", "notes"]);
    expect(result).toBe(4);
  });

  test("stops before thesis and notes when report refresh fails", async () => {
    const proposeThesis = vi.fn();
    const generateNotes = vi.fn();

    await expect(
      runAiNotesWorkflow({
        refreshReport: async () => {
          throw new Error("Report failed");
        },
        proposeThesis,
        generateNotes,
      })
    ).rejects.toThrow("Report failed");

    expect(proposeThesis).not.toHaveBeenCalled();
    expect(generateNotes).not.toHaveBeenCalled();
  });

  test("stops before notes when thesis proposal fails", async () => {
    const generateNotes = vi.fn();

    await expect(
      runAiNotesWorkflow({
        refreshReport: async () => ({ summary: "Fresh report" }),
        proposeThesis: async () => {
          throw new Error("Thesis failed");
        },
        generateNotes,
      })
    ).rejects.toThrow("Thesis failed");

    expect(generateNotes).not.toHaveBeenCalled();
  });
});
