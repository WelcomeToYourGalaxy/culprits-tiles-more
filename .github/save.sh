#!/usr/bin/env bash
# Commits and pushes whatever the step before it changed, then asks Pages to
# republish. Used by every job in refresh.yml. Files over 95 MB are left out
# (GitHub refuses files over 100 MB) and named in the log.
set -u
msg="$1"
git config user.name "culprits-refresh"
git config user.email "actions@users.noreply.github.com"
# Python's cache files are never saved (23 September: one left in an old
# checkout clashed with main, where they had been removed, and the save was
# stuck on that clash for all eight tries).
git rm -r -q --cached --ignore-unmatch scripts/__pycache__ >/dev/null 2>&1 || true
find . -path ./.git -prune -o -name __pycache__ -type d -print0 | xargs -0 rm -rf
git add -A
git diff --cached --name-only -z | while IFS= read -r -d '' f; do
  if [ -f "$f" ] && [ "$(stat -c %s "$f")" -gt 99614720 ]; then
    echo "$f is over 95 MB; left out."
    git reset -q -- "$f"
  fi
done
if git diff --cached --quiet; then echo "Nothing changed."; exit 0; fi
git commit -q -m "$msg"
for i in 1 2 3 4 5 6 7 8; do
  # --autostash: a file left out for size (over 95 MB) stays changed in the
  # working tree, and a plain rebase refuses to run over it - every save on
  # 22 September failed that way, eight tries each, and nothing was kept.
  if git pull -q --rebase --autostash -X theirs origin main && git push -q; then
    echo "Saved."
    gh api -X POST "repos/$REPO/pages/builds" >/dev/null 2>&1 || echo "Pages will republish on its own."
    exit 0
  fi
  # A rebase that stopped on a clash is undone before the next try; left
  # half-done, every later pull refused to run ("unmerged files").
  git rebase --abort >/dev/null 2>&1 || true
  echo "Push attempt $i did not go through; trying again."
  sleep $((RANDOM % 20 + 5))
done
echo "Could not push after 8 tries."
exit 1
