# Plan: give the tuner a running start (H-014)

Written in plain English, like [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md). Nothing
has been built yet — this is the proposal to approve before we start.

---

## The problem, in one picture

Every few months the strategy re-tunes itself. Today, each re-tune starts
**completely from scratch**: the optimizer throws a handful of random guesses at
the wall, keeps the best, and calls that the new rulebook.

```
Quarter 1:  random guesses -> settles on  EMA 52 / stop 10.7%
Quarter 2:  random guesses -> settles on  EMA 45 / stop 13.3%     (unrelated to Q1)
Quarter 3:  random guesses -> settles on  EMA  7 / stop  9.5%     (unrelated to Q2)
```

Two separate problems come out of this, and one idea fixes both.

### Problem 1 — the answers jump around, so every transition is a lurch

Look at the real schedule from the sweep we just ran: the short EMA went
**52 → 45 → 7**. That is not the market changing its mind that violently; it is
the optimizer landing somewhere different each time it rolls the dice. Every one
of those jumps is a transition the strategy has to absorb — the exact thing you
asked to smooth.

### Problem 2 — the answers are so unstable we can't measure anything

This is what killed the grandfather A/B (H-013). Re-running the *same*
configuration with a different random starting point moved the result by up to
**12.6 percentage points**, while the effect we were trying to measure was worth
about **1.4**. The measurement noise was 6–9× bigger than the thing being
measured, so the test simply could not answer the question.

You correctly identified the cause: population 4 / generations 2 is far too
small a search to land in the same place twice.

---

## The idea: start from last quarter's answer

Instead of starting each re-tune from random guesses, **start it from the
parameters that were already working**, and let the optimizer improve on them.

```
Quarter 1:  random guesses      -> EMA 52 / stop 10.7%
Quarter 2:  start from Q1's answer, improve -> EMA 50 / stop 11.2%
Quarter 3:  start from Q2's answer, improve -> EMA 48 / stop 11.0%
```

An analogy: today we re-hire a consultant every quarter who has never seen the
business before and has one afternoon to form an opinion. Warm-starting is
keeping the same consultant, who begins each quarter with last quarter's plan
and adjusts it.

### Why this fixes both problems at once

- **Smaller transitions.** The new rulebook is a refinement of the old one
  rather than an unrelated draw, so there is far less to absorb at each
  boundary. This is smoothing at the *source* — it makes the jump smaller,
  rather than cushioning the landing afterwards.
- **A readable measurement.** If the tuner stops landing somewhere different
  every time, the seed-to-seed noise shrinks, and effects worth ~1 point
  become visible instead of being drowned out.

That second point is why I recommend doing this **before** the higher-budget
grandfather retest rather than after: it may make that retest readable at a
much smaller (and much faster) search budget.

---

## The one real risk, and how we handle it

**The risk is anchoring** — if we always start from last quarter's answer, the
strategy could get stuck defending an old idea long after the market has moved
on. That would defeat the entire purpose of re-tuning.

**The safeguard:** only *part* of the optimizer's starting line-up comes from
last quarter. The rest stays random, so a genuinely better and quite different
answer can still win. We will make that fraction a dial (default: roughly half),
and one of the things we measure is whether the tuner still moves when the
market genuinely changes.

A second, smaller consideration: with warm-starting, each quarter depends on the
one before it, so a run becomes a connected chain rather than independent
windows. This is normal for walk-forward testing and does not affect
reproducibility — the chosen parameters are still recorded window by window, so
any past run can still be replayed exactly.

---

## What gets built

1. **A new option, off by default** — `--ga-warm-start` with a companion dial
   for what fraction of the starting line-up is inherited. Default off means
   every existing run and every past result is completely unaffected.
2. **The plumbing you already have, reused.** It gets recorded in the run
   history, becomes part of the sweep's "have I run this already?" identity so
   an A/B never confuses itself, and replays exactly — the same treatment the
   transition policy got.
3. **Tests** proving that the inherited parameters actually reach the optimizer,
   that the random portion is still random, and that switching the option off
   reproduces today's behaviour exactly.

Rough size: about 40 lines of real logic plus tests. Small.

---

## How we will know whether it worked

Success is **not** "returns went up". This change is about stability, and we
should judge it on stability. Three checks, decided in advance:

| Question | How we measure it | What counts as success |
|---|---|---|
| Did the tuner get more stable? | Re-run one configuration under several different random starting points and look at the spread of results | Spread shrinks **materially** from today's 9–12.6 points |
| Did the transitions get smaller? | `param_jump_distance`, already recorded for every window | Average jump falls from today's ~0.11 |
| Did we break anything? | Excess return vs buy & hold across the same 8-pair grid | Not meaningfully worse than today |
| Is it still adapting? | Do the parameters still move when the market shifts? | Parameters are not frozen across all windows |

If stability improves but returns are unchanged, **that is still a win** — it
buys us the ability to measure everything else we want to test, including
grandfathering.

---

## Suggested order of work

1. Build warm-start behind the flag, with tests. *(short)*
2. Quick stability check on Microsoft: one configuration, several random
   starting points, warm-start on vs off. This answers "did the noise shrink?"
   cheaply, before committing to any long sweep. *(~1 hour of compute)*
3. **Decision point.** If the noise shrank, run the grandfather retest at a
   higher search budget — now with a decent chance of a readable answer. If it
   did not shrink, we have learned the budget must go up regardless, and we
   raise it.
4. Write the results up as H-014.

You had no preference on sequencing, so this is my recommendation: step 2 is
deliberately a cheap checkpoint, so we find out whether this works before paying
for a multi-hour sweep.

---

## What this plan deliberately does not do

- It does not change any default. Every existing result stands.
- It does not touch the no-leverage rule.
- It does not replace grandfathering — that option stays exactly as it is, still
  awaiting its higher-budget retest.
- It does not attempt the other smoothing ideas (blending rules over several
  days, only switching when the new rules are clearly better, staggered
  sub-portfolios). Those remain on the table for later.
