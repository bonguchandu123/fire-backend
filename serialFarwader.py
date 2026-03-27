import serial
import requests
import time
import os
import threading
from dotenv import load_dotenv

load_dotenv()

ARDUINO_PORT = os.getenv("ARDUINO_PORT", "COM5")
BAUD_RATE    = int(os.getenv("BAUD_RATE", 9600))
RENDER_URL   = os.getenv("RENDER_URL", "https://your-app.onrender.com")
POLL_INTERVAL = 2  # seconds

current_angle   = 90
previous_status = "SCANNING"
ser             = None   # global serial connection

def send_to_render(status: str, angle: int, fire_angle: int = None):
    try:
        payload = {
            "status":     status,
            "angle":      angle,
            "relay":      status == "FIRE",
            "buzzer":     status == "FIRE",
            "fire_angle": fire_angle or angle,
        }
        res = requests.post(f"{RENDER_URL}/serial/data", json=payload, timeout=5)
        print(f"✅ Sent → {status} @ {angle}° | {res.status_code}")
    except Exception as e:
        print(f"⚠️ Send error: {e}")

def parse_line(line: str):
    global current_angle, previous_status

    if line.startswith("Angle:"):
        try:
            current_angle = int(line.split("Angle:")[-1].strip())
        except:
            pass
        return

    if line.startswith("Sensor:"):
        return

    if "FIRE DETECTED" in line:
        if previous_status != "FIRE":
            print(f"🔥 Fire at angle {current_angle}°")
            send_to_render("FIRE", current_angle, current_angle)
            previous_status = "FIRE"
        return

    if "Scanning" in line:
        if previous_status == "FIRE":
            print("✅ Fire cleared")
            send_to_render("SCANNING", current_angle)
            previous_status = "SCANNING"
        else:
            send_to_render("SCANNING", current_angle)
        return

# ─────────────────────────────────────────
# POLL RENDER FOR POWER COMMANDS
# ─────────────────────────────────────────
last_power = "ON"

def poll_power():
    global last_power, ser
    while True:
        try:
            res   = requests.get(f"{RENDER_URL}/power", timeout=5)
            power = res.json().get("power", "ON")

            if power != last_power:
                last_power = power
                if ser and ser.is_open:
                    cmd = "POWER_ON\n" if power == "ON" else "POWER_OFF\n"
                    ser.write(cmd.encode())
                    print(f"📤 Sent to Arduino: {cmd.strip()}")
        except Exception as e:
            print(f"⚠️ Power poll error: {e}")
        time.sleep(POLL_INTERVAL)

def run():
    global ser, current_angle

    # Start power polling in background
    t = threading.Thread(target=poll_power, daemon=True)
    t.start()

    while True:
        try:
            ser = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
            print(f"✅ Arduino connected on {ARDUINO_PORT}")
            angle      = 0
            scan_speed = 3

            while True:
                try:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    print(f"📡 {line}")

                    if "Scanning" in line:
                        angle += scan_speed
                        if angle >= 180 or angle <= 0:
                            scan_speed = -scan_speed
                        current_angle = angle

                    parse_line(line)
                except Exception as e:
                    print(f"⚠️ Read error: {e}")

        except Exception as e:
            print(f"❌ Arduino error: {e}")
            print("🔄 Retrying in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    run()