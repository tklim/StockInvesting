# Experiment Log — Executive Summary

A running, plain-English record of what we've tried to improve the automated
buy/sell strategy, what happened, and what we're testing next. Written for a
human reader, not a programmer. For the technical methodology, see
[OPTIMIZATION_LOOP.md](OPTIMIZATION_LOOP.md).

**Bottom line so far: we have not found a version of this strategy that
reliably beats simply buying and holding the stock — under a fair,
capital-matched comparison.** An earlier positive result (H-005/H-006, Apple)
was later disqualified because it beat the market only by investing *more* money
(leverage), which isn't a fair fight. See the rule note below.

> **Ground rule — DO NOT INVEST MORE than buy & hold.** The strategy is never
> allowed to put more money at risk than simply buying and holding would
> ($10k vs $10k). Winning by deploying $13.5k against a $10k benchmark isn't
> skill, it's just more chips on the table — especially here, where borrowing
> is treated as free. So any setting that "leans in" above normal size is
> disqualified from being called a winner. The only allowed edge is *timing*
> (holding cash at the right moments), never *leverage*. **This retroactively
> disqualifies the Apple result in H-005/H-006** — see H-007 for the fair
> re-test.

---

## H-001 — Try a more disciplined exit/re-entry rule

**Date:** 2026-07-23
**Stock:** Microsoft (MSFT)

**The idea:** Our strategy sells during a price drop and buys back in after a
rebound. We wondered if adding stricter rules — only sell/buy when the
underlying trend clearly confirms it — would help, since our data showed the
strategy tends to sit out a lot of the recovery after a drop (missing ~16-24%
of the upside on average).

**What we tested:** Ran the stricter version against the normal version,
12 times total, mixing different random starting conditions so the result
wasn't a fluke of one lucky run.

**What happened:** The stricter version was worse in 5 out of 6 comparisons.
It did cut the number of trades way down (from ~20-38 down to ~4-8) and
slightly reduced the worst-case loss, but it actually missed *more* of the
rebound than before (24% vs 16%), not less — because "wait for confirmation"
means waiting until after most of the recovery has already happened.

**Verdict: Rejected.** The stricter rule doesn't fix the problem it was meant
to fix.

---

## H-002 — Check if a promising result was just luck

**Date:** 2026-07-23
**Stock:** Microsoft (MSFT)

**The idea:** One configuration (MSFT, roughly the last 2 years, checked every
12 months) looked like a genuine winner in early testing. Before trusting it,
we needed to know: does it still work if we re-run it with different random
starting conditions? A result that only shows up under one specific random
seed isn't real — it's noise.

**What we tested:** Re-ran the same configuration 10 more times with fresh
random seeds, plus doubled the "search effort" the strategy uses to tune
itself, to see if the result holds up under more careful tuning too.

**What happened:** Every single run (10 out of 10, and 8 out of 8 when
combined with the earlier tests) beat buy-and-hold. That's the first time
any configuration has done that consistently across this whole project.

**The catch — this is not a clean win:**
- Buy-and-hold itself *lost* about 4.7% per year in this exact 2-year window
  (Microsoft's stock was down over this period). Our strategy also mostly
  lost money in absolute terms — it just lost *less*, by sitting out some of
  the decline.
- When we gave the strategy more effort to tune itself (which should make it
  smarter, not weaker), the advantage shrank by about half.
- So: this looks less like "the strategy is good at picking winners" and more
  like "holding cash helps when the stock is falling," which is closer to
  luck of timing than a repeatable edge.

**Verdict: Initially accepted as the best-known setup — but later overturned
by H-003 (see below).** At the time it was the strongest result we had, but we
did not trust it as a real strategy edge, and the follow-up test proved that
distrust correct.

---

## H-003 — Was the "win" real, or just one lucky time slice?

**Date:** 2026-07-23
**Stock:** Microsoft (MSFT)

**The idea:** H-002's win came from checking the strategy every 12 months over
one specific 2-year stretch. If it's a genuine edge, it shouldn't matter
whether we check every 12, 6, or 3 months — the strategy is the same. If the
win only appears at the 12-month setting, that proves it was an accident of how
that one time window happened to line up, not real skill.

**What we tested:** Re-ran the exact same MSFT setup, same 8 random seeds, but
checking every 3 months and every 6 months instead of every 12 — 16 more runs.

**What happened:** The win evaporated.

| How often we rechecked | How many of 8 beat buy-and-hold | Average edge |
|---|---|---|
| Every 12 months (the H-002 result) | 8 of 8 | +5.1% |
| Every 6 months | 5 of 8 | +1.9% |
| Every 3 months | 4 of 8 (a coin flip) | +1.4% |

Nothing changed except the recheck schedule, and the "reliable winner" turned
into a coin flip. For example, one seed went from +3.5% (12-month) to **-5.2%**
(3-month). The strategy also lost money in absolute terms at every setting.

**Verdict: Requires human review — and H-002 is downgraded to Rejected.** The
MSFT result was an accident of one particular time window, not a real edge.
We're back to square one: **no version of this strategy reliably beats simply
buying and holding.**

---

## H-004 — Is there ANY setting worth keeping? (portfolio-wide review)

**Date:** 2026-07-23
**Scope:** all 357 test runs collected so far, across 10 stocks

**The idea:** After three straight promising results dissolved under
stress-testing, rather than test another single setup, look across everything
we've collected and ask one blunt question: is there **any** stock or setting
where the strategy both (a) beats buy-and-hold, (b) actually makes money, and
(c) holds up across different time windows and random conditions — all at once?

**What we found:** No.

- About 1 run in 5 beats buy-and-hold, and about 1 in 8 also makes money in
  absolute terms — but these are scattered one-offs, not repeatable setups.
- When we require the same setup to work across at least 3 different random
  conditions, the *best* setup in the entire project (Microsoft, 12-month
  checks) succeeds only 38% of the time. Every other setup is worse.
- No stock-and-timeframe combination holds up across even two different recheck
  schedules. The moment we demand real robustness, every candidate disappears.

**Verdict: Requires human review — recommendation is to stop tuning.** Across
four experiments and 357 runs, there is no setting where this strategy reliably
beats buy-and-hold *and* makes money. Continuing to adjust its dials is
searching a space that appears to have no winning spot in it. That's not a
failure of the search — it's a genuine, useful finding about the strategy
itself.

**Suggested directions (a human decision):**
1. **Accept the negative result and stop.** "This indicator strategy doesn't
   beat buy-and-hold on big US stocks" is a real, effort-saving conclusion.
2. **Change the strategy itself**, not its settings — a different kind of
   signal, or a "when to be active at all" detector, since the one thing that
   reliably helped was holding cash during declines.
3. **Test on rougher markets** — the data we have (2021-2026 big tech) is
   mostly a calm bull market with no crash for a downside-protection strategy
   to protect against. Indices through 2008 or 2020 would be a fairer test.

---

## H-005 — Let the strategy invest a bit more aggressively

**Date:** 2026-07-23
**Stocks:** Apple (AAPL), Alphabet (GOOGL), Microsoft (MSFT)

**The idea:** Until now, every one of the 357 tests kept the strategy at "normal"
investment size — it could hold cash or be fully invested, but never more. In a
rising market that guarantees it lags buy-and-hold, because any time spent in
cash is upside it can never recover. The software has a setting that lets the
strategy lean in slightly harder (up to ~1.35x) when it's confident. We'd never
tried it. This directly targets higher returns.

**What happened — the best result the project has produced, but only for Apple:**

| Stock (and its trend) | Normal setting | Lean-in setting |
|---|---|---|
| **Apple** (rising +21%/yr) | lost to buy-and-hold, 0 of 3 | **beat buy-and-hold, 3 of 3**, +23.5%/yr, better risk-adjusted too |
| Alphabet (rising +39%/yr) | 2 of 3 | mixed, 2 of 3 (one bad blow-up) |
| Microsoft (falling -5%/yr) | 3 of 3 | 0 of 3 — leaning in made the losses worse |

- **On Apple this is a real, consistent win** — it beat the market on all three
  random conditions, actually made money (+23.5%/yr vs the old +7%/yr), and did
  so with better risk-adjusted returns, not just by taking on more risk.
- Importantly, it wasn't just "use more leverage in an up market" — the strategy
  actually held *slightly less* average market exposure than buy-and-hold, yet
  still beat it. That points to genuine timing skill on Apple, finally being put
  to use instead of wasted sitting in cash.
- **But it's not a cure-all.** On a falling stock (Microsoft) leaning in
  amplified the losses badly, and on Alphabet it added instability. The setting
  helps in a clear uptrend and hurts in a downtrend — which makes sense.
- The trade-off: leaning in raised the worst-case loss on every stock. Apple
  still came out ahead on risk-adjusted terms; the others didn't.

**Verdict: Refine and retest.** This is the most promising result so far and the
first to clear every bar at once on a stock — but only on Apple, and only tested
on one recheck schedule. The last time a result looked this good (H-002), it fell
apart when we changed the recheck schedule (H-003). So before celebrating, the
next step puts Apple through that exact same stress test.

---

## H-006 — Stress-testing the Apple result (the make-or-break check)

**Date:** 2026-07-23
**Stock:** Apple (AAPL), 42 new test runs

**The idea:** Put the promising Apple "lean-in" setting through the exact test
that broke the last false winner: different recheck schedules (every 3, 6, and
12 months) plus 5 more random conditions, for 8 total.

**What happened: it passed, for real this time — with an honest asterisk.**

- Unlike the earlier false alarm, where the SAME random condition flipped from
  a win to a big loss just by changing the recheck schedule, this result stayed
  essentially identical no matter how often we rechecked: same win rate (5 of
  8), same typical outcome, at 3-month, 6-month, and 12-month schedules alike.
  That is a genuinely different — and much more trustworthy — signature than
  the mirage we found in H-003.
- On the two metrics that matter most for "did this actually get better" —
  actual money made and risk-adjusted return — **the lean-in setting won every
  single one of 24 head-to-head comparisons.** Typical return jumped from about
  8%/yr to about 20%/yr; risk-adjusted return roughly doubled.
- The honest catch: it beats the market in about 6 of every 10 tries, not all
  of them. Two of the eight random conditions were consistently bad, and they
  get *worse* the less often we recheck — the opposite pattern from a lucky
  time-window, which points to "the search sometimes lands on a worse setup,"
  not "the whole thing was luck."
- We also spotted a likely cause: this setting still carries some of the same
  overly-cautious re-entry rule we already proved hurts (H-001). The bad
  outcomes may be where that rule is doing the most damage.

**Verdict: Accept as the new best-known setup — with a clearly logged
weakness to keep improving.** This is real, durable progress: it survived the
stress test the last "winner" failed, and it dominates the old setup on return
and risk-adjustment with no exceptions. But per the standing instruction to
keep pushing for higher, more consistent returns, we're not stopping — the
uneven win rate is the next thing to fix.

---

## H-007 — The fair rematch: same strategy, same $10k, no leaning in

**Date:** 2026-07-23
**Stock:** Apple (AAPL), 24 runs

**The idea:** Settle whether the Apple win was real skill or just the extra
money. We re-ran the *exact same* strategy with one thing forced to normal:
it could never invest more than buy-and-hold's $10k. Everything else identical.

**What happened: stripped of the extra money, the edge vanished.**

| Version (all timing the same) | Allowed to invest more? | Beat buy-and-hold |
|---|---|---|
| Normal size, plain strategy | No | 1 of 24 |
| **Normal size, "improved" strategy** | **No** | **2 of 24** |
| Lean-in strategy (H-005/H-006) | Yes (up to 1.35x) | 15 of 24 |

- The leaning-in, all by itself, was worth about **+9 percentage points of
  return per year** and helped in 22 of 24 cases. It — not the strategy logic —
  is what beat the market.
- Forced to the same $10k as buy-and-hold, the "improved" strategy wins just 2
  times in 24, no better than the plain version, and loses to the market ~95%
  of the time. **Your intuition was exactly right: it wasn't a fair game.**

**Verdict: Rejected. The Apple result is officially withdrawn.** Under the new
"don't invest more" rule it doesn't count, and now we've proven that even
setting the rule aside, there was no real skill underneath — only the leverage.
We're back to: no fair version of this strategy beats buying and holding on
these (calm, mostly-rising) stocks.

---

## H-008 — The fair strategy on 20 years, crashes and all

**Date:** 2026-07-23
**Stocks:** 5 large-caps over ~20 years

**The idea:** A strategy that sits in cash can only beat buy-and-hold if there's
a real crash to sit out. So we tested the fair (normal-size) strategy on ~20
years including the 2020 crash.

**What happened:** It lost on return every time (0 of 15), by about 9%/yr — even
with crashes present. Over a full cycle, the gains it gives up waiting to get
back in after a dip outweigh what it saves by dodging the dip. **But** it did
reliably reduce the worst-case loss: smaller peak-to-trough drops than
buy-and-hold in 14 of 15 runs (e.g. Apple 29% vs 44%).

**Verdict: Rejected for the returns goal.** Its one honest skill is smoothing
out the ride (lower drawdown), not making more money — and since we've barred
leverage, we can't convert that smoother ride into higher returns.

---

## H-009 — Teach the optimizer to not miss the rebound

**Date:** 2026-07-23
**Stocks:** Microsoft, Apple, Alphabet — tested one stock at a time

**The idea (from your steer):** The whole point is to dodge the short dips but
stay in the uptrend. We found the strategy's #1 weakness is *missing the bounce*
after it sells — it gets out for a dip and then sits out the recovery. It turns
out the optimizer was never actually told to care about this. So we switched on
a penalty for "missed rebound" and let it re-optimize each stock.

**What happened — it helped, but only where the stock is choppy, not smoothly
rising:**
- **Microsoft (roughly flat over the period): a real, fair improvement.** It
  missed less of the rebounds, traded less, and its return edge over
  buy-and-hold grew (and it actually made money instead of roughly breaking
  even) — across all 3 test conditions.
- **Apple & Alphabet (both strongly rising): no gain.** The penalty did what it
  was told — the strategy missed noticeably less upside — but it still couldn't
  beat simply holding, because these stocks rise so smoothly that any time spent
  out of the market during their quick dips costs more than the dips save.

**Verdict: Accept as an improvement for Microsoft (fair, no leverage); keep
digging for the rising stocks.** This is the first *fair* (normal-size) change
that genuinely improved a stock. It confirms your instinct that this is a
per-stock game: dip-dodging pays on choppy stocks, not on smooth rocket-ships.

---

## H-010 — Does a much harder search crack the rising stocks?

**Date:** 2026-07-23
**Stocks:** Apple, Alphabet

**The idea:** You asked us to turn up the optimizer's effort when results are
weak. So we re-ran Apple and Alphabet with a 10x more thorough (and ~10x slower)
search.

**What happened: it got *worse*, not better.** More search effort let the
optimizer fit each training stretch more tightly, and that tighter fit
generalized *worse* to the real out-of-sample test — a textbook case of
"overfitting." No setting came close to beating buy-and-hold.

**Verdict: The ceiling is real, not a search limitation.** For a smoothly-rising
stock, there simply is no dip-dodging setup that beats holding it — more compute
just finds a more elaborate way to overfit. (Useful side note: the "don't miss
the rebound" version still beat the plain version even here — it's the better
recipe, just not a miracle.)

---

## H-011 — Give it a real crash to dodge (the 2022 bear)

**Date:** 2026-07-23
**Stocks:** Meta, Nvidia, Tesla, Apple

**The idea:** Dodging dips can only pay if there's a big dip to dodge. So we
tested volatile, high-flying stocks over a longer window that includes the 2022
market crash.

**What happened: the opposite of the hope.** The higher-returning the stock, the
worse it did — Nvidia missed *162%* of upside after its exits and lost ~42%/yr
to buy-and-hold. These stocks crashed and then snapped back violently; the
strategy sold into the crash and then sat out the rocket-ship recovery.

**Verdict: Rejected — and it clinches the big picture.** Across all 11
experiments, one rule has never broken: **the stronger a stock's rise, the more
this dip-dodging strategy loses to simply holding it** — because in fast-rising
stocks the dips and their recoveries can't be separated. Dodging dips only pays
on choppy, flat, or falling stocks (like Microsoft), where there's little upside
to miss.

---

## Where we are now — focusing on what works

After 11 experiments the verdict is clear and consistent: at fair (normal) size,
this strategy **cannot** beat buy-and-hold on a strongly-rising stock, no matter
the settings, search effort, time window, or which rising stock we pick. Its one
genuine, fair edge is on **choppy or flat stocks**, where sidestepping declines
actually helps — Microsoft being the clear example.

**Your call: optimize the stocks where it works, instead of fighting the ones it
can't.** So we're now optimizing Microsoft hard — the best fair setup, tested
across time windows and 8 different random conditions for robustness. Honest
expectation: a solid, dependable edge over buy-and-hold, but a modest headline
return (Microsoft was roughly flat over these years, so "beating it" is a real
but not flashy result).

## What's next — H-012

**Status:** Running — deep Microsoft optimization for the most robust fair
(no-leverage) setup.

---

## H-013 — Stop the strategy from tripping over its own rule changes

**Date:** 2026-08-03 (updated same day with the full sweep)
**Stocks:** Microsoft (MSFT) 3-year file; an early check also covered the S&P
500 fund (SPY)

**The idea:** Every few months the strategy re-tunes itself to the latest
market — that's the point of it. But the switchover is abrupt: a position
bought under the *old* rules is suddenly judged by the *new* rules the morning
they take effect. If the new rules happen to be stricter, the strategy can sell
on day one even though the market didn't move at all — a trade caused by the
rule change itself, not by prices. We called these "phantom exits."

**What we built:** Two things, both kept as permanent tooling.

1. **Measurement.** Every run now records, for each switchover, whether an exit
   fired in the first days afterwards and whether it would also have fired
   under the old rules (`transition_report.csv` per run, summarized by
   `backtest/analysis/transitions.py`).
2. **A candidate fix — "grandfathering"** (`--transition-policy grandfather`):
   a position keeps the exit rules it was bought under until it is sold; only
   *new* purchases follow the new rules. Off by default.

**First look (one setting) was encouraging — and misleading.** On the single
1-year-lookback / 3-month-offset setting, grandfathering improved Microsoft's
excess return from −10.33% to −7.43% and Sharpe from 0.16 to 0.23. We wrote
that up as promising.

**Then we swept it properly:** 8 matched pairs (lookback 1Y/2Y × offset
3/6/9/12M), identical seed 999, identical tuned parameters, the only difference
being grandfathering on or off. Excess *annualized* return, grandfather minus
normal:

| lookback | offset | normal | grandfather | difference |
|---|---|---|---|---|
| 1Y | 3M | −4.98 | −3.56 | **+1.42** |
| 1Y | 6M | −14.21 | −12.93 | **+1.28** |
| 1Y | 9M | −9.79 | −10.47 | **−0.68** |
| 1Y | 12M | −7.70 | −8.38 | **−0.68** |
| 2Y | 3M | +20.89 | +20.89 | 0.00 |
| 2Y | 6M | +1.08 | +1.08 | 0.00 |
| 2Y | 9M | +20.89 | +20.89 | 0.00 |
| 2Y | 12M | +3.11 | +3.11 | 0.00 |

**Two better, two worse, four unchanged.** The first look had landed on the
single most favourable cell in the whole grid — exactly the mistake H-002 was
supposed to have taught us.

**What we learned anyway (the useful part):**

- **The original theory was wrong.** Across all 58 switchovers measured, the
  strict day-one phantom-exit counter fired **zero** times. Exits just after a
  switchover would have happened under the old rules too. The problem we set
  out to fix is not actually occurring on this data.
- **What grandfathering really does is hold positions longer.** Where it
  helped, it avoided being shaken out; where it hurt (9M and 12M), it stayed in
  a falling position longer — time invested rose ~2 points and the worst
  drawdown got *worse* (19.0% → 20.1%). That is a genuine trade-off, not noise.
- **Four "unchanged" rows are mostly not evidence.** The 2Y/12M run contains
  only *one* window, so there is no switchover at all and the setting cannot
  possibly matter. Only about half the grid meaningfully tests the mechanism.

**Why this is not a rejection — the tuning budget was too small to tell.** All
of these runs used a very light optimizer setting (population 4, generations 2).
At that budget the *same* configuration re-run under a different random seed
swings far more than the effect we were trying to measure:

| cell | seed-to-seed spread | policy effect |
|---|---|---|
| 1Y/3M | 9.02 points | 1.42 |
| 1Y/12M | 12.59 points | 0.68 |
| 2Y/3M | 0.04 points | 0.00 |

Where the tuning is unstable (the 1Y cells), the noise is **6–9× larger** than
the signal, so the A/B simply cannot resolve it. Where the tuning is stable
(the 2Y cells), the setting made no difference at all. Neither half of the grid
supports a conclusion in either direction.

**Verdict at this budget: Inconclusive.** The option stays in the code
(`--transition-policy`, default `none`), is recorded per run, replays exactly,
and is part of the sweep resume identity so an A/B never resumes off the other
policy's history. Retest at a higher tuning budget, where the noise floor is
small enough for a ~1-point effect to be visible.

**Practical notes for the retest:**
- A 3-year data file with a 3-year lookback leaves no out-of-sample period and
  returns a meaningless 0% — keep lookbacks below the file's span.
- Watch for one-day tail windows when the offset doesn't divide the test span
  evenly (2Y/3M ends with a 2026-07-30 → 2026-07-31 window).
- On the `generic` profile the long EMA barely affects trading decisions — the
  buy/sell logic keys off the short EMA and the drawdown threshold — so two
  runs with very different long EMAs can produce identical results.

---

### Second sweep — same grid, pop=6/gen=3 (2026-08-03)

Same 8-pair MSFT grid, same seed 999, budget raised from pop=4/gen=2 to
pop=6/gen=3. Transition policy was the only thing that changed between the two
runs of each pair — GA warm start (H-014, below) was off for both sides.

| lookback | offset | normal | grandfather | difference |
|---|---|---|---|---|
| 1Y | 3M | −2.45 | −0.99 | **+1.46** |
| 1Y | 6M | −10.93 | −9.61 | **+1.32** |
| 1Y | 9M | −14.12 | −14.12 | 0.00 |
| 1Y | 12M | −10.11 | −8.78 | **+1.33** |
| 2Y | 3M | −5.51 | −5.51 | 0.00 |
| 2Y | 6M | −5.36 | −5.36 | 0.00 |
| 2Y | 9M | −6.58 | −6.58 | 0.00 |
| 2Y | 12M | −8.63 | −8.63 | 0.00 |

**3 better, 5 unchanged, none worse.** That is a real shift from the first
sweep, where 2 of the 8 cells got *worse* under grandfathering (the 9M/12M
cells, where holding a losing position longer was the wrong call). Those
losses are gone at the higher budget. Zero phantom exits again, across 74
windows now measured at the 3-month offset alone — the original "accidental
trade right after the switch" theory keeps not happening.

**Still not enough to call it Accepted.** Only one seed (999) has been run at
this budget, so there is no seed-to-seed spread to compare the effect against
— we cannot yet tell "no losses at this budget" apart from "this seed happened
to avoid the losing draw." The first sweep's lesson stands: a pattern seen at
one seed is not evidence until it survives a few more.

**Verdict: Still Inconclusive, but trending toward Accepted.** Run 2-3 more
seeds at pop=6/gen=3 (or higher) before deciding. If the "no losses" pattern
holds, grandfathering becomes the default; if it doesn't, this settles back to
the pop=4 finding that the fair comparison is a wash.

---

## H-014 — Give the tuner a running start

**Date:** 2026-08-03 to 2026-08-04
**Stock:** Microsoft (MSFT), 3-year file
**Plan:** [WARM_START_PLAN.md](WARM_START_PLAN.md)

**The idea:** Every few months the strategy re-tunes from random guesses, so
consecutive quarters can land on unrelated settings — we watched the short EMA
go 52 → 45 → 7 on real data. That is both a source of abrupt transitions and
the reason H-013 was unmeasurable: the tuner was so unstable that re-running
the same test with a different random start moved the answer by more than the
effect we were trying to measure. "Warm starting" means each quarter begins
from last quarter's settings and improves on them, instead of starting over.

**How we judged it:** deliberately on **stability, not returns.** The plan set
the bar in advance: the spread between repeated runs of the same configuration
must shrink materially from the 9–12.6 points that made H-013 unreadable.

**What happened — it failed its own test.** Six runs of one configuration
(MSFT 1-year lookback, 3-month offset, larger tuning budget), differing only in
the random seed:

```
-14.17, -13.64, -13.44, -4.13, -2.28, -2.27
spread = 11.89 points
```

**11.89 points is inside the very range it was supposed to fix.** Warm starting
did not stabilise the tuner.

**Two things we learned that are worth more than the headline:**

- **The results are bimodal, not noisy.** Three runs land near −13.5, three
  near −2.9, and nothing in between. The tuner is choosing between two
  distinct answers depending on the seed. That also explains why warm starting
  cannot fix it: the *first* quarter has no previous settings to inherit, so it
  starts cold anyway, and warm starting then faithfully carries whichever
  answer it stumbled into through every quarter that follows. It preserves the
  first roll of the dice rather than damping it.
- **Steadier settings really do perform better.** Counting how many different
  short-EMA values each run used across its nine quarters, the correlation with
  return is strong and clear (rho = −0.90): runs that kept a steady setting did
  dramatically better than runs that thrashed. **The underlying instinct is
  right** — a settled strategy beats a thrashing one. What is wrong is the
  assumption that warm starting *reliably produces* a settled strategy. It does
  so only sometimes, decided by luck.

**A separate, clean comparison agrees.** On a smaller budget, with verified
identical data, warm start was worse in 6 of 8 grid cells (mean −2.70 points).

**Verdict: Rejected at these settings.** The option stays in the code
(`--ga-warm-start`, default off) and is recorded per run, but it is not the
route to a stable tuner. If revisited, the lever is inheriting a much smaller
share of the population (0.15–0.25 rather than 0.5) so the previous answer
biases the search instead of dominating it — and the first-quarter cold start
would still need solving.

**A methodology problem this exposed, now fixed.** Three separate comparisons
in this experiment were invalidated because the derived data slices
(`MSFT-3Y.csv`, `MSFT-5Y.csv`) are regenerated periodically and roll forward
silently — same filename, often the same end date, but a different start date
and row count, which shifts every window and moves the benchmark. In one case
buy & hold differed by 6.6 points between two runs of the "same" test. Runs now
record a **data fingerprint**, the sweep drivers refuse to treat an old-vintage
run as completed, and the analysis tools warn when pooled results span more
than one vintage.

---

## How to read "Verdict"

- **Accepted** — becomes the new reference point to beat, sometimes with
  caveats noted above.
- **Rejected** — didn't help, tried and ruled out, won't be retested without
  a new reason.
- **Inconclusive** — the test couldn't answer the question, usually because
  the measurement noise was larger than the effect being looked for. Different
  from Rejected: the idea is still open, it just needs a sharper test.
- **Requires human review** — result is ambiguous or conflicts with policy
  (e.g. relies on a single lucky trade); needs a person to decide before
  continuing.
