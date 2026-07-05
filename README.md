# Office Room Agent

Pan/tilt camera agent for `pi4book`. Every 10 minutes, systemd starts a 15-second capture window. During that window it captures timestamped images every five seconds, steps through configured pan/tilt positions, records each capture to a daily CSV, writes errors to a separate log, and generates a daily markdown report with observation notes.

Runtime data is intentionally outside the repo:

- Images: `~/office-room-agent-data/images/YYYY-MM-DD/`
- Capture CSV logs: `~/office-room-agent-data/logs/captures-YYYY-MM-DD.csv`
- Error log: `~/office-room-agent-data/logs/agent-errors.log`
- Reports: `~/office-room-agent-data/reports/report-YYYY-MM-DD.md`

Artifacts are also archived every minute to NVMe storage on `pi5d05`:

- Archive target: `192.168.1.108:/mnt/nas02/office-room-agent-archive/pi4book/`
- Archive log: `~/office-room-agent-data/logs/archive.log`

## Hardware Defaults

- Pan servo: BCM GPIO 13
- Tilt servo: BCM GPIO 12
- Camera orientation: `hflip=true`, `vflip=true`
- Capture cadence while active: 5 seconds
- Activation cadence: 15 seconds every 10 minutes

These defaults came from the existing `ptz-cli` setup on this host.

## Commands

Install and start the service:

```bash
./scripts/install_service.sh
```

Check service status:

```bash
systemctl status office-room-agent.timer --no-pager
systemctl status office-room-agent-archive.timer --no-pager
systemctl list-timers office-room-agent.timer
systemctl list-timers office-room-agent-archive.timer
```

Watch logs:

```bash
journalctl -u office-room-agent.service -f
journalctl -u office-room-agent-archive.service -f
tail -f ~/office-room-agent-data/logs/agent-errors.log
tail -f ~/office-room-agent-data/logs/archive.log
```

Run one scan pass manually:

```bash
sudo systemctl stop office-room-agent.service
python3 -m office_room_agent --config ./config.json --once
```

Run one 15-second capture window manually:

```bash
python3 -m office_room_agent --config ./config.json --duration-seconds 15
```

Generate or refresh a report:

```bash
python3 -m office_room_agent --config ./config.json --report "$(date +%F)"
```

## Notes

The observation fields are heuristic. The agent estimates lights from image brightness, estimates people with OpenCV body and face detectors, and infers likely activity from visible people plus frame-to-frame motion. It does not identify people.
