#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    import pigpio
except Exception:
    pigpio = None


FIELDS = [
    "timestamp",
    "date",
    "position",
    "pan",
    "tilt",
    "image_path",
    "lights_on",
    "avg_brightness",
    "person_count",
    "multiple_people",
    "likely_activity",
    "motion_score",
    "status",
    "error",
]


@dataclass
class ServoState:
    pan: float = 0.0
    tilt: float = 0.0


class OfficeRoomAgent:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self.load_config(config_path)
        self.data_dir = Path(self.config["data_dir"]).expanduser()
        self.image_dir = self.data_dir / "images"
        self.log_dir = self.data_dir / "logs"
        self.report_dir = self.data_dir / "reports"
        self.state_dir = self.data_dir / "state"
        for path in (self.image_dir, self.log_dir, self.report_dir, self.state_dir):
            path.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            filename=str(self.log_dir / "agent-errors.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        self.stop_requested = False
        self.servo_state = ServoState()
        self.pi = None
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.previous_gray = None
        self.current_date = self.local_now().date()

    @staticmethod
    def load_config(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def local_now() -> dt.datetime:
        return dt.datetime.now().astimezone()

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        self.write_startup_note()
        positions = self.config["scan_positions"]
        interval = float(self.config["capture_interval_seconds"])
        index = 0
        while not self.stop_requested:
            started = time.monotonic()
            now = self.local_now()
            if now.date() != self.current_date:
                self.write_daily_report(self.current_date)
                self.current_date = now.date()
                self.previous_gray = None
            position = positions[index % len(positions)]
            index += 1
            row = self.capture_position(position)
            self.append_csv(row)
            elapsed = time.monotonic() - started
            self.sleep_interruptible(max(0.0, interval - elapsed))
        self.write_daily_report(self.current_date)
        self.center_servos()
        self.close_servo()

    def request_stop(self, _signum, _frame) -> None:
        self.stop_requested = True

    def sleep_interruptible(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self.stop_requested and time.monotonic() < deadline:
            time.sleep(min(0.2, deadline - time.monotonic()))

    def write_startup_note(self) -> None:
        logging.info("office room agent starting with config %s", self.config_path)

    def capture_position(self, position: dict[str, Any]) -> dict[str, Any]:
        now = self.local_now()
        stamp = now.strftime("%Y%m%d_%H%M%S_%f")
        day_dir = self.image_dir / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        image_path = day_dir / f"{stamp}_{position['name']}.jpg"
        row = {
            "timestamp": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            "position": position["name"],
            "pan": position["pan"],
            "tilt": position["tilt"],
            "image_path": str(image_path),
            "lights_on": "",
            "avg_brightness": "",
            "person_count": "",
            "multiple_people": "",
            "likely_activity": "",
            "motion_score": "",
            "status": "ok",
            "error": "",
        }
        try:
            self.move_servos(float(position["pan"]), float(position["tilt"]))
            time.sleep(float(self.config["servo"]["settle_seconds"]))
            self.take_photo(image_path)
            row.update(self.observe(image_path))
        except Exception as exc:
            row["status"] = "error"
            row["error"] = repr(exc)
            logging.exception("capture failed at %s", position["name"])
        return row

    def ensure_servo(self):
        servo_cfg = self.config["servo"]
        if not servo_cfg.get("enabled", True):
            return None
        if pigpio is None:
            raise RuntimeError("pigpio Python module is not available")
        if self.pi and self.pi.connected:
            return self.pi
        self.pi = pigpio.pi()
        if not self.pi.connected:
            subprocess.run(["sudo", "pigpiod"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.3)
            self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon is not running")
        return self.pi

    @staticmethod
    def clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def map_angle(angle: float, in_min=-90.0, in_max=90.0, out_min=250.0, out_max=1250.0) -> float:
        return (angle - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def set_servo(self, pin: int, angle: float) -> None:
        pi = self.ensure_servo()
        if pi is None:
            return
        pi.set_PWM_frequency(pin, 50)
        pi.set_PWM_range(pin, 10000)
        pi.set_PWM_dutycycle(pin, self.map_angle(angle))

    def move_servos(self, pan: float, tilt: float) -> None:
        servo_cfg = self.config["servo"]
        if not servo_cfg.get("enabled", True):
            return
        pan = self.clamp(pan, float(servo_cfg["pan_min"]), float(servo_cfg["pan_max"]))
        tilt = self.clamp(tilt, float(servo_cfg["tilt_min"]), float(servo_cfg["tilt_max"]))
        steps = max(1, int(float(servo_cfg["smooth_move_ms"]) / 20))
        start_pan = self.servo_state.pan
        start_tilt = self.servo_state.tilt
        for i in range(1, steps + 1):
            p = start_pan + (pan - start_pan) * i / steps
            t = start_tilt + (tilt - start_tilt) * i / steps
            self.set_servo(int(servo_cfg["pan_pin"]), p)
            self.set_servo(int(servo_cfg["tilt_pin"]), t)
            time.sleep(0.02)
        self.servo_state = ServoState(pan=pan, tilt=tilt)

    def center_servos(self) -> None:
        try:
            self.move_servos(0.0, 0.0)
        except Exception:
            logging.exception("failed to center servos during shutdown")

    def close_servo(self) -> None:
        if self.pi:
            self.pi.stop()
            self.pi = None

    def take_photo(self, output: Path) -> None:
        camera = self.config["camera"]
        cmd = [
            "rpicam-still",
            "--timeout",
            str(int(camera["timeout_ms"])),
            "--nopreview",
            "--width",
            str(int(camera["width"])),
            "--height",
            str(int(camera["height"])),
            "-o",
            str(output),
        ]
        if camera.get("hflip", False):
            cmd.append("--hflip")
        if camera.get("vflip", False):
            cmd.append("--vflip")
        if camera.get("autofocus_mode"):
            cmd += ["--autofocus-mode", str(camera["autofocus_mode"])]
        if camera.get("autofocus_on_capture", False):
            cmd.append("--autofocus-on-capture")
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        if proc.returncode != 0:
            combined = (proc.stdout or "") + (proc.stderr or "")
            raise RuntimeError(f"rpicam-still failed with exit {proc.returncode}: {combined.strip()}")

    def observe(self, image_path: Path) -> dict[str, Any]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise RuntimeError(f"could not read captured image {image_path}")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        avg_brightness = float(np.mean(gray))
        lights_on = avg_brightness >= float(self.config["observation"]["lights_on_brightness_threshold"])
        person_count = self.estimate_people(image, gray)
        motion_score = self.motion_score(gray)
        likely_activity = self.describe_activity(person_count, motion_score)
        return {
            "lights_on": str(lights_on).lower(),
            "avg_brightness": f"{avg_brightness:.2f}",
            "person_count": person_count,
            "multiple_people": str(person_count > 1).lower(),
            "likely_activity": likely_activity,
            "motion_score": f"{motion_score:.4f}",
        }

    def estimate_people(self, image, gray) -> int:
        small = cv2.resize(image, (640, int(image.shape[0] * 640 / image.shape[1])))
        rects, weights = self.hog.detectMultiScale(small, winStride=(8, 8), padding=(16, 16), scale=1.05)
        threshold = float(self.config["observation"]["person_confidence_threshold"])
        bodies = sum(1 for weight in weights if float(weight) >= threshold)
        faces = self.face.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(35, 35))
        return int(max(bodies, len(faces)))

    def motion_score(self, gray) -> float:
        resized = cv2.resize(gray, (320, 180))
        score = 0.0
        if self.previous_gray is not None:
            diff = cv2.absdiff(resized, self.previous_gray)
            score = float(np.mean(diff) / 255.0)
        self.previous_gray = resized
        return score

    def describe_activity(self, person_count: int, motion_score: float) -> str:
        motion_threshold = float(self.config["observation"]["motion_threshold"])
        if person_count <= 0:
            return "no person visible"
        if motion_score >= motion_threshold:
            if person_count > 1:
                return "multiple people visible, likely moving or interacting"
            return "one person visible, likely moving"
        if person_count > 1:
            return "multiple people visible, likely seated or standing"
        return "one person visible, likely seated or standing"

    def append_csv(self, row: dict[str, Any]) -> None:
        path = self.log_dir / f"captures-{row['date']}.csv"
        new_file = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)

    def write_daily_report(self, day: dt.date) -> Path | None:
        csv_path = self.log_dir / f"captures-{day.isoformat()}.csv"
        if not csv_path.exists():
            return None
        rows = []
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        report_path = self.report_dir / f"report-{day.isoformat()}.md"
        ok_rows = [r for r in rows if r["status"] == "ok"]
        error_rows = [r for r in rows if r["status"] != "ok"]
        people_rows = [r for r in ok_rows if int(r.get("person_count") or 0) > 0]
        multiple_rows = [r for r in ok_rows if r.get("multiple_people") == "true"]
        lights_on_rows = [r for r in ok_rows if r.get("lights_on") == "true"]
        activities: dict[str, int] = {}
        for row in ok_rows:
            activities[row.get("likely_activity", "unknown")] = activities.get(row.get("likely_activity", "unknown"), 0) + 1
        generated = self.local_now().isoformat(timespec="seconds")
        lines = [
            f"# Office Room Report - {day.isoformat()}",
            "",
            f"Generated: {generated}",
            "",
            f"- Captures: {len(rows)}",
            f"- Successful captures: {len(ok_rows)}",
            f"- Errors: {len(error_rows)}",
            f"- Lights on captures: {len(lights_on_rows)}",
            f"- Captures with anyone visible: {len(people_rows)}",
            f"- Captures with multiple people visible: {len(multiple_rows)}",
            "",
            "## Observation Notes",
        ]
        for activity, count in sorted(activities.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {activity}: {count}")
        lines += ["", "## Recent Captures"]
        for row in rows[-20:]:
            lines.append(
                f"- {row['timestamp']} {row['position']}: lights_on={row['lights_on']} "
                f"people={row['person_count']} activity={row['likely_activity']} status={row['status']}"
            )
        if error_rows:
            lines += ["", "## Errors"]
            for row in error_rows[-20:]:
                lines.append(f"- {row['timestamp']} {row['position']}: {row['error']}")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Office room pan/tilt camera capture agent")
    parser.add_argument("--config", default=str(Path.home() / "code/projects/office-room-agent/config.json"))
    parser.add_argument("--once", action="store_true", help="Capture one full scan pass and exit")
    parser.add_argument("--report", help="Generate report for YYYY-MM-DD and exit")
    args = parser.parse_args()

    agent = OfficeRoomAgent(Path(args.config).expanduser())
    if args.report:
        report = agent.write_daily_report(dt.date.fromisoformat(args.report))
        print(report or "no report generated")
        return
    if args.once:
        for position in agent.config["scan_positions"]:
            row = agent.capture_position(position)
            agent.append_csv(row)
        agent.write_daily_report(agent.local_now().date())
        agent.center_servos()
        agent.close_servo()
        return
    agent.run()


if __name__ == "__main__":
    main()
