# Office Room Agent Skill

Use this skill when maintaining the `pi4book` office camera agent in `~/code/projects/office-room-agent`.

## Final Known-Good Setup

- Use one calibrated video sweep only: `top_right -> bottom_left`.
- Coordinates:
  - `top_left`: `pan=45`, `tilt=-15`
  - `top_right`: `pan=0`, `tilt=-15`
  - `bottom_left`: `pan=45`, `tilt=10`
  - `bottom_right`: `pan=0`, `tilt=10`
- Use `pigpio.set_servo_pulsewidth()`, not generic `set_PWM_dutycycle()`.
- Pulse range: `500us..2500us`.
- Servo pins:
  - pan: BCM 13
  - tilt: BCM 12
- Camera orientation: `--hflip --vflip`.
- Runtime data stays outside the repo under `~/office-room-agent-data`.
- Archive target is `192.168.1.108:/mnt/nas02/office-room-agent-archive/pi4book/`.

## Important Learnings

- Vilib and the pan-tilt-hat examples do not provide servo telemetry. They only write servo commands.
- Pigpio readback APIs are available and useful:
  - `get_PWM_dutycycle()` for old PWM-duty mode
  - `get_servo_pulsewidth()` for final pulsewidth mode
  - `get_PWM_frequency()` and `get_PWM_range()` for diagnostics
- PWM-duty telemetry looked clean but physical video still glitched.
- Pulsewidth mode also showed clean telemetry and produced the accepted smooth clip:
  - `~/office-room-agent-data/videos/2026-07-05/20260705_010544_335333_sweep.mp4`
- `vcgencmd get_throttled` stayed `throttled=0x0` during tests, so the observed glitch was not a Pi-level undervoltage event.
- If jitter returns, suspect mechanical/base movement, servo power delivery, or servo gear backlash before changing software paths.

## Do Not Reintroduce

- Do not restore the old 3x3 still-photo scan as the default.
- Do not restore multi-corner loop video sweeps.
- Do not restore row-sweep rotation as the default.
- Do not switch back to `set_PWM_dutycycle()` unless explicitly testing a regression.
- Do not center the PTZ after every recording; extra unrecorded movement can shift the base.

## Manual Validation

Before resuming the timer after changes:

```bash
sudo systemctl stop office-room-agent.timer office-room-agent.service
cd ~/code/projects/office-room-agent
python3 -m office_room_agent --config ./config.json --duration-seconds 20
tail -1 ~/office-room-agent-data/logs/captures-$(date +%F).csv
```

Check the produced MP4 under:

```text
~/office-room-agent-data/videos/YYYY-MM-DD/
```
