# The Price of a Coverage

Draft. The write-up goes here; see `docs/outline.md` for the numbers and structure.

## Reproduce

```bash
uv sync
bash scripts/download_data.sh
uv run coverage-price reproduce --data-dir data/opendata-basketball --out results
```

Requires `uv`, `git` and `git-lfs`. Data: SkillCorner ACB 2025-26 open data (not included).
