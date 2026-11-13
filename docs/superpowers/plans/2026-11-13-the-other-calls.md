# The Other Calls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For every pick in the 10 tracked games, price each plausible handler–screener pair among the five on the floor, mark the pair actually used, and report a summary and a rule-chosen worked moment.

**Architecture:** Two new modules. `menu.py` is pure pricing: season rates per player and role from the pick aggregates, shrunk toward the league, combined into a pair price with a 95% interval. `freezes.py` reads each game's pick events into freezes (the five on the floor, period, margin), builds menus, summarises them and picks the worked moment. `cli.py` gains a `menu` command and feeds `reproduce`'s gate-eligible picks into the summary.

**Tech Stack:** Python ≥3.11, uv, pandas, numpy, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-13-the-other-calls-design.md`

## Global Constraints

- Only SkillCorner ACB 2025–26 open data. No video, no outside data, and no code or data from Armchair or TheLowPost.
- No existing number in `results/` or `docs/outline.md` changes. `reproduce` only gains outputs.
- The README stays ≤1,000 words and ≤2 figures/tables in total, and the video ≤3:00. This plan writes neither; Adam does.
- Tests live in `tests/test_<module>.py` (this repo's pattern), written first and run to fail before the code.
- Gates before any commit: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- Work on a branch `feat/other-calls` cut from `feat/coverage-price-package`. **Adam approves every commit.** Each "Commit" step means: stage, show the message, and commit only on his go-ahead. Conventional Commits, no AI tool names, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Fixed values (from the spec, or decided here before any menu is seen):
  - `MIN_ROLE_PICKS = 30`: direct picks needed to be offered in a role.
  - `PRIOR_PICKS = 50`: the shrinkage strength, in pseudo-picks at the league rate. It's this plan's call, fixed now, and it is stated in the outline.
  - `LATE_PERIOD = 4`, `CLOSE_MARGIN = 6`, `MIN_RULE_SET = 5`: the worked-moment rule and its fallbacks (second half means period ≥ 3, then the whole game).
  - 95% intervals use `Z95 = 1.96`.

## Decisions this plan makes (the spec left them open)

- **Price interval.** Per role, the league per-pick variance of points comes from the outcome counts. A pick yields 0, 2 or 3 points: SkillCorner's points equal 2×(score_2pt+assist_2pt) + 3×(score_3pt+assist_3pt), which I checked on the season totals for both roles. A player's sd is σ_role / √(n + PRIOR_PICKS). A pair's sd is √(sd_h² + sd_s²). The overlap term is treated as fixed.
- **Five on the floor:** the pick's chance's `offPlayerIds`, not reconstructed from tracking. If the pair actually used is missing from that list, it is still added to the menu.
- **Gate eligibility:** a pick is eligible if `reproduce`'s space table has a row for it at `offset == 0` and `role == "team_mean"`. That means its own frame passed the existing gate with five players a side.
- **Margin:** |homeStartScore − awayStartScore| of the pick's chance. Period comes from the pick event.
- **Aggregate ids** go through `player_id_aliases.csv` before summing. The aggregates contain 8 alias ids, and events are already canonical.

## Review Focus

1. A player on the floor with no aggregate row (an alias, or no picks) prices at the league rate and does not raise a `KeyError`. Test in Task 1.
2. A traded player (one row per team plus a `total` row) is counted once, and an alias id is merged into its canonical id. Test in Task 1.
3. The pair actually used is not among the chance's `offPlayerIds`. It is still priced and marked. Test in Task 2.
4. The worked-moment set has an even count. The median pick is chosen deterministically (lower middle, ties broken by `action_id`). Test in Task 3.
5. `coverage-price menu` is given an unknown id or a non-pick id. It exits 2 with a message, not a traceback. Test in Task 4.

---

### Task 1: Season rates per player and pair price

**Files:**
- Create: `src/coverage_price/menu.py`
- Test: `tests/test_menu.py`

**Interfaces:**
- Produces:
  - `MIN_ROLE_PICKS = 30`, `PRIOR_PICKS = 50`, `Z95 = 1.96`
  - `League` (frozen dataclass): `handler_rate`, `screener_rate`, `handler_sd`, `screener_sd`, `assist_to_screener_rate`, `points_per_screener_basket` (all `float`).
  - `league_rates(picks_agg: pd.DataFrame) -> League`
  - `player_rates(picks_agg: pd.DataFrame, aliases: dict[int, int], prior_picks: float = PRIOR_PICKS) -> pd.DataFrame`, indexed by canonical `player_id`, with columns `handler_picks`, `handler_rate`, `handler_sd`, `assist_to_screener_rate`, `screener_picks`, `screener_rate`, `screener_sd`. A player with 0 picks in a role has exactly the league rate there.
  - `role_rate(rates: pd.DataFrame, league: League, player_id: int, role: str) -> tuple[float, float, int]` returns (rate, sd, picks). A player not in `rates` gets the league rate, sd σ_role/√PRIOR_PICKS and 0 picks.
  - `pair_price(handler_rate: float, screener_rate: float, assist_to_screener_rate: float, points_per_screener_basket: float) -> float`

Aggregate columns read: `player_id, team_name, {role}_total_picks, {role}_points, {role}_score_2pt, {role}_score_3pt, {role}_assist_2pt, {role}_assist_3pt, handler_assist_to_screener`. Exclude rows whose `team_name == SEASON_TOTAL_TEAM` (import it from `pricing.py`), map ids through `aliases`, then group by `player_id` and sum.

- [ ] **Step 1: Write the failing tests** in `tests/test_menu.py`, with a `_agg_row(player_id, team_name="A", **counts)` helper that fills every column above with 0 unless given.

```python
def test_pair_price_subtracts_the_overlap_once():
    assert pair_price(0.80, 0.30, 0.10, 2.25) == pytest.approx(0.80 + 0.30 - 0.10 * 2.25)

def test_league_points_per_screener_basket_uses_the_two_three_mix():
    league = league_rates(pd.DataFrame([_agg_row(1, screener_score_2pt=3, screener_score_3pt=1,
                                                 screener_total_picks=10, screener_points=9)]))
    assert league.points_per_screener_basket == pytest.approx((2 * 3 + 3 * 1) / 4)

def test_player_with_no_picks_in_a_role_prices_at_league():
    # player 1 handles 100 picks for 80 points; player 2 never handles
    rates = player_rates(table, aliases={}, prior_picks=10)
    assert rates.loc[2, "handler_rate"] == pytest.approx(league_rates(table).handler_rate)

def test_player_with_many_picks_prices_near_his_own_rate():
    # 10_000 picks at 1.2 points per pick; league otherwise 0.7
    assert rates.loc[1, "handler_rate"] == pytest.approx(1.2, abs=0.01)

def test_missing_player_gets_league_rate_and_no_picks():          # Review Focus 1
    assert role_rate(rates, league, 999, "screener") == (
        pytest.approx(league.screener_rate), pytest.approx(league.screener_sd / PRIOR_PICKS**0.5), 0)

def test_traded_and_aliased_rows_are_counted_once():               # Review Focus 2
    # rows: (7, "A", 20 picks), (7, "B", 15 picks), (7, "total", 35 picks), (70, "A", 5 picks)
    rates = player_rates(table, aliases={70: 7})
    assert rates.loc[7, "handler_picks"] == 40 and 70 not in rates.index

def test_league_sd_matches_the_outcome_mix():
    # 10 picks: 2 two-point scores, 1 three-point assist -> mean 0.7, E[X^2] = (2*4 + 9)/10
    assert league.handler_sd == pytest.approx(math.sqrt(1.7 - 0.7**2))
```

- [ ] **Step 2: Run them and confirm they fail.** Run `uv run pytest tests/test_menu.py -v`. Expected: collection errors, because `coverage_price.menu` doesn't exist yet.
- [ ] **Step 3: Implement the interface above in `src/coverage_price/menu.py`.** The shrunk rate is `(points + prior × league_rate) / (picks + prior)`. `assist_to_screener_rate` shrinks the same way, toward the league rate per handler pick.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `uv run pytest tests/test_menu.py -v`. Expected: all pass.
- [ ] **Step 5: Run the gates.** Commit `feat(menu): price handler–screener pairs from season pick rates` on Adam's approval.

### Task 2: A pick's menu

**Files:**
- Modify: `src/coverage_price/menu.py`
- Test: `tests/test_menu.py`

**Interfaces:**
- Consumes: `League`, `role_rate`, `pair_price`, `MIN_ROLE_PICKS`, `Z95` (Task 1).
- Produces:
  - `MENU_COLUMNS = ["handler_id", "screener_id", "price", "lo", "hi", "used", "below_volume", "best", "too_close_to_best"]`
  - `too_close(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> bool`: True when the intervals overlap, touching included.
    *Superseded after review (Adam's call): `too_close(gap, sd)` is True when |gap| ≤ Z95 × sd, with sd from `difference_sd(a_terms, b_terms)`, where a (player, role) term both pairs share cancels. See the spec's "Too close to call".*
  - `build_menu(on_floor: Sequence[int], used: tuple[int, int], rates: pd.DataFrame, league: League) -> pd.DataFrame`. It returns one row per ordered pair (h ≠ s) from `set(on_floor) | set(used)` where h has ≥ MIN_ROLE_PICKS handler picks and s has ≥ MIN_ROLE_PICKS screener picks, plus always the `used` row (`below_volume` True if it fails the rule). Rows are sorted by price descending. `best` marks the top row; `too_close_to_best` is true for any row whose interval overlaps the best's (and for the best itself).

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize("a, b, expected", [
    ((0.8, 1.0), (0.9, 1.1), True), ((0.8, 1.0), (1.0, 1.2), True), ((0.8, 1.0), (1.01, 1.2), False)])
def test_too_close_when_intervals_overlap(a, b, expected): ...

def test_low_volume_player_is_not_offered_but_used_pair_is_priced():
    # five players; player 5 has 3 handler picks. used = (5, 1)
    menu = build_menu([1, 2, 3, 4, 5], (5, 1), rates, league)
    assert menu[(menu.handler_id == 5)].shape[0] == 1
    used = menu[menu.used].iloc[0]
    assert (used.handler_id, used.screener_id, used.below_volume) == (5, 1, True)

def test_used_pair_off_the_listed_five_is_still_on_the_menu():   # Review Focus 3
    menu = build_menu([1, 2, 3, 4, 6], (5, 1), rates, league)
    assert menu.used.sum() == 1

def test_menu_never_pairs_a_player_with_himself(): ...
def test_best_is_the_highest_price_and_flags_ties_within_interval(): ...
```

- [ ] **Step 2: Run them and confirm they fail.** Expected: `ImportError` on `build_menu`.
- [ ] **Step 3: Implement `too_close` and `build_menu`.** The interval is `price ± Z95 × √(sd_h² + sd_s²)`.
- [ ] **Step 4: Run the tests and confirm they pass.**
- [ ] **Step 5: Run the gates.** Commit `feat(menu): list and rank the pairs on the floor at a pick` on approval.

### Task 3: Freezes, summary and the worked moment

**Files:**
- Create: `src/coverage_price/freezes.py`
- Test: `tests/test_freezes.py`

**Interfaces:**
- Consumes: `build_menu`, `League`, `player_rates`, `league_rates` (Tasks 1–2); `load_events`, `load_game` (loader).
- Produces:
  - `FREEZE_COLUMNS = ["action_id", "game_id", "period", "margin", "handler_id", "screener_id", "on_floor"]`, where `on_floor` is a tuple of ints.
  - `game_freezes(events: dict[str, pd.DataFrame], home_team_id: int) -> pd.DataFrame`: one row per pick with a chance. `margin` is `abs(homeStartScore - awayStartScore)` of its chance. Picks with no chance row are dropped.
  - `menus_for(freezes: pd.DataFrame, rates: pd.DataFrame, league: League) -> pd.DataFrame`: the concatenated menus with `action_id` and `game_id` columns added.
  - `gaps(menus: pd.DataFrame) -> pd.DataFrame`: one row per action with at least one non-used pair. Columns: `action_id, game_id, gap` (best price − used price), `used_too_close` (bool).
  - `summarise_menus(menus: pd.DataFrame, n_boot: int, seed: int = 0) -> dict`, with keys `picks_with_menu`, `left_out` (actions whose menu is the used pair alone), `share_too_close`, `mean_gap`, `gap_lo`, `gap_hi`, `n_games`. The gap interval resamples whole games, as in `eventstudy._game_draws` (reuse it).
  - `LATE_PERIOD = 4`, `CLOSE_MARGIN = 6`, `MIN_RULE_SET = 5`
  - `worked_moment(gaps: pd.DataFrame, freezes: pd.DataFrame) -> tuple[str, str]` returns (action_id, rule), where rule is one of `"fourth quarter, within 6"`, `"second half, within 6"` or `"whole game, within 6"`. In each set it takes the lower-middle element after sorting by (gap, action_id).

- [ ] **Step 1: Write the failing tests.**

```python
def test_freeze_reads_five_period_and_margin_from_the_chance():
    events = {"picks": pd.DataFrame([pick("p1", chance="c1", period=4, handler=1, screener=2)]),
              "chances": pd.DataFrame([chance("c1", off=[1, 2, 3, 4, 5], home=70, away=66)])}
    row = game_freezes(events, HOME).iloc[0]
    assert (row.period, row.margin, row.on_floor) == (4, 4, (1, 2, 3, 4, 5))

def test_pick_without_a_chance_is_dropped(): ...

def test_summary_counts_left_out_and_share_too_close():
    # three actions: one alone (left out), one used==best, one used clearly worse
    s = summarise_menus(menus, n_boot=50)
    assert (s["picks_with_menu"], s["left_out"], s["share_too_close"]) == (2, 1, pytest.approx(0.5))

@pytest.mark.parametrize("periods, expected_rule", [
    ([4] * 5, "fourth quarter, within 6"), ([4] * 2 + [3] * 3, "second half, within 6"),
    ([1] * 5, "whole game, within 6")])
def test_worked_moment_falls_back(periods, expected_rule): ...

def test_worked_moment_takes_the_median_gap():
    # five late close actions with gaps 0.0, 0.1, 0.2, 0.3, 0.4 -> the 0.2 one
def test_even_set_takes_the_lower_middle_by_gap_then_id():       # Review Focus 4
    # six actions, gaps 0.0, 0.1, 0.2, 0.2, 0.3, 0.4 with ids "b" and "a" at 0.2 -> "a"
```

Is "within 6" required in every fallback? Yes. The spec widens only the time window, so the margin rule holds in every fallback.

- [ ] **Step 2: Run them and confirm they fail.** Run `uv run pytest tests/test_freezes.py -v`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement `freezes.py` to the interfaces above.**
- [ ] **Step 4: Run the tests and confirm they pass.**
- [ ] **Step 5: Run the gates.** Commit `feat(freezes): summarise pick menus and choose the worked moment by rule` on approval.

### Task 4: `menu` command and `reproduce` output

**Files:**
- Modify: `src/coverage_price/cli.py`
- Test: `tests/test_cli.py` (create), plus an integration test in `tests/test_freezes.py`

**Interfaces:**
- Consumes: everything above; `report.load_inputs` and `space` as already built in `reproduce`; `load_aliases`, `list_games`, `load_events`, `load_game`.
- Produces:
  - `menu(data_dir: Path, action_id: str) -> int`, which prints one line per pair: handler name, screener name, price with `[lo, hi]`, and markers `used`, `best`, `too close`, `below 30`. It returns 0, or 2 with a stderr message for missing data, an unknown id, or a non-pick id. It reads no tracking.
  - In `reproduce`: per game, `game_freezes`, filtered to action ids in `space[(space.kind == "pick") & (space.offset == 0) & (space.role == "team_mean")]`. After the loop it builds menus, writes `out/tables/menus.csv`, and adds `summary["other_calls"] = {**summarise_menus(...), "worked_moment": id, "worked_rule": rule, "prior_picks": PRIOR_PICKS, "min_role_picks": MIN_ROLE_PICKS}`. Every existing key and file stays the same.

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize("action_id", ["no-such-id", "drive-114086-1-0"])
def test_menu_rejects_unknown_and_non_pick_ids(tmp_path, action_id, capsys):   # Review Focus 5
    root = write_game(tmp_path, ...)  # conftest helper, with one pick and one drive
    assert main(["menu", "--data-dir", str(root), action_id]) == 2
    assert action_id in capsys.readouterr().err

def test_menu_prints_the_used_pair(tmp_path, capsys): ...
```

The integration test in `tests/test_freezes.py`, `@pytest.mark.skipif(not REAL_DATA.exists(), ...)`, runs `game_freezes` and `menus_for` on the first real game. Assert:
  - every freeze has 5 on the floor;
  - every menu has exactly one `used` row;
  - every price is between 0 and 3.

- [ ] **Step 2: Run them and confirm they fail.** Expected: argparse error ("invalid choice: 'menu'").
- [ ] **Step 3: Add the `menu` subcommand (`action_id` is positional, `--data-dir` as in `replay`) and the `reproduce` additions.** The aggregate path stays `PICKS_AGGREGATE`.
- [ ] **Step 4: Run all tests and confirm they pass.** Then run `uv run coverage-price reproduce --quick`. Expected: it exits 0, `results/summary.json` has an `other_calls` key, and `results/tables/menus.csv` exists.
- [ ] **Step 5: Negative control.** Run `git diff --stat results/` against the pre-change quick run. Only `summary.json` (the new key, plus `seconds`) and the new `menus.csv` may differ. Any other changed file fails the task.
- [ ] **Step 6: Run the gates.** Commit `feat(cli): print a pick's menu and add the other-calls summary to reproduce` on approval.

### Task 5: Full run and outline numbers

**Files:**
- Modify: `docs/outline.md` (a new section, `## 9. The other calls`)

- [ ] **Step 1: Run the full reproduction.** Run `uv run coverage-price reproduce` in the background. Expected: it exits 0, and the existing figures and tables are byte-identical to the committed ones.
- [ ] **Step 2: Render the worked moment.** Run `uv run coverage-price replay --action-id <worked_moment> --out results/worked_moment.mp4`, then `uv run coverage-price menu <worked_moment>`.
- [ ] **Step 3: Write section 9 of `docs/outline.md`.** Include:
  - the fixed values (`MIN_ROLE_PICKS`, `PRIOR_PICKS`, the rule and which fallback applied);
  - `picks_with_menu`, `left_out`, `share_too_close`, and the mean gap with its game-resampled interval and `n_games`;
  - the worked moment's id, its game, period and margin, and its printed menu.

  Cite numbers only, copied from `summary.json`, with no prose for the README. Add the known weaknesses from the spec, plus this one: screener assists to the handler, if any, are not separable in the aggregates (`screener_assist_to_other` lumps them), so a second overlap may remain.
- [ ] **Step 4: Commit** `docs(outline): other-calls numbers for the write-up` on approval.
