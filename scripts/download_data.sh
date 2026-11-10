#!/usr/bin/env bash
# Download the SkillCorner ACB 2025-26 open data (about 400 MB) into data/opendata-basketball,
# at the exact version the published numbers were computed from.
#
#   bash scripts/download_data.sh [destination]
#   DATA_REF=<commit> bash scripts/download_data.sh    # use a different data version
set -euo pipefail

repo="https://github.com/SkillCorner/opendata-basketball.git"
pinned="4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66" # SkillCorner/opendata-basketball, 2026-09-10
ref="${DATA_REF:-$pinned}"
dest="${1:-data/opendata-basketball}"

if ! command -v git-lfs >/dev/null 2>&1; then
  echo "git-lfs is required for the tracking files: https://git-lfs.com" >&2
  exit 1
fi

export GIT_LFS_SKIP_SMUDGE=1 # fetch the large files once, explicitly, at the end
if [ ! -d "$dest/.git" ]; then
  git init -q "$dest"
  git -C "$dest" remote add origin "$repo"
fi
if [ "$(git -C "$dest" rev-parse -q --verify HEAD 2>/dev/null || true)" != "$ref" ]; then
  git -C "$dest" fetch -q --depth 1 origin "$ref"
  git -C "$dest" checkout -q --detach FETCH_HEAD
fi
git -C "$dest" lfs install --local >/dev/null
git -C "$dest" lfs pull

actual="$(git -C "$dest" rev-parse HEAD)"
if [ "$actual" != "$ref" ]; then
  echo "Expected data version $ref but have $actual" >&2
  exit 1
fi
echo "Data ready in $dest (version ${actual:0:7})"
