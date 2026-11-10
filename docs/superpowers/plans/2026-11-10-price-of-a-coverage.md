# The Price of a Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reproducible Python package that measures how much space each ball-screen coverage gives up in the 10 tracked ACB games and prices each coverage from the season aggregates.

**Architecture:** Six small modules in one package. `loader` turns SkillCorner files into tables; `openness` turns frames into nearest-defender distances with an eligibility flag; `actions` unifies the event families; `eventstudy` computes and summarises space created; `depth` gives a label-free check; `pricing` reads the season file. A CLI runs them in order and writes two figures and the result tables.

**Tech Stack:** Python 3.11+, uv, pandas, numpy, matplotlib, pytest, ruff. MIT licence.

**Spec:** `docs/superpowers/specs/2026-11-10-price-of-a-coverage-design.md`

## Global Constraints

- Only the SkillCorner ACB 2025–26 open dataset. No video, no other data, no code or data from TheLowPost.
- Data is never committed. `data/` is git-ignored.
- No proprietary software and no notebooks in the reproduction path.
- `LICENSE.md` (MIT) at the repository root.
- All distances in feet; frame rate 25 fps; hoop at (−40.76, 0) in the normalised frame.
- `soft` is reported as `drop` in every output.
- A measurement is either eligible or ineligible. Ineligible values are excluded and counted; they are never zero-filled.
- Default eligibility gate: `predError` ≤ 3.0 ft for both the offensive player and the nearest defender; at least 5 tracked players per side in the frame.
- Uncertainty is by resampling whole games; label permutations are within game.
- Test first for every function. Tests live in `tests/test_<module>.py`. Literals in tests are named.
- No `TODO` comments; open a GitHub issue instead once the repository exists.
- Nothing is committed, pushed or published without Adam's explicit approval. Each task ends by showing the diff and a proposed Conventional Commit message, with no mention of AI tools and no co-author trailer.
- README prose and the video are Adam's. The package produces numbers, figures and an outline only.

## Review Focus

1. Tracking file is still a Git LFS pointer (data not fully downloaded): expect a clear error naming the download script, not a gzip traceback. Test in Task 2.
2. An action's main player is missing from tracking at the baseline frame: expect that role to be ineligible for that action, counted, not a crash or a zero. Test in Task 5.
3. A window crosses dead-ball frames or frames with fewer than 5 players a side: expect those offsets to be missing for that action only. Tests in Tasks 3 and 5.
4. A coverage with very few actions (blitz, ice): expect it in the table with its count and an empty range, not dropped and not a bootstrap error. Test in Task 6.
5. An event with a null `location` or null coverage label: expect `depth` to skip it and report how many were skipped, and the coverage to read `none`. Tests in Tasks 4 and 7.

---

## File Structure

```
pyproject.toml            package metadata, deps, ruff and pytest config, CLI entry point
LICENSE.md                MIT
.gitignore                data/, results/, .venv/, caches
scripts/download_data.sh  clone SkillCorner/opendata-basketball with LFS into data/
src/coverage_price/
  __init__.py
  constants.py            FPS, HOOP_XY, OFFSETS, BASELINE_OFFSET, MAX_PRED_ERROR_FT, COVERAGE_NAMES
  loader.py               game metadata, events, tracking frames
  openness.py             nearest-defender distance + eligibility
  actions.py              unified action table, control moments
  eventstudy.py           space created, summaries, permutation test
  depth.py                screener-defender depth at the screen
  pricing.py              season points per pick by coverage
  report.py               figures and tables
  cli.py                  `coverage-price reproduce`
tests/
  conftest.py             synthetic frame and event builders
  test_loader.py test_openness.py test_actions.py test_eventstudy.py
  test_depth.py test_pricing.py test_report.py
docs/outline.md           numbers and argument outline for Adam's README and video
```

---

### Task 1: Repository scaffold and event loader

**Files:**
- Create: `pyproject.toml`, `LICENSE.md`, `.gitignore`, `scripts/download_data.sh`, `src/coverage_price/__init__.py`, `src/coverage_price/constants.py`, `src/coverage_price/loader.py`, `tests/conftest.py`, `tests/test_loader.py`

**Interfaces:**
- Produces:
  - `constants.FPS = 25`, `HOOP_XY = (-40.76, 0.0)`, `OFFSETS = tuple(range(-25, 80, 5))`, `BASELINE_OFFSET = -15`, `MAX_PRED_ERROR_FT = 3.0`, `COVERAGE_NAMES = {"soft": "drop"}`
  - `loader.list_games(data_dir: Path) -> list[Path]` — sorted game folders under `data_dir/data/matches`
  - `loader.Game` — frozen dataclass: `game_id: int`, `home_team_id: int`, `away_team_id: int`, `players: pd.DataFrame` (`player_id`, `team_id`, `name`, `jersey`)
  - `loader.load_game(game_dir: Path) -> Game`
  - `loader.load_events(game_dir: Path, aliases: dict[int, int] | None = None) -> dict[str, pd.DataFrame]` — one DataFrame per event family, keys exactly as in the JSON; every column ending in `Id` that holds player ids is mapped through `aliases`
  - `loader.load_aliases(data_dir: Path) -> dict[int, int]`
  - `conftest.write_game(tmp_path, game_id, events: dict, frames: list[dict]) -> Path` — writes a miniature game folder in SkillCorner's layout (JSON, JSON, gzipped JSON Lines)

- [ ] **Step 1:** `git init -b main`; write `pyproject.toml` (src layout, `requires-python = ">=3.11"`, deps pandas, numpy, matplotlib; dev deps pytest, ruff; script `coverage-price = "coverage_price.cli:main"`), `LICENSE.md` (MIT, holder Adam Rowe, 2026), `.gitignore`. Run `uv sync`. Expected: environment created.
- [ ] **Step 2:** Write `scripts/download_data.sh`: clones `https://github.com/SkillCorner/opendata-basketball.git` into `data/opendata-basketball` with `git lfs install --local` then `git lfs pull`; exits non-zero with a message if `git-lfs` is missing.
- [ ] **Step 3: Write failing tests** in `tests/test_loader.py`:

```python
HOME, AWAY, GAME = 10, 20, 999


def test_load_game_reads_team_ids_and_players(tmp_path):
    game_dir = write_game(tmp_path, GAME, events={}, frames=[])
    game = load_game(game_dir)
    assert (game.game_id, game.home_team_id, game.away_team_id) == (GAME, HOME, AWAY)
    assert set(game.players.columns) == {"player_id", "team_id", "name", "jersey"}


def test_load_events_returns_one_table_per_family_and_applies_aliases(tmp_path):
    DUPLICATE, CANONICAL = 501, 500
    events = {
        "picks": [{"id": "pick-1", "frame": 100, "ballhandlerId": DUPLICATE, "screenerId": 7}],
        "shots": [],
    }
    game_dir = write_game(tmp_path, GAME, events=events, frames=[])
    tables = load_events(game_dir, aliases={DUPLICATE: CANONICAL})
    assert tables["picks"].loc[0, "ballhandlerId"] == CANONICAL
    assert tables["shots"].empty


def test_list_games_is_sorted(tmp_path): ...  # two folders written out of order come back ascending
```

- [ ] **Step 4:** Run `uv run pytest tests/test_loader.py -v`. Expected: FAIL, `coverage_price.loader` not found.
- [ ] **Step 5:** Implement `constants.py`, `loader.py` (functions above) and `conftest.write_game`. `write_game` uses `HOME`/`AWAY` rosters of five players each (ids 1–5 and 11–15) unless told otherwise.
- [ ] **Step 6:** Run `uv run pytest -v` and `uv run ruff check . && uv run ruff format --check .`. Expected: all pass.
- [ ] **Step 7:** Show the diff; propose `chore: scaffold package and add event loader`.

---

### Task 2: Tracking frame reader

**Files:**
- Modify: `src/coverage_price/loader.py`
- Test: `tests/test_loader.py`

**Interfaces:**
- Consumes: `Game`, `write_game`.
- Produces: `loader.read_frames(game_dir: Path, game: Game, frame_ids: Collection[int]) -> pd.DataFrame` — long table, one row per tracked player per requested frame: `frame: int`, `team_id: int`, `player_id: int`, `x: float`, `y: float`, `pred_error: float`, `is_detected: bool`. Frames with an empty player list on either side are absent. `loader.DataNotDownloadedError(RuntimeError)`.

- [ ] **Step 1: Write failing tests:**

```python
def test_read_frames_returns_only_requested_live_frames(tmp_path):
    LIVE, DEAD, UNREQUESTED = 100, 101, 102
    frames = [live_frame(LIVE), dead_frame(DEAD), live_frame(UNREQUESTED)]
    game_dir = write_game(tmp_path, GAME, events={}, frames=frames)
    out = read_frames(game_dir, load_game(game_dir), {LIVE, DEAD})
    assert set(out.frame) == {LIVE}
    assert len(out) == 10 and out.is_detected.dtype == bool


def test_read_frames_raises_clear_error_on_lfs_pointer(tmp_path):
    game_dir = write_game(tmp_path, GAME, events={}, frames=[])
    (game_dir / f"{GAME}_tracking_data.jsonl.gz").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
    )
    with pytest.raises(DataNotDownloadedError, match="download_data.sh"):
        read_frames(game_dir, load_game(game_dir), {1})
```

Add `live_frame(frame_idx, home_xy=None, away_xy=None, pred_error=1.0)` and `dead_frame(frame_idx)` builders to `conftest.py`.

- [ ] **Step 2:** Run the two tests. Expected: FAIL.
- [ ] **Step 3:** Implement `read_frames`. Stream the gzip line by line; read the frame index from the line's `"frameIdx":` prefix and call `json.loads` only on requested lines (a full game is 30–46 MB compressed). Detect an LFS pointer by the first bytes not being the gzip magic `1f 8b`.
- [ ] **Step 4:** Run `uv run pytest tests/test_loader.py -v`. Expected: PASS.
- [ ] **Step 5:** Show the diff; propose `feat(loader): read requested tracking frames`.

---

### Task 3: Openness

**Files:**
- Create: `src/coverage_price/openness.py`, `tests/test_openness.py`

**Interfaces:**
- Consumes: the long frame table from `read_frames`.
- Produces: `openness.openness(frames: pd.DataFrame, sides: pd.DataFrame, max_pred_error: float = MAX_PRED_ERROR_FT) -> pd.DataFrame` — `sides` has `frame`, `off_team_id`, `def_team_id`. Returns one row per offensive player per frame: `frame`, `player_id`, `dist_ft`, `defender_id`, `eligible: bool`.

- [ ] **Step 1: Write failing tests:**

```python
DEFENDER_GAP_FT = 4.0

def test_distance_is_to_the_nearest_defender():
    # offensive player 1 at (0, 0); defenders at (DEFENDER_GAP_FT, 0) and (20, 0)
    out = openness(frames, sides)
    row = out[out.player_id == 1].iloc[0]
    assert row.dist_ft == pytest.approx(DEFENDER_GAP_FT) and row.defender_id == 11 and row.eligible

def test_high_pred_error_on_either_player_is_ineligible():   # offensive player error 3.1 -> False; nearest defender error 3.1 -> False
def test_threshold_is_inclusive():                           # error exactly 3.0 -> eligible
def test_fewer_than_five_a_side_makes_every_row_ineligible():
def test_frame_missing_from_sides_is_dropped():
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement with a per-frame pairwise distance matrix in numpy (5×5 per frame; group by frame).
- [ ] **Step 4:** Run `uv run pytest tests/test_openness.py -v`. Expected: PASS.
- [ ] **Step 5:** Show the diff; propose `feat(openness): nearest-defender distance with eligibility gate`.

---

### Task 4: Unified action table and control moments

**Files:**
- Create: `src/coverage_price/actions.py`, `tests/test_actions.py`

**Interfaces:**
- Consumes: `load_events` tables, `COVERAGE_NAMES`.
- Produces:
  - `actions.collect_actions(events: dict[str, pd.DataFrame], game_id: int) -> pd.DataFrame` — columns `action_id`, `kind`, `game_id`, `frame`, `main_id`, `second_id` (nullable), `off_team_id`, `def_team_id`, `main_cov`, `second_cov`, `chance_id`, `loc_x`, `loc_y` (nullable).
  - `actions.control_moments(events, actions: pd.DataFrame, game_id: int, seed: int = 0, clear_frames: int = 75) -> pd.DataFrame` — same columns, `kind == "control"`, ids and coverages null; at most one per chance, drawn between `frontcourtFrame + 50` and `endFrame − 100`, kept only if no action lies within `clear_frames`.

Field mapping (source table → `frame`, `main_id`, `second_id`, `main_cov`, `second_cov`):

| kind | frame | main | second | main_cov | second_cov |
|---|---|---|---|---|---|
| `pick` (`picks`) | `frame` | `ballhandlerId` | `screenerId` | `bhrDefType` | `scrDefType` |
| `handoff` (`handoffs`) | `frame` | `receiverId` | `setterId` | `receiverDefType` | `setterDefType` |
| `off_ball_screen` (`off_ball_screens`) | `frame` | `cutterId` | `screenerId` | `cutterDefType` | `screenerDefType` |
| `drive` (`drives`) | `startFrame` | `ballhandlerId` | — | — | — |
| `isolation` (`isolations`) | `startFrame` | `ballhandlerId` | — | — | — |
| `post` (`posts`) | `startFrame` | `ballhandlerId` | — | — | — |

- [ ] **Step 1: Write failing tests:** `test_pick_maps_to_unified_columns`; `test_soft_is_renamed_drop` (`scrDefType="soft"` → `second_cov == "drop"`); `test_null_coverage_reads_none`; `test_null_location_gives_null_loc` (`location=None` → `loc_x` is NaN, row kept); `test_missing_family_is_skipped` (no `posts` key → no error); `test_control_moment_is_rejected_near_an_action`; `test_control_moments_are_reproducible_for_a_seed`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement both functions; the mapping table above is a module-level dict.
- [ ] **Step 4:** Run `uv run pytest tests/test_actions.py -v`. Expected: PASS.
- [ ] **Step 5:** Show the diff; propose `feat(actions): unify action events and sample control moments`.

---

### Task 5: Space created

**Files:**
- Create: `src/coverage_price/eventstudy.py`, `tests/test_eventstudy.py`

**Interfaces:**
- Consumes: `collect_actions` output, `openness` output, `OFFSETS`, `BASELINE_OFFSET`.
- Produces:
  - `eventstudy.frames_needed(actions: pd.DataFrame, offsets=OFFSETS) -> set[int]`
  - `eventstudy.sides_for(actions: pd.DataFrame, offsets=OFFSETS) -> pd.DataFrame` — the `sides` table for `openness`
  - `eventstudy.space_created(actions: pd.DataFrame, open_long: pd.DataFrame, offsets=OFFSETS, baseline=BASELINE_OFFSET) -> pd.DataFrame` — long: `action_id`, `game_id`, `kind`, `main_cov`, `second_cov`, `role`, `offset`, `baseline_ft`, `delta_ft`. Roles: `main`, `second`, `other_max` (most open of the offensive players who are neither main nor second), `team_mean`. A row exists only when both the baseline and the offset value are eligible for that role; `team_mean` and `other_max` need all contributing players eligible.

- [ ] **Step 1: Write failing tests:**

```python
START_GAP_FT, END_GAP_FT = 4.0, 9.0

def test_defender_leaving_gives_positive_space_created():
    # main player's only near defender moves from START_GAP_FT to END_GAP_FT between baseline and +25
    out = space_created(actions, open_long)
    row = out[(out.role == "main") & (out.offset == 25)].iloc[0]
    assert row.baseline_ft == pytest.approx(START_GAP_FT)
    assert row.delta_ft == pytest.approx(END_GAP_FT - START_GAP_FT)

def test_static_players_give_zero_for_every_role_and_offset():
def test_main_player_missing_at_baseline_drops_main_role_only():
def test_ineligible_offset_is_missing_not_zero():
def test_second_role_absent_when_action_has_no_second_player():
def test_other_max_excludes_main_and_second():
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Join actions × offsets to `open_long` on `frame = action.frame + offset`.
- [ ] **Step 4:** Run `uv run pytest tests/test_eventstudy.py -v`. Expected: PASS.
- [ ] **Step 5:** Show the diff; propose `feat(eventstudy): compute space created around actions`.

---

### Task 6: Summaries, ranges and the permutation test

**Files:**
- Modify: `src/coverage_price/eventstudy.py`
- Test: `tests/test_eventstudy.py`

**Interfaces:**
- Consumes: `space_created` output.
- Produces:
  - `eventstudy.summarise(space: pd.DataFrame, by: list[str], n_boot: int = 2000, seed: int = 0, min_n_for_range: int = 30) -> pd.DataFrame` — per group: `n`, `n_games`, `mean_delta_ft`, `lo`, `hi` (2.5/97.5 percentiles resampling games with replacement; NaN when `n < min_n_for_range` or `n_games < 2`), `mean_baseline_ft`.
  - `eventstudy.gap_between(space, label_col: str, a: str, b: str, n_boot=2000, seed=0) -> dict` — keys `gap_ft`, `lo`, `hi`, `games_same_sign`, `n_games`; the range resamples games.
  - `eventstudy.permutation_p(space, label_col: str, n_perm: int = 5000, seed: int = 0, min_n: int = 40) -> float` — between-group sum of squares against labels shuffled within `game_id`; `(count + 1) / (n_perm + 1)`.

All three expect `space` already filtered to one `kind`, `role` and `offset`.

- [ ] **Step 1: Write failing tests:**

```python
def test_summarise_reports_thin_groups_with_count_and_empty_range():
    # group "blitz" has 3 actions in 1 game
    row = summarise(space, by=["second_cov"]).set_index("second_cov").loc["blitz"]
    assert row.n == 3 and np.isnan(row.lo) and np.isnan(row.hi)

def test_summarise_range_contains_mean_for_a_well_populated_group():
def test_gap_between_counts_games_with_the_same_sign():      # 4 synthetic games, gap positive in all -> games_same_sign == 4
def test_permutation_p_is_small_for_a_planted_difference():  # planted 2 ft gap, n=200 per label -> p < 0.01
def test_permutation_p_is_not_small_for_identical_groups():  # same distribution -> p > 0.05
def test_results_are_reproducible_for_a_seed():
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the three functions with `numpy.random.default_rng(seed)`.
- [ ] **Step 4:** Run `uv run pytest tests/test_eventstudy.py -v`. Expected: PASS.
- [ ] **Step 5:** Show the diff; propose `feat(eventstudy): game-resampled ranges and within-game permutation test`.

---

### Task 7: Screener-defender depth

**Files:**
- Create: `src/coverage_price/depth.py`, `tests/test_depth.py`

**Interfaces:**
- Consumes: pick rows from `collect_actions` joined with the `picks` event table for `screenerDefId`; frames from `read_frames`; `HOOP_XY`.
- Produces:
  - `depth.orientation_sign(tracked_xy: tuple[float, float], event_xy: tuple[float, float]) -> int` — `+1` if the tracked position is nearer `event_xy`, `−1` if its point reflection through the origin is nearer.
  - `depth.screener_defender_depth(picks: pd.DataFrame, frames: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]` — table `action_id`, `depth_ft`; and skip counts keyed `null_location`, `player_not_tracked`. `picks` needs `action_id`, `frame`, `main_id`, `second_id`, `screener_def_id`, `loc_x`, `loc_y`.

`depth_ft` definition: after applying the orientation sign to all positions, let `u` be the unit vector from the screener to `HOOP_XY`. `depth_ft = (defender − screener) · u`. Positive means the defender is between the screener and the hoop (dropping); zero or negative means level with or above the screen (showing).

- [ ] **Step 1: Write failing tests:**

```python
DROP_FT = 6.0

def test_defender_between_screener_and_hoop_has_positive_depth():
    # screener at (-20, 0), defender at (-20 - DROP_FT, 0), event location matches tracking
    table, skipped = screener_defender_depth(picks, frames)
    assert table.depth_ft.iloc[0] == pytest.approx(DROP_FT)

def test_depth_is_unchanged_when_tracking_is_mirrored():   # same play with every tracked x, y negated -> same depth
def test_defender_above_the_screen_has_negative_depth():
def test_null_location_is_skipped_and_counted():           # skipped["null_location"] == 1, table empty
def test_untracked_defender_is_skipped_and_counted():
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Orientation is resolved from the ball handler's tracked position against the pick `location`.
- [ ] **Step 4:** Run `uv run pytest tests/test_depth.py -v`. Expected: PASS.
- [ ] **Step 5:** Show the diff; propose `feat(depth): label-free screener-defender depth`.

---

### Task 8: Season pricing

**Files:**
- Create: `src/coverage_price/pricing.py`, `tests/test_pricing.py`

**Interfaces:**
- Consumes: `data/aggregates/acb_picksaggregates_20252026.csv`.
- Produces: `pricing.price_by_coverage(picks_agg: pd.DataFrame) -> pd.DataFrame` — columns `role` (`handler`/`screener`), `coverage`, `picks`, `points_per_pick`, `score_rate`, `assist_rate`, `turnover_rate`. Handler coverages: `over`, `under`, `switch`, `ice`, `blitz`. Screener coverages: `drop` (source `soft`), `show`, `switch`, `ice`, `blitz`. Rows where `team_name == "total"` are excluded before summing. Each rate is the summed count (`{role}_points_vs_{cov}`, `_score_`, `_assist_`, `_turnover_`) over summed `{role}_picks_vs_{cov}`.

- [ ] **Step 1: Write failing tests:**

```python
def test_rates_are_summed_counts_over_summed_picks():
    # two player rows: 10 picks / 8 points and 30 picks / 12 points vs show -> 20 / 40 = 0.5
    out = price_by_coverage(agg).set_index(["role", "coverage"])
    assert out.loc[("screener", "show"), "points_per_pick"] == pytest.approx(0.5)
    assert out.loc[("screener", "show"), "picks"] == 40

def test_season_total_rows_are_not_double_counted():
def test_soft_is_reported_as_drop():
def test_coverage_with_zero_picks_has_nan_rates_not_an_error():
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest tests/test_pricing.py -v`. Expected: PASS.
- [ ] **Step 5:** Show the diff; propose `feat(pricing): season points per pick by coverage`.

---

### Task 9: Report, CLI and clean-install reproduction

**Files:**
- Create: `src/coverage_price/report.py`, `src/coverage_price/cli.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `report.run_game(game_dir: Path, aliases: dict[int, int], max_pred_error: float = MAX_PRED_ERROR_FT) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]` — space-created table (actions and controls), depth table, skip counts, for one game.
  - `report.build_tables(space: pd.DataFrame, depth: pd.DataFrame, prices: pd.DataFrame) -> dict[str, pd.DataFrame]` — keys `curves` (kind × coverage × role × offset), `pick_coverage` (role × coverage at offsets 25 and 50 with ranges and permutation p), `gaps` (show vs drop, under vs over), `controls`, `depth_by_label`, `depth_dose_response` (space created by depth bin: `< 0`, `0–3`, `3–6`, `> 6` ft), `prices`, `sensitivity` (show-vs-drop team-mean gap at baselines −10/−15/−25, offsets 25/40/50, gates 2/3/5 ft).
  - `report.figure_curves(tables, path: Path) -> None`, `report.figure_space_vs_points(tables, path: Path) -> None`
  - CLI: `coverage-price reproduce --data-dir data/opendata-basketball --out results [--max-pred-error 3.0]` writes `results/tables/*.csv`, `results/fig1_curves.png`, `results/fig2_space_vs_points.png`, `results/summary.json` (action counts by kind, eligible share by role, skip counts).

- [ ] **Step 1: Write failing tests:**

```python
def test_run_game_on_a_synthetic_game_returns_expected_shapes(tmp_path):   # one pick, static players -> all delta_ft == 0
def test_build_tables_has_every_documented_key(): 
def test_depth_dose_response_bins_are_ordered_and_counted():
def test_figures_are_written(tmp_path):                                    # both PNGs exist and are non-empty (matplotlib Agg backend)
def test_reproduce_fails_clearly_when_data_dir_is_missing(tmp_path):       # exit code 2, message names scripts/download_data.sh

@pytest.mark.skipif(not REAL_DATA.exists(), reason="open data not downloaded")
def test_real_game_openness_matches_supplied_shot_distance():
    # game 114243: nearest-defender distance at each shot's startFrame for the shooter
    # agrees with shots.closestDefDist; median absolute difference < 0.1 ft
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `report.py` and `cli.py` (argparse). Process one game at a time and concatenate; never hold more than one game's frames.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: PASS (real-data test skipped if data is absent).
- [ ] **Step 5:** Run `bash scripts/download_data.sh` then `uv run coverage-price reproduce --data-dir data/opendata-basketball --out results`. Expected: exits 0, files listed above exist, real-data test now passes. Note the wall-clock time in `docs/outline.md`.
- [ ] **Step 6:** Clean-environment check: in a fresh clone in a temporary directory, `uv sync && bash scripts/download_data.sh && uv run coverage-price reproduce ...`. Expected: identical `results/tables/*.csv` (compare with `diff -r`).
- [ ] **Step 7:** Show the diff; propose `feat: reproduce command, tables and figures`.

---

### Task 10: Results audit and writing outline

**Files:**
- Create: `docs/outline.md`

**Interfaces:**
- Consumes: `results/tables/*.csv`, `results/summary.json`.
- Produces: `docs/outline.md` for Adam.

- [ ] **Step 1:** Compare the package's numbers with the spec's provisional ones and record each side by side in `docs/outline.md`: team-mean space created at +1 s for show and drop; the show-vs-drop gap and its game-resampled range; games with the same sign; handler under vs over; control-moment change; season points per pick for the four headline cells. Flag any that moved by more than 0.2 ft or 0.02 points, with the reason (the eligibility gate is new and is the expected cause).
- [ ] **Step 2:** Record the three decisive checks and their outcomes: depth by label (is drop deeper than show?), depth dose-response (does space created fall as depth rises?), sensitivity table (does the show-vs-drop gap keep its sign in every cell?). If any fails, stop and report to Adam before writing further; the headline claim changes.
- [ ] **Step 3:** Add an argument outline for the README and video in bullet form only: question, method in three sentences, the two figures and what each shows, the known weaknesses from the spec, open-source potential (a `kloppy`-style loader contribution and the event-study engine). No finished prose; the rules require Adam's own words.
- [ ] **Step 4:** Add a submission checklist: README ≤ 1,000 words and ≤ 2 figures or tables; `LICENSE.md` present; data not committed; clean-install run passes; video ≤ 3 minutes, voiced by Adam; repository public; submitted at submissions.analytics-cup.org by 16 December.
- [ ] **Step 5:** Show the diff; propose `docs: results audit and writing outline`.
