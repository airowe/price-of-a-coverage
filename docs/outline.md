# Results audit and writing outline

For Adam. Numbers below come from `uv run coverage-price reproduce` on 10 November 2026
(10 games, about 16 seconds, tables identical in a fresh copy of the project), after
the fixes from the independent code review (section 7).
The README and video must be in your own words; this file gives you the numbers and
a structure, not prose to paste.

All distances are feet of nearest-defender distance. Ranges are 95%, from resampling
whole games. "+1 s" means one second after the screen, measured against 0.6 s before it.
A window stops when the possession's scoring chance ends.

## 1. Audit: package against the provisional numbers in the spec

| Quantity | Spec (throwaway scripts) | Package | Moved? |
|---|---|---|---|
| Team-average space at +1 s, show | +0.93 | +0.99 [0.88, 1.12], n=526 | No |
| Team-average space at +1 s, drop | +0.18 | +0.31 [0.14, 0.43], n=549 | No (+0.13) |
| Show minus drop, team average, +1 s | 0.54 to 0.98 | 0.68 [0.52, 0.85] | No |
| Games with the same sign | 10 of 10 | 10 of 10 | No |
| Handler, under minus over, +1 s | about +1.36 | +1.32 [0.98, 1.65], 10 of 10 games | No |
| No-action control, team average, +1 s | −0.17 | −0.22 [−0.45, +0.01], n=98 | No |
| Season points per pick, screener vs show | 0.306 | 0.306 (9,498 picks) | No |
| Season points per pick, screener vs drop | 0.216 | 0.217 (8,218 picks) | No |
| Season points per pick, handler vs under | 0.770 | 0.770 (3,302 picks) | No |
| Season points per pick, handler vs over | 0.699 | 0.699 (14,501 picks) | No |

Nothing moved by more than 0.2 ft or 0.02 points. The small shifts come from the
eligibility gate (tracking error of 3 ft or less) and from stopping each window at the
end of the chance, neither of which the throwaway scripts had.

## 2. The three decisive checks

**Is drop deeper than show in the tracking? Yes.**

| SkillCorner label | Picks | Median depth below the screen |
|---|---|---|
| drop (`soft`) | 652 | 5.4 ft |
| switch | 213 | 3.2 ft |
| show | 607 | 2.4 ft |

So `soft` is drop. Note that "show" here is a defender about 2 ft below the screen
on average, not a hard hedge above it: 93% of shows are still below the screen
(99% of drops are).

**Does space created fall as the defender plays deeper? Yes.**

| Screener's defender depth | Picks | Team-average space at +1 s |
|---|---|---|
| Above the screen (< 0 ft) | 56 | +0.92 [0.60, 1.24] |
| 0–3 ft | 447 | +1.02 [0.90, 1.16] |
| 3–6 ft | 492 | +0.49 [0.35, 0.64] |
| Deep (> 6 ft) | 289 | +0.05 [−0.16, 0.20] |

About 1 ft when the defender is at or above the screen or within 3 ft below it, half
that at 3–6 ft, and nothing beyond 6 ft, without using any label. The first two groups
are not distinguishable from each other.

**Does the show-minus-drop gap keep its sign under other settings? Yes.**
Varying one setting at a time, error gate (2, 3, 5 ft) or baseline (0.4, 0.6, 1.0 s
before), at three horizons (+1.0, +1.6, +2.0 s) gives 15 cases. The gap is between 0.63
and 1.06 ft in all of them, each with a range above zero and the same sign in 10 of 10
games. The full 27-cell cross was not run.

None of the three stop conditions in the plan was met.

## 3. Headline numbers you can quote

Ball screens, by the screener's defender, at +1 s:

| Coverage | Picks | Screener | Most open teammate | Team average |
|---|---|---|---|---|
| Show | ~600 | +1.54 [1.28, 1.79] | +1.97 [1.71, 2.17] | +0.99 [0.88, 1.12] |
| Drop | ~635 | +0.31 [0.06, 0.63] | +0.56 [0.21, 0.82] | +0.31 [0.14, 0.43] |
| Switch | ~212 | −0.41 [−0.73, −0.13] | +1.09 [0.62, 1.63] | +0.30 [0.16, 0.47] |

- Handler at +2 s: −0.22 against a show, −1.23 against a drop, −1.30 against a switch.
  Showing leaves the handler freer two seconds on as well.
- Handler by own defender at +1 s: −0.04 when the defender goes under, −1.35 over.
  By +2 s that difference is gone (−0.12 [−0.60, 0.40]).

Other actions at +1.6 s (supporting, same engine):

| Action | n | Main player | Most open teammate | Team average |
|---|---|---|---|---|
| Drive | ~600 | −3.51 | +1.48 | +0.40 |
| Handoff | ~400 | −1.46 | +1.94 | +0.62 |
| Off-ball screen | ~1,000 | +0.59 | +1.09 | +0.73 |
| Isolation | ~172 | −1.89 | +0.64 | +0.22 |
| No-action control | 91 | — | −0.65 | −0.43 |

Off-ball screens, cutter at +1 s: +1.43 when the defender goes around the screen
(`whip`, n=414), +0.56 when trailing (n=550).

Coverage: 96–97% of picks give an eligible handler and screener measurement at +1 s;
85% give an eligible team average (all five players must pass the gate).
Blitz (4 picks) and ice (13–14) are too rare in 10 games to say anything; they are in
the tables with their counts and no range.

## 4. Argument outline (structure only)

- **Question.** What does each way of guarding a ball screen give up, to whom, for how long?
- **Why it matters.** Coverage choice is a weekly coaching decision; public work prices
  coverages by points, not by the space that produces them.
- **Method in three steps.** Nearest-defender distance for every offensive player, every
  frame, gated on tracking error. Change from just before each action to three seconds
  after. Ranges by resampling whole games; a label-free check using defender depth.
- **Figure 1** (`results/fig1_curves.png`): space-created curves for screener, most open
  teammate and team average, by coverage.
- **Figure 2** (`results/fig2_space_vs_points.png`): space created in the tracked games
  against season points per pick, by coverage, for screener and handler.
- **Finding.** Showing opens about 0.7 ft more per offensive player than dropping, and
  the roles that gain space are the ones that score more over the season.
- **What it does not show.** Listed in section 5.
- **Open-source potential.** A loader for SkillCorner's basketball format, an openness
  measure with an honest quality gate, and an event-study engine that works for any
  action. `kloppy`'s documented SkillCorner loader covers football only; I found no
  mention of basketball in its docs or in a web search (not a check of its source code).

## 5. Weaknesses to state

- SkillCorner derives the coverage labels from the same tracking, so the screener's own
  gain against a show is close to definitional. The teammate, team-average and depth
  results carry the claim.
- Space is not points. The scoring link is by coverage over the season, not pick by pick,
  and the season file counts only picks that ended directly in a shot, assist or foul.
- Three coverages per role have enough picks for a range, so Figure 2 is three points a panel.
- Coverages are chosen, not assigned: teams show against some handlers and drop against
  others. These are descriptions of what happened, not the effect of switching coverage.
- Ten games, one league, one season, and only ten games to resample, so the ranges are
  probably a little narrow.
- The no-action control uses the most open of all five players, while actions use the
  most open of the three not involved. Compare team averages, not that column.

## 6. Submission checklist

- [ ] README at most 1,000 words, at most two figures or tables in total, your own words
- [ ] README includes run instructions for a clean environment (the three commands in the stub)
- [ ] `LICENSE.md` present (done, MIT)
- [ ] Data not committed (`data/` is git-ignored)
- [ ] Clean-install run passes (done locally on a copy; repeat from a real clone once pushed)
- [ ] Video at most three minutes, presented and voiced by you, on YouTube
- [ ] Repository public
- [ ] Submitted at submissions.analytics-cup.org by 16 December (deadline 18 December)

## 7. What the independent code review changed

A fresh reviewer read the whole project and re-ran it. Three findings were fixed, each
with a test that failed first:

- **Depth orientation was wrong for 74 of 1,509 picks.** A pick's recorded location is
  the screener's position, and tracking maps onto it by a mirror in x, not the point
  reflection the code assumed. The earlier "defenders above the screen break the pattern"
  result was this bug. No headline show-versus-drop number depended on it.
- **Windows ran past the end of the chance** (about 1% of picks at +1 s, 3–4% at +2 s,
  12% at +3 s). They now stop there.
- **Two tests would have passed with the wrong resampling.** Added tests that fail unless
  ranges come from resampling games and label shuffles stay within a game. These two
  passed against the existing code on first run; I did not watch them fail.

Left as they are, for you to decide:

- The `permutation_p` column in `pick_coverage.csv` is one test across all well-populated
  coverages, repeated on every row. It is not a show-versus-drop p-value. Do not quote it
  as one; quote the gap and its range.
- The eligibility gate uses SkillCorner's error estimate only, not its on-screen flag.
  The spec named both. Tightening the gate to 2 ft does not change the result.
- `scripts/download_data.sh` fetches the latest SkillCorner data, not a pinned version.
  If they update the files, the numbers could shift. Worth pinning before you submit.
- `results/` is git-ignored, so figures in the README need to be copied somewhere tracked.
- `uv.lock` should be committed with the code.

## 8. Added after the first commit

- **Figure 2 now compares like with like.** The season file prices only picks that led
  directly to a shot, assist or foul, so the tracked side of Figure 2 uses those picks
  too (`results/tables/pick_coverage_direct.csv`). The picture is the same: screener
  +1.39 ft against a show (318 picks) and +0.26 against a drop (354); handler −0.13
  when the defender goes under (121) and −1.33 over (545).
- **Replay clips for the video.** `uv run coverage-price replay --coverage show --out
  results/replay_show.gif` draws the pick whose team-average space created is nearest
  the median for that coverage, so the example is typical rather than flattering. Use
  `.mp4` instead of `.gif` for video editing. Clips are not tracked in git.
- **Review minors fixed:** the coverage-table p-value is renamed `omnibus_p` and blank
  for coverages too thin to be in the test; the five-a-side check counts distinct
  players; two teams acting in the same frame are kept apart; an empty data folder
  gives a clear error; four weak tests strengthened.
- **README.** The current `README.md` is a complete draft (839 words, two figures)
  written for you, not by you. The rules ask for your own words, so rewrite it in your
  voice before submitting and keep it aligned with what you say in the video.
