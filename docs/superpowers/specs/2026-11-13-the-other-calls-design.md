# The other calls: pricing what the offense could have run — design

13 November 2026. An addition to the PySport Analytics Cup 2.0 entry described in
`2026-11-10-price-of-a-coverage-design.md`. That document's constraints all still apply.

## Intent

The entry so far measures what a defense's ball-screen coverage gives up. It only ever
looks at the action that was run. This addition shows the actions that were not run: at a
real moment in a tracked game, it lists what this offense, with these five players on the
floor, could have run instead, prices each option from those players' own season numbers,
and sets the action they actually ran against that menu. The menu is ball screens only: which
handler–screener pair to run it with (see "Why picks only").

The idea comes from a separate project of Adam's (a "what would you call" game). Only the
idea carries over. No code or data from that project, or from TheLowPost, is used.

It is part of the current entry, not a second entry. It appears in the story the judges
read and watch (README and video), not as a separate tool.

## Goals

- For any pick in the 10 tracked games, a priced menu of every plausible handler–screener
  pair among the five offensive players on the floor, with the pair actually used marked.
- One worked moment that carries this idea in the video and the README.
- One summary number across all eligible actions in the 10 games, so the worked moment is
  not the only evidence (see "Summary across all actions").
- Everything reproducible from the existing `reproduce` command, with new numbers listed in
  `docs/outline.md` for Adam to write from.

## Non-goals

- A playable or interactive tool. This was considered and turned down (see Approaches).
- Menus of different kinds of action (pick against drive against catch-and-shoot). Turned
  down by Adam; see "Why picks only".
- Freezes on actions other than picks.
- Changing any existing result in the entry.
- Predicting what a coach should have called. The menu prices options; it does not say the
  offense was wrong.

## Anti-goals (failure even if it technically works)

- A worked moment chosen because it makes the menu look dramatic, then presented as typical.
- Two prices compared on different scales, so the menu ranks options by an artefact of how
  SkillCorner counts them.
- Breaking or slowing the existing reproduction, or changing any number already in
  `docs/outline.md`.
- Pushing the README past 1,000 words or two figures and tables, or the video past three
  minutes.

## Constraints

From the entry's rules, as recorded in the original design: only SkillCorner's ACB
2025–26 data; no video; all code written for this entry; Python with `uv`, pandas, numpy,
matplotlib, pytest, ruff; README at most 1,000 words and two figures or tables in total,
in Adam's own words; video at most three minutes, voiced by Adam. Submission by 18 December,
internal target 16 December.

Room left today: the README is 838 words with both figures used. The video script runs 2:50.

## Approaches

| | Approach | Trade-off | |
|---|---|---|---|
| A | The menu appears in the story: one worked moment in the video, a short passage and a summary number in the README, a command that prints the menu for any action. | Fits the rules. It costs README words and video seconds that other material has to give up. | **Chosen** |
| B | A small local page where a viewer freezes a moment, picks a call and sees the reveal. | Strongest on open-source potential. It's a new front end with five weeks left. Judges may never open it, since it sits outside the README and the video. | Turned down |
| C | A menu of named offensive play calls (horns, floppy and so on), as in the game the idea comes from. | SkillCorner does not label play calls, only the actions inside them. Pricing them would need a model the original design's first test already showed 10 games cannot support. | Ruled out |

Within A, Adam chose a menu of picks only over a mixed menu of picks, drives and
catch-and-shoot shots (see "Why picks only").

A menu of defensive coverages was not considered as an alternative. That is the original
entry's subject; this addition is about the offense's options.

## Design

### Why picks only

The season aggregates put the three kinds of action on different scales, and nothing in
them lines the scales up (checked against `docs/aggregates_columns.md`, `PRIMER.md` and
`KNOWN_ISSUES.md`, and the files themselves):

- Pick totals count only direct picks, where the handler or screener shot, assisted or was
  fouled straight after the screen: 22,085 of the season's 42,156 picks. Drive totals count
  every drive.
- Pick and drive points include assisted teammates' baskets and leave out free throws. Shot
  points are the shooter's own and include free throws on and-ones.

A mixed menu would need a direct-pick share estimated from the 10 tracked games and applied
to season numbers. Adam chose picks only: every price stays on one season-long scale, and the
menu stays on the entry's subject.

### The freeze

A freeze is the frame of a pick in one of the 10 tracked games (the `pick` kind in
`actions.py`) whose tracking frame passes the existing eligibility gate. Direct and
non-direct picks both count. The menu prices the decision, which pair to run it with, not
the outcome, so a pick that led nowhere is still a decision with a menu. The five offensive
players on the floor are read from that frame.

### The menu

Every ordered handler–screener pair among those five players that passes the plausibility
rule below. The pair actually used is always on the menu and always priced, even if it fails
the rule; it is then marked as below the rule's volume.

**Plausibility (my call).** A player can be the handler in a menu pair only if he has at
least 30 direct picks as handler this season, and the screener only if he has at least 30 as
screener. Without this, centers would appear as handlers and be priced near the league handler
rate, far above the screener rate, so implausible pairs could top the menu. The threshold is
fixed here, before any menu is seen. If a player has fewer than 30 picks in a role, he is not
offered in that role. If no pair passes, the menu holds only the pair actually used and the
moment is left out of the summary, which counts how often that happens.

**Coverage (my call).** Prices pool every coverage, using each player's totals across all of
them. The aggregates record only the offense, so a defense's season coverage mix does not
exist in them; the 10 tracked games give one or two games per team, usually the very game of
the freeze. Which coverage a defense chooses is the original entry's subject. The menu is about
the offense's choice of pair, and every option, the one actually run included, is priced on
the same pooled footing.

### Pricing a pair

A player's rate in a role is points per direct pick in that role, shrunk toward the league
rate for the role, weighted by his direct picks in it. The prior's strength is left to the
builder, chosen once and stated, not tuned to the results.

A pair's price is points per direct pick for the two of them together (my call):

- the handler's points per pick, which counts his own baskets and every basket he assisted,
  including the screener's;
- plus the screener's points per pick, which counts his own baskets and the baskets he
  assisted (any assist to the handler is then counted twice and cannot be separated);
- minus the overlap: the screener's baskets assisted by the handler are in both. The handler's
  assist-to-screener rate times the league's points per assisted screener basket estimates it.
  `handler_assist_to_screener` is not split into twos and threes, so the league's two/three mix
  for screener baskets sets the points per basket. A known-answer test fixes the arithmetic.

Season totals check this: handler points 15,497 and screener points 5,683 over 22,085 direct
picks, with 1,620 handler assists to the screener inside the handler's total.

Each price carries a 95% interval.

### Too close to call

Two options are reported as too close to call, not ranked, when the difference between their
prices sits inside that difference's 95% interval (touching counts). The spread of the
difference comes from the player estimates the two options do not share: a player in the
same role in both adds the same estimate to each price, so it cancels. (Revised after review:
the first draft called two options too close when their own intervals overlapped, which is
stricter and ignores a shared player.) The menu shows the best option, the action actually
run, and whether they can be told apart.

### Summary across all actions

Across every eligible pick in the 10 games with at least one menu pair beside the one used,
the builder reports:

- the share where the pair actually used is too close to call with the best pair on its menu;
- the average gap in expected points per direct pick between the best pair and the pair used,
  with a game-resampled interval like the rest of the entry;
- how many picks were left out because no other pair passed the plausibility rule.

This is the number that carries the idea in the README, as text, not a table.

### The worked moment

It is chosen by a rule fixed before looking at any menu. The rule: of eligible picks in the
fourth quarter with the margin within 6 points, the one whose gap is the median of that set.
This is my call: it keeps the example typical, and says so. If that set has fewer than 5
actions, widen to the second half, then to the whole game, and say which rule applied.

The worked moment uses the existing replay renderer to show the real action. The menu is
shown beside it as a text card, which needs no new rendering work.

### Where it appears

- **README:** no new figure or table. About 120–150 words, which Adam writes: the idea, the
  worked moment in one sentence, the summary number, and the limits. Some existing text has
  to give way, and that choice is Adam's.
- **Video:** the worked moment, about 25–30 seconds. Because the script already runs 2:50,
  existing sections have to shrink. The outline suggests where; the cut is Adam's.
- **Command:** `uv run coverage-price menu <action_id>` prints the menu for any pick, and
  `reproduce` adds the summary numbers and the worked moment's id to its output.
- **`docs/outline.md`:** a new section with every number above, its interval and its sample
  size.

### Tests

Following the original design, every component's tests are written first.

- Known-answer tests on small synthetic aggregates:
  - a player with no actions prices at the league rate;
  - a player with many actions prices near his own rate;
  - a pair's price matches a hand-computed value, with the overlap subtracted once;
  - a player under the volume threshold is not offered in that role, but the pair actually
    used is priced whatever its volume;
  - two options whose price difference sits inside its 95% interval are reported as too
    close to call, and a player both options share in the same role does not widen it.
- A selection-rule test on synthetic actions: the rule picks the median-gap action and falls
  back as described.
- One integration test against a real game, skipped when the data is absent.

## Known weaknesses to state openly

- Season prices are averages over many situations; a moment's own context is not priced
  (score, clock, matchups at that moment, the coverage the defense was in).
- The menu covers only who runs the ball screen, not other kinds of action.
- Prices are per direct pick, about half of all picks; picks that lead nowhere are outside
  the season numbers.
- The handler–screener overlap is estimated, not counted.
- Ten tracked games, one league, one season.

## Left to the builder

- Module layout and names, within the existing package.
- The shrinkage prior's strength, chosen once and stated.
- How the menu is printed.
- Where the summary goes in the `reproduce` output.

## Open items for Adam

- Which README text and video section give way for this addition.
- Whether the plausibility threshold (30 direct picks in a role) and pooled-coverage pricing
  match how you want the menu to read.
- Writing the README passage and the video segment.
