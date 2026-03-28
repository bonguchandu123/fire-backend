import serial
import threading
import time
import random
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

latest_status = {
    "status":     "SCANNING",
    "angle":      90,
    "relay":      False,
    "buzzer":     False,
    "fire_angle": None,
    "timestamp":  None,
    "power":      True,
}

on_fire_detected = None
on_fire_cleared  = None
on_data_update   = None

_previous_status = "SCANNING"
_ser             = None   # ✅ global serial for send_command

def send_command(cmd: str):
    """Send command to Arduino e.g. POWER_ON / POWER_OFF"""
    global _ser
    if _ser and _ser.is_open:
        try:
            _ser.write(f"{cmd}\n".encode())
            print(f"📤 Command sent to Arduino: {cmd}")
        except Exception as e:
            print(f"⚠️ Command send error: {e}")
    else:
        print(f"⚠️ Serial not open — cannot send: {cmd}")

def parse_line(line: str):
    global latest_status, _previous_status

    now = datetime.utcnow().isoformat()

    if line.startswith("Angle:"):
        try:
            val = int(line.split("Angle:")[-1].strip())
            latest_status["angle"]     = val
            latest_status["timestamp"] = now
        except ValueError:
            pass
        return

    elif line.startswith("Sensor:"):
        return

    elif line.startswith("STATUS:"):
        status_val = line.split("STATUS:")[-1].strip()
        latest_status["power"] = (status_val == "ON")
        print(f"🔌 Arduino power: {status_val}")
        return

    elif "FIRE DETECTED" in line:
        latest_status.update({
            "status":     "FIRE",
            "relay":      True,
            "buzzer":     True,
            "fire_angle": latest_status["angle"],
            "timestamp":  now,
        })
        if _previous_status != "FIRE" and on_fire_detected:
            try:
                on_fire_detected(dict(latest_status))
            except Exception as e:
                print(f"⚠️ on_fire_detected error: {e}")
        _previous_status = "FIRE"

    elif "Scanning" in line:
        latest_status.update({
            "status":     "SCANNING",
            "relay":      False,
            "buzzer":     False,
            "fire_angle": None,
            "timestamp":  now,
        })
        if _previous_status == "FIRE" and on_fire_cleared:
            try:
                on_fire_cleared()
            except Exception as e:
                print(f"⚠️ on_fire_cleared error: {e}")
        _previous_status = "SCANNING"

    else:
        return

    if on_data_update:
        try:
            on_data_update(dict(latest_status))
        except Exception as e:
            print(f"⚠️ on_data_update error: {e}")


def start_arduino_reader():
    global _ser
    port      = os.getenv("ARDUINO_PORT", "COM5")
    baud_rate = int(os.getenv("BAUD_RATE", 9600))

    def _read():
        global _ser
        try:
            _ser = serial.Serial(port, baud_rate, timeout=1)
            print(f"✅ Arduino connected on {port}")
            while True:
                try:
                    raw  = _ser.readline()
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if line:
                        print(f"📡 Arduino: {line}")
                        parse_line(line)
                except Exception as e:
                    print(f"⚠️ Read error: {e}")
                    time.sleep(1)
        except Exception as e:
            print(f"❌ Cannot connect to Arduino on {port}: {e}")
            print("⚠️ Running in simulation mode")
            _simulate()

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()


def _simulate():
    print("🔄 Simulation mode started")
    angle     = 0
    direction = 3

    while True:
        try:
            angle += direction
            if angle >= 180 or angle <= 0:
                direction = -direction

            now = datetime.utcnow().isoformat()

            latest_status.update({
                "angle":      angle,
                "status":     "SCANNING",
                "relay":      False,
                "buzzer":     False,
                "fire_angle": None,
                "timestamp":  now,
            })

            if angle == 90 and random.random() < 0.1:
                latest_status.update({
                    "status":     "FIRE",
                    "fire_angle": angle,
                    "relay":      True,
                    "buzzer":     True,
                    "timestamp":  now,
                })
                if on_fire_detected:
                    try:
                        on_fire_detected(dict(latest_status))
                    except Exception as e:
                        print(f"⚠️ on_fire_detected error: {e}")

            if on_data_update:
                try:
                    on_data_update(dict(latest_status))
                except Exception as e:
                    print(f"⚠️ on_data_update error: {e}")

            time.sleep(0.1)

        except Exception as e:
            print(f"⚠️ Simulation error: {e}")
            time.sleep(1)