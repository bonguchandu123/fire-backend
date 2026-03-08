import json
import os
import firebase_admin
from firebase_admin import credentials, messaging
from dotenv import load_dotenv

load_dotenv()

def init_firebase():
    try:
        key_path = os.getenv("FIREBASE_KEY_PATH", "serviceAccountKey.json")

        # Support passing raw JSON string in env var (for Render deployment)
        if key_path.strip().startswith("{"):
            key_dict = json.loads(key_path)
            cred = credentials.Certificate(key_dict)
        else:
            cred = credentials.Certificate(key_path)

        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized")
    except Exception as e:
        print(f"⚠️  Firebase init failed: {e}")

def send_fire_notification(tokens: list, angle: int, timestamp: str):
    if not tokens:
        print("⚠️  No FCM tokens to notify")
        return
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title="🔥 FIRE DETECTED!",
                body=f"Fire detected at angle {angle}°! Pump activated immediately.",
            ),
            data={
                "status":    "FIRE",
                "angle":     str(angle),
                "timestamp": timestamp,
            },
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="alarm",
                    channel_id="fire_alert_channel",
                ),
            ),
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)
        print(f"✅ Notifications sent: {response.success_count}/{len(tokens)}")
    except Exception as e:
        print(f"❌ Notification error: {e}")

def send_safe_notification(tokens: list):
    if not tokens:
        return
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title="✅ All Clear!",
                body="Fire extinguished. System is back to scanning.",
            ),
            data={"status": "SCANNING"},
            tokens=tokens,
        )
        messaging.send_each_for_multicast(message)
        print("✅ Safe notification sent")
    except Exception as e:
        print(f"❌ Safe notification error: {e}")