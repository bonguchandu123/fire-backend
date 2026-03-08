import serial
import threading
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# ─────────────────────────────────────────
# SHARED STATE
# ─────────────────────────────────────────
latest_status = {
    "status":     "SCANNING",
    "angle":      90,
    "relay":      False,
    "buzzer":     False,
    "fire_angle": None,
    "timestamp":  None,
}

# Callbacks set by main.py
on_fire_detected = None   # called when fire starts
on_fire_cleared  = None   # called when fire stops
on_data_update   = None   # called on every update

_previous_status = "SCANNING"

# ─────────────────────────────────────────
# PARSE ARDUINO LINE
# ─────────────────────────────────────────
def parse_line(line: str):
    global latest_status, _previous_status

    now = datetime.utcnow().isoformat()

    if "FIRE DETECTED" in line:
        latest_status = {
            "status":     "FIRE",
            "angle":      latest_status["angle"],
            "relay":      True,
            "buzzer":     True,
            "fire_angle": latest_status["angle"],
            "timestamp":  now,
        }
        # Trigger fire callback only on transition
        if _previous_status != "FIRE" and on_fire_detected:
            on_fire_detected(latest_status)
        _previous_status = "FIRE"

    elif "Scanning" in line:
        latest_status = {
            "status":     "SCANNING",
            "angle":      latest_status["angle"],
            "relay":      False,
            "buzzer":     False,
            "fire_angle": None,
            "timestamp":  now,
        }
        # Trigger cleared callback only on transition
        if _previous_status == "FIRE" and on_fire_cleared:
            on_fire_cleared()
        _previous_status = "SCANNING"

    elif "Sensor:" in line:
        try:
            # Extract raw sensor value (0 or 1)
            val = int(line.split("Sensor:")[-1].strip())
            latest_status["angle"] = val
        except:
            pass

    # Always trigger data update
    if on_data_update:
        on_data_update(latest_status)

# ─────────────────────────────────────────
# START ARDUINO READER THREAD
# ─────────────────────────────────────────
def start_arduino_reader():
    port      = os.getenv("ARDUINO_PORT", "COM3")
    baud_rate = int(os.getenv("BAUD_RATE", 9600))

    def _read():
        try:
            ser = serial.Serial(port, baud_rate, timeout=1)
            print(f"✅ Arduino connected on {port}")
            while True:
                try:
                    raw  = ser.readline()
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if line:
                        print(f"📡 Arduino: {line}")
                        parse_line(line)
                except Exception as e:
                    print(f"⚠️  Read error: {e}")
        except Exception as e:
            print(f"❌ Cannot connect to Arduino on {port}: {e}")
            print("⚠️  Running in simulation mode")
            _simulate()

    thread        = threading.Thread(target=_read, daemon=True)
    thread.start()

# ─────────────────────────────────────────
# SIMULATION MODE (if no Arduino connected)
# ─────────────────────────────────────────
def _simulate():
    import time, random
    print("🔄 Simulation mode started")
    angle     = 0
    direction = 3
    while True:
        angle += direction
        if angle >= 180 or angle <= 0:
            direction = -direction

        latest_status["angle"]  = angle
        latest_status["status"] = "SCANNING"

        # Simulate fire every 30 seconds
        if angle == 90 and random.random() < 0.1:
            latest_status["status"]     = "FIRE"
            latest_status["fire_angle"] = angle
            latest_status["relay"]      = True
            latest_status["buzzer"]     = True
            if on_fire_detected:
                on_fire_detected(latest_status)

        if on_data_update:
            on_data_update(latest_status)

        time.sleep(0.05)