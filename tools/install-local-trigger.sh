#!/bin/bash
# Install the launchd agent that dispatches the tracker every 30 minutes.
set -euo pipefail
LABEL="com.harryjoyce.gb-update-tracker"
SRC="$(cd "$(dirname "$0")" && pwd)/${LABEL}.plist"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

mkdir -p "${HOME}/Library/LaunchAgents"
cp "$SRC" "$DEST"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed and loaded ${LABEL} (every 30 minutes)."
echo "Log: ~/Library/Logs/gb-update-tracker.log"
