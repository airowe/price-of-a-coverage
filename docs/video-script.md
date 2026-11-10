# Video script: The Price of a Coverage

Limit: three minutes, presented and voiced by you. The spoken lines total 413 words: about 2.8 minutes
at a measured 150 words a minute. Time yourself once before recording; if you run past
2:50, cut the "What it doesn't show" section to its first sentence.

Every number here matches the README and `results/tables/`. If you change a number in
one place, change it in the other: the rules ask for the README and video to agree.

Clips to record or export first:

- `results/replay_show.gif` and `results/replay_drop.gif` (re-export as `.mp4` with
  `uv run coverage-price replay --coverage show --out results/replay_show.mp4`)
- `results/fig1_curves.png` and `results/fig2_space_vs_points.png`
- A screen recording of `uv run coverage-price reproduce` finishing (about 16 seconds)

---

## 0:00 – 0:20 · The question

**On screen:** you on camera, then the show replay clip.

> Every basketball team has to decide how to guard a ball screen. Drop the big man
> back, have him show at the ball, or switch. I'm Adam Rowe, and my project asks a
> simple question about that choice: how much space does each coverage give up, to
> whom, and for how long?

## 0:20 – 0:45 · Why this problem

**On screen:** you on camera.

> I didn't start here. My first idea was that how fast a defender closes out would
> predict makes better than how close he is. Ten games couldn't show it: makes are too
> rare and too noisy. Space isn't. Tracking gives you the distance to the nearest
> defender for every player, twenty-five times a second. So I stopped asking whether
> the shot went in, and asked what created the room to take it.

## 0:45 – 1:25 · How it works

**On screen:** the drop replay clip, then a slow scroll of Figure 1's axes.

> For every offensive player, in every frame, I measure the distance to the nearest
> defender, and keep it only when SkillCorner's own error estimate says the tracking
> is good.
>
> Then, for each of fifteen hundred ball screens, I compare that distance just before
> the screen with the three seconds after it. That change is the space created.
>
> Two things keep it honest. The ranges come from resampling whole games, not single
> plays. And because the coverage labels come from the same tracking, I also measured
> how far below the screen the big man's defender stands, with no labels at all.

## 1:25 – 2:15 · What I found

**On screen:** Figure 1, then Figure 2.

> One second after the screen, a show has opened about one foot of space per offensive
> player. A drop has opened about a third of a foot. That gap shows up in all ten
> games.
>
> Against a show the screener gains a foot and a half and the most open teammate two
> feet. And the ball handler isn't contained: two seconds later he's nearly as free as
> when he started.
>
> The label-free check agrees. The deeper that defender plays, the less space opens,
> down to nothing beyond six feet.
>
> And space lines up with scoring. Across the full season, screeners score about forty
> percent more per pick against a show than against a drop.

## 2:15 – 2:35 · What it doesn't show

**On screen:** you on camera.

> A caution. Teams choose their coverage, so this describes what happened, not what
> would happen if a team switched. And it's ten games from one league.

## 2:35 – 2:50 · Open source

**On screen:** the terminal recording of `reproduce` finishing, then the repository page.

> Everything reproduces with one command in under a minute. The package has three
> reusable parts: a loader for SkillCorner's basketball data, the space measure, and
> an engine that works for any action. Next, I'd contribute the loader to kloppy and
> run this on a full season. Thanks for watching.

---

## Checks behind the spoken numbers

| Line in the script | Source |
|---|---|
| "about one foot" / "about a third of a foot" | Team average at +1 s: show +0.99 ft, drop +0.31 ft |
| "all ten games" | Show minus drop, team average, +1 s: same sign in 10 of 10 |
| "a foot and a half" | Screener at +1 s against a show: +1.54 ft |
| "two feet" | Most open teammate at +1 s against a show: +1.97 ft |
| "nearly as free as when he started" | Handler at +2 s against a show: −0.22 ft (range −0.65 to +0.24) |
| "nothing beyond six feet" | Team average at +1 s, defender deeper than 6 ft: +0.05 ft (range −0.16 to +0.20) |
| "about forty percent more" | Season points per pick, screener: 0.306 against a show, 0.217 against a drop (+41%) |
| "fifteen hundred ball screens" | 1,520 picks |
| "under a minute" | About 16 seconds on a laptop, plus the one-time data download |

Two wording notes:

- "The deeper that defender plays, the less space opens" is true from 3 ft down. The two
  shallowest groups (above the screen, and 0–3 ft below it) both sit at about 1 ft and
  can't be told apart. If you have a spare second, "once he's more than three feet below
  the screen" is the precise version.
- I say "contributing the loader to kloppy" as a next step. kloppy's documentation shows
  SkillCorner support for football only; I didn't read its source code, so don't claim
  on camera that it definitely lacks basketball support.
