export type AiNotesWorkflowStage = "report" | "thesis" | "notes";

export async function runAiNotesWorkflow<Report, Thesis, Result>({
  refreshReport,
  proposeThesis,
  generateNotes,
  onStage,
}: {
  refreshReport: () => Promise<Report>;
  proposeThesis: (report: Report) => Promise<Thesis>;
  generateNotes: (context: { report: Report; thesis: Thesis }) => Promise<Result>;
  onStage?: (stage: AiNotesWorkflowStage) => void;
}) {
  onStage?.("report");
  const report = await refreshReport();

  onStage?.("thesis");
  const thesis = await proposeThesis(report);

  onStage?.("notes");
  return await generateNotes({ report, thesis });
}
