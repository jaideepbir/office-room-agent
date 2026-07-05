#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-$HOME/office-room-agent-data/}"
ARCHIVE_TARGET="${ARCHIVE_TARGET:-192.168.1.108:/mnt/nas02/office-room-agent-archive/pi4book/}"
LOG_DIR="${LOG_DIR:-$HOME/office-room-agent-data/logs}"
LOG_FILE="$LOG_DIR/archive.log"
LOCK_FILE="${LOCK_FILE:-/tmp/office-room-agent-archive.lock}"

mkdir -p "$LOG_DIR"

{
  flock -n 9 || {
    printf '%s archive already running\n' "$(date --iso-8601=seconds)"
    exit 0
  }

  printf '%s archive start source=%s target=%s\n' "$(date --iso-8601=seconds)" "$SOURCE_DIR" "$ARCHIVE_TARGET"
  rsync -a --partial --mkpath \
    --exclude 'logs/archive.log' \
    -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
    "$SOURCE_DIR" "$ARCHIVE_TARGET"
  printf '%s archive complete\n' "$(date --iso-8601=seconds)"
} 9>"$LOCK_FILE" >>"$LOG_FILE" 2>&1
