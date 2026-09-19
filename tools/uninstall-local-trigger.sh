#!/bin/bash
# Remove the launchd agent. Run this once GitHub's own scheduler works again,
# or when the rollout is finished and the tracker is no longer needed.
set -euo pipefail
LABEL="com.harryjoyce.gb-update-tracker"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$DEST"
echo "Removed ${LABEL}. The dashboard will stop updating automatically."
echo "Logs left in place: ~/Library/Logs/gb-update-tracker*.log"
