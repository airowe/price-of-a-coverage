#!/usr/bin/env bash
# Download the SkillCorner ACB 2025-26 open data (about 400 MB) into data/opendata-basketball.
set -euo pipefail
dest="${1:-data/opendata-basketball}"
if ! command -v git-lfs >/dev/null 2>&1; then
  echo "git-lfs is required for the tracking files: https://git-lfs.com" >&2
  exit 1
fi
if [ ! -d "$dest/.git" ]; then
  GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/SkillCorner/opendata-basketball.git "$dest"
fi
git -C "$dest" lfs install --local
git -C "$dest" lfs pull
echo "Data ready in $dest"
