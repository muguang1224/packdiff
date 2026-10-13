#!/usr/bin/env bash
# Regenerate docs/demo.gif.
#
# Needs two tools that are not project dependencies:
#   pip install asciinema
#   agg  (prebuilt binary from https://github.com/asciinema/agg/releases)
#
# It records a real session in a throwaway git repository: two files edited and
# one added, then `packdiff --diff` to show that only those three are packed.
# Note the `rm -f review.md` — without it a previous run's output is itself an
# untracked file, and --diff would dutifully pack the previous pack.
set -euo pipefail

DEMO=${DEMO:-/tmp/demo-api}
COLS=92
ROWS=24

cd "$DEMO"
rm -f review.md

P=$'\033[1;32mapi\033[0m \033[1;36m~\033[0m $ '
play() {
  printf '%s' "$P"; printf '%s\n' "$1"; sleep 1.1
  shift; "$@"; sleep 0.9
}

play 'git status --short'
printf '\n'
play 'packdiff --diff -o review.md' packdiff --diff -o review.md
printf '\n'
play 'head -22 review.md' head -22 review.md
sleep 2.2
