# Office Room Agent

Calibrated Raspberry Pi camera agent for `pi4book`. Every 10 minutes, systemd starts one bounded capture window. The agent records a timestamped MP4 while moving the pan/tilt camera across the accepted office bounding box, logs the capture to CSV, writes error and power-status logs, generates a daily markdown report, and archives artifacts to NVMe storage on `pi5d05`.

## Final Capture Approach

The final working approach is a single diagonal video sweep from top-right to bottom-left of the calibrated room rectangle:

- Top-left: `pan=45`, `tilt=-15`
- Top-right: `pan=0`, `tilt=-15`
- Bottom-left: `pan=45`, `tilt=10`
- Bottom-right: `pan=0`, `tilt=10`
- Active path: `top_right -> bottom_left`
- Sweep duration: `20s`
- Pre-record settle: `5s`
- Servo update cadence: `120ms`
- Servo easing: smoothstep ease-in/ease-out

The agent intentionally does not run old 3x3 still-photo scans, row-sweep clips, or fixed-view fallback clips. Those were useful during calibration but caused poor coverage, visible jitter, or no motion.

## Glitch Removal

The original implementation used `pigpio.set_PWM_dutycycle()` with a 50 Hz range of `10000`. Motion looked smooth in command telemetry but still glitched physically. The useful fix was to drive the servos with pigpio's dedicated hobby-servo API:

- `set_servo_pulsewidth()`
- `pulse_min_us=500`
- `pulse_max_us=2500`

Telemetry from `~/office-room-agent-data/logs/pulsewidth-diagonal-telemetry-20260705-010500.csv` showed stable command/readback values, no pulse spikes, no timing stalls, and `throttled=0x0`. The confirmed smooth test video was:

```text
~/office-room-agent-data/videos/2026-07-05/20260705_010544_335333_sweep.mp4
```

If jitter returns, first check mechanical stability, servo power, and the telemetry logs before changing the sweep path.

## Runtime Data

Runtime data is intentionally outside the repo:

- Videos: `~/office-room-agent-data/videos/YYYY-MM-DD/`
- Thumbnail images: `~/office-room-agent-data/images/YYYY-MM-DD/`
- Capture CSV logs: `~/office-room-agent-data/logs/captures-YYYY-MM-DD.csv`
- Error and power log: `~/office-room-agent-data/logs/agent-errors.log`
- Reports: `~/office-room-agent-data/reports/report-YYYY-MM-DD.md`

Artifacts are archived every minute to NVMe storage on `pi5d05`:

- Archive target: `192.168.1.108:/mnt/nas02/office-room-agent-archive/pi4book/`
- Archive log: `~/office-room-agent-data/logs/archive.log`

## Hardware

- Pan servo: BCM GPIO 13
- Tilt servo: BCM GPIO 12
- Camera orientation: `hflip=true`, `vflip=true`
- Camera output: 1280x720 MP4
- Servo control: pigpio pulsewidth mode

These pins and orientation came from the existing `~/code/projects/ptz-cli` and `~/code/camera/pan-tilt-hat` setup on `pi4book`.

## Commands

Install and start timers:

```bash
./scripts/install_service.sh
```

Check status:

```bash
systemctl status office-room-agent.timer --no-pager
systemctl status office-room-agent-archive.timer --no-pager
systemctl list-timers office-room-agent.timer
systemctl list-timers office-room-agent-archive.timer
```

Run one calibrated sweep manually:

```bash
sudo systemctl stop office-room-agent.timer office-room-agent.service
python3 -m office_room_agent --config ./config.json --duration-seconds 20
```

Watch logs:

```bash
journalctl -u office-room-agent.service -f
tail -f ~/office-room-agent-data/logs/agent-errors.log
tail -f ~/office-room-agent-data/logs/archive.log
```

Generate or refresh a report:

```bash
python3 -m office_room_agent --config ./config.json --report "$(date +%F)"
```

## Notes

The observation fields are heuristic. The agent estimates lights from image brightness, estimates people with OpenCV body and face detectors, and infers likely activity from visible people plus frame-to-frame motion. It does not identify people.
