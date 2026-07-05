#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="$REPO_DIR/config.json"

if [[ ! -f "$CONFIG_PATH" ]]; then
  cp "$REPO_DIR/config.example.json" "$CONFIG_PATH"
fi

mkdir -p "$HOME/office-room-agent-data"/{images,logs,reports,state}

sudo systemctl enable --now pigpiod
sudo systemctl disable --now office-room-agent.service 2>/dev/null || true
sudo install -m 0644 "$REPO_DIR/systemd/office-room-agent.service" /etc/systemd/system/office-room-agent.service
sudo install -m 0644 "$REPO_DIR/systemd/office-room-agent.timer" /etc/systemd/system/office-room-agent.timer
sudo install -m 0644 "$REPO_DIR/systemd/office-room-agent-archive.service" /etc/systemd/system/office-room-agent-archive.service
sudo install -m 0644 "$REPO_DIR/systemd/office-room-agent-archive.timer" /etc/systemd/system/office-room-agent-archive.timer
sudo systemctl daemon-reload
sudo systemctl enable --now office-room-agent.timer
sudo systemctl enable --now office-room-agent-archive.timer

systemctl status office-room-agent.timer --no-pager
systemctl status office-room-agent-archive.timer --no-pager
