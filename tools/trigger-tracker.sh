#!/bin/bash
# Dispatch the tracker workflow on GitHub.
#
# Stopgap for GitHub not delivering scheduled events to this repository: a
# minimal probe workflow (*/10, one echo, state active) never fired either, so
# the fault is repository/account level rather than in our workflow files.
#
# This only *triggers* the run -- the checking, committing and pushing all stay
# in GitHub Actions, which works fine via push and workflow_dispatch. That
# keeps one code path rather than a second, divergent local one.
#
# Driven by ~/Library/LaunchAgents/com.harryjoyce.gb-update-tracker.plist.
# Remove with: tools/uninstall-local-trigger.sh

set -uo pipefail

# launchd gives a job almost no environment, so PATH must be explicit.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

REPO="harry-joyce/gb-update"
WORKFLOW="track.yml"
LOG="${HOME}/Library/Logs/gb-update-tracker.log"
mkdir -p "$(dirname "$LOG")"

stamp() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

if ! command -v gh >/dev/null 2>&1; then
  echo "$(stamp)  ERROR  gh not found on PATH" >> "$LOG"
  exit 1
fi

out=$(gh workflow run "$WORKFLOW" --repo "$REPO" 2>&1)
status=$?

if [ $status -eq 0 ]; then
  echo "$(stamp)  ok     dispatched $WORKFLOW" >> "$LOG"
else
  echo "$(stamp)  ERROR  dispatch failed ($status): ${out//$'\n'/ }" >> "$LOG"
fi

# Keep the log from growing without bound over a long run.
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 500 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

exit $status
