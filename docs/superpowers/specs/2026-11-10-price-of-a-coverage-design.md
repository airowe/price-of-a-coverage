# The Price of a Coverage — design

10 November 2026. Entry for the PySport Analytics Cup 2.0, basketball dataset, USA edition.
Submission deadline 18 December 2026; internal target 16 December.

## Question

When a defence chooses how to guard a ball screen, how much space does it give up,
to whom, for how long, and what is that worth in points?

## Why this question

Three throwaway tests on the 10 tracked games decided the direction.

| Test | Result |
|---|---|
| Does the defender's path (closing speed, angle) predict makes beyond the supplied `closestDefDist`? 1,278 unfouled shots, leave-one-game-out. | No. Log-loss change −0.0004, interval spans zero. The supplied distance itself barely registers (+0.007), so 10 games cannot resolve contest effects on makes. |
| Do the actions before a shot predict how open it is? 1,424 shots. | Yes, but coarsely. Held-out R² 0.21 from actions alone; most of it travels through shot type. Findings match common coaching knowledge. |
| Does openness change around each action, by coverage? 1,520 picks, about 4,000 actions in all. | Yes. Team-average openness one second after a screen: +0.93 ft against a show, +0.18 ft against a drop (`soft`). Gap 0.54–0.98 ft resampling whole games; same sign in 10 of 10 games. No-action control moments show no gain. |

Season aggregates agree on the points side: screeners score 0.306 points per direct pick
against a show (9,498 picks) and 0.216 against a drop (8,218); handlers 0.770 against
under (3,302) and 0.699 against over (14,501).

These figures come from throwaway scripts and must be reproduced by the package before
any of them is quoted in the submission.

## Competition constraints that shape the design

- Only the SkillCorner ACB 2025–26 dataset. No video and no outside data; either is
  disqualifying. Nothing from TheLowPost's data or code is used.
- Substantial new work. All code is written for this entry.
- Public GitHub repository, open-source licence, `LICENSE.md`, runs out of the box,
  no proprietary software, data not committed.
- `README.md` of at most 1,000 words and two figures or tables in total, written in the
  entrant's own words.
- YouTube video of at most three minutes, presented and voiced by the entrant.
- Judged equally on relevance, methodology, originality, communication and
  open-source potential.

## Terms

- **Openness**: distance in feet from an offensive player to the nearest defender in
  one tracking frame.
- **Action**: a SkillCorner dynamic event with a frame: pick, handoff, off-ball
  screen, drive, isolation, post.
- **Coverage**: SkillCorner's label for how a defender played the action
  (`bhrDefType`, `scrDefType` and equivalents). `soft` is reported as **drop**.
- **Space created**: openness at a time after the action minus openness 0.6 s before it.
- **Eligible**: a measurement whose tracking quality passes the gate below. Anything
  else is **ineligible** and is excluded, never treated as zero.

## Components

Each unit has one job and is tested on its own.

### 1. `loader`

Reads one game folder into typed tables: game metadata and rosters, each dynamic-event
family, and tracking frames.

- Tracking is read as a stream and only requested frames are parsed, so a game never
  has to fit in memory as Python objects.
- Dead-ball frames (empty player lists) are dropped at read time.
- `player_id_aliases.csv` is applied so each player has one id.
- Data location comes from an argument or environment variable. A helper script
  downloads the open-data repository including its large files.

### 2. `openness`

For a set of frames, returns one row per offensive player per frame: nearest-defender
distance, that defender's id, and an eligibility flag.

- Eligibility uses SkillCorner's own `predError` for both the offensive player and
  the nearest defender. Default gate: both `predError` ≤ 3 ft. `isDetected` is read but
  not part of the gate: `predError` already rises for extrapolated positions.
  The threshold is a parameter and its effect is reported.
- Fewer than five players tracked on either side makes the whole frame ineligible.

### 3. `eventstudy`

For each action, samples openness from 1.0 s before to 3.0 s after at 0.2 s steps and
returns the change from the 0.6 s-before baseline for four roles: main player,
screener or setter, most open other teammate, and team average.

- A window stops at the end of the action's chance.
- Aggregates by action type and coverage.
- Uncertainty by resampling whole games, since actions within a possession are not
  independent.
- Coverage differences tested by shuffling labels within each game.
- Reports per-game values so consistency is visible, with coverage counts so thin
  cells (blitz, ice) are shown as thin rather than hidden.

### 4. `depth` (label-free check)

Measures, at the moment of each pick, how far the screener's defender stands from the
screen along the line to the hoop, in feet. Two uses:

- Confirms the reading of the labels: drop should sit below the screen, show at or
  above it.
- Gives a result that does not depend on the labels: space created as a function of
  depth. A steady rise with depth supports the main finding independently.

The tracking frame is camera-oriented while event locations are normalised to the
offensive hoop. A pick's `location` is the screener's position; tracking x is mirrored
when the offence attacks the other hoop and tracking y is the event y negated. Depth
needs only the x mirror, taken from the screener. (Corrected after code review: the
first version assumed a point reflection matched on the ball handler.) Hoop position is (−40.76, 0) ft in the
normalised frame; the spike confirmed this against the supplied shot distances.

### 5. `pricing`

From the season pick aggregates: points per direct pick, own-score rate, assist rate
and turnover rate by coverage, separately for handler and screener, summed over
player rows with season-total rows excluded.

Stated limits: direct picks only (about 52% of all picks), offense only, and no
crossing of handler coverage with screener coverage.

### 6. `report`

Builds the two figures and a results table file.

- Figure 1: space-created curves for ball screens by screener coverage, one panel per
  role, with resampled ranges.
- Figure 2: space created against season points per pick, by coverage and role.

One command reproduces every quoted number and both figures from a clean install.

## Scope

In:

- Ball screens as the headline result.
- Off-ball screens, handoffs and drives through the same engine as supporting results.

Out:

- Per-player or per-team rankings. Ten games cannot support them.
- Any predictive model of makes or shot quality.
- Court animations or an interactive app. A single replay clip may be made for the
  video only if time allows.

## Controls and checks

- No-action moments sampled from live half-court play, expected to show no gain.
- Coverage labels shuffled within game as the null for differences.
- Sign consistency across the 10 games.
- Sensitivity to baseline offset, time horizon and the eligibility threshold.
- A known-answer test for each metric: synthetic frames with a defender at a set
  distance must return that distance, and a synthetic "defender leaves" sequence must
  return a positive space created.

## Known weaknesses to state openly

- Coverage labels are derived by SkillCorner from the same tracking, so the screener's
  own gain against a show is close to definitional. The teammate and team-average
  results, and the depth result, carry the claim.
- Openness is not points. The link to scoring is by coverage at season level, not
  action by action.
- Ten games, one league, one season.
- Starting openness differs slightly by coverage, so some regression toward the mean
  is possible; baseline levels are reported beside every change.

## Technology

- Python package with a `src` layout, installed with `uv`; pandas and numpy for data,
  matplotlib for figures, pytest for tests, ruff for lint and format.
- MIT licence.
- Tests written first for each component. Pure-logic tests use small synthetic frames;
  one integration test runs against a real game when the data is present and is
  skipped otherwise.
- No notebooks in the reproduction path.

## Division of work

- Code, tests, figures, numbers and an outline of the argument: produced in this project.
- README text and the video: written and recorded by the entrant, as the rules require.

## Schedule

| Week of | Work |
|---|---|
| 10 Nov | Repository, loader, openness, with tests |
| 17 Nov | Event study and controls |
| 24 Nov | Depth check, pricing, figures |
| 1 Dec | README and video |
| 8 Dec | Clean-install test, buffer, submit by 16 Dec |

## Open items for the entrant

- Confirm solo entry, USA edition, and in-person attendance in Boston on 24 February 2027.
- Register on the competition site and join the Discord, where rule clarifications are posted.
- Choose the public repository name.
