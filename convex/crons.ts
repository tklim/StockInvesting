import { cronJobs } from "convex/server";
import { internal } from "./_generated/api";

const crons = cronJobs();

crons.cron(
  "weekday portfolio valuation",
  "30 22 * * 1-5",
  internal.portfolios.refreshAllActive,
  {}
);

export default crons;
