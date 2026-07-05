# Office Room Agent

Pan/tilt camera agent for `pi4book`. It captures a timestamped image every five seconds, steps through configured pan/tilt positions, records each capture to a daily CSV, writes errors to a separate log, and generates a daily markdown report with observation notes.

Runtime data is intentionally outside the repo:

- Images: `~/office-room-agent-data/images/YYYY-MM-DD/`
- Capture CSV logs: `~/office-room-agent-data/logs/captures-YYYY-MM-DD.csv`
- Error log: `~/office-room-agent-data/logs/agent-errors.log`
- Reports: `~/office-room-agent-data/reports/report-YYYY-MM-DD.md`

## Hardware Defaults

- Pan servo: BCM GPIO 13
- Tilt servo: BCM GPIO 12
- Camera orientation: `hflip=true`, `vflip=true`
- Capture cadence: 5 seconds

These defaults came from the existing `ptz-cli` setup on this host.

## Commands

Install and start the service:

```bash
./scripts/install_service.sh
```

Check service status:

```bash
systemctl status office-room-agent.service --no-pager
```

Watch logs:

```bash
journalctl -u office-room-agent.service -f
tail -f ~/office-room-agent-data/logs/agent-errors.log
```

Run one scan pass manually:

```bash
sudo systemctl stop office-room-agent.service
python3 -m office_room_agent --config ./config.json --once
```

Generate or refresh a report:

```bash
python3 -m office_room_agent --config ./config.json --report "$(date +%F)"
```

## Notes

The observation fields are heuristic. The agent estimates lights from image brightness, estimates people with OpenCV body and face detectors, and infers likely activity from visible people plus frame-to-frame motion. It does not identify people.
