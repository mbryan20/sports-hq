#!/usr/bin/env bash
# Commit and push whatever the last pass wrote. Safe to call when nothing changed.
git config user.name "sports-hq-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
mkdir -p state
git add docs/data state
git commit -q -m "data: $(date -u +%FT%TZ)" || { echo "nothing to commit"; exit 0; }
for i in 1 2 3; do git pull -q --rebase -X theirs && git push -q && exit 0; sleep 5; done
exit 1
