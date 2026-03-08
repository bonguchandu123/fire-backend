import asyncio
import json
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database
import firebase
import arduino

# ─────────────────────────────────────────
# STORE MAIN EVENT LOOP
# ─────────────────────────────────────────
_loop: asyncio.AbstractEventLoop = None

# ─────────────────────────────────────────
# WEBSOCKET MANAGER
# ─────────────────────────────────────────
class WebSocketManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"📱 Client connected | Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        print(f"📱 Client disconnected | Total: {len(self.active)}")

    async def broadcast(self, data: dict):
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(data))
            except:
                disconnected.append(ws)
        for ws in disconnected:
            self.active.remove(ws)

ws_manager = WebSocketManager()

# ─────────────────────────────────────────
# ARDUINO CALLBACKS
# ─────────────────────────────────────────
async def _save_fire_event(status: dict):
    db = database.get_db()
    if db is None:
        return

    now = datetime.utcnow().isoformat()

    event = {
        "status":     "FIRE",
        "angle":      status["angle"],
        "fire_angle": status["fire_angle"],
        "relay":      True,
        "buzzer":     True,
        "timestamp":  now,
    }
    await db["fire_events"].insert_one(event)
    print(f"✅ Fire event saved at angle {status['angle']}°")

    await db["fire_alerts"].insert_one({
        "title":      "🔥 Fire Detected!",
        "body":       f"Fire detected at angle {status['angle']}°. Pump activated.",
        "angle":      status["angle"],
        "fire_angle": status["fire_angle"],
        "relay":      True,
        "buzzer":     True,
        "unread":     True,
        "timestamp":  now,
    })

    await db["system_log"].insert_one({
        "from_status": "SCANNING",
        "to_status":   "FIRE",
        "angle":       status["angle"],
        "timestamp":   now,
    })

    await db["servo_log"].insert_one({
        "angle":     status["angle"],
        "status":    "FIRE",
        "timestamp": now,
    })

    tokens_cursor = db["fcm_tokens"].find({}, {"token": 1})
    tokens = [doc["token"] async for doc in tokens_cursor]
    firebase.send_fire_notification(tokens, status["angle"], now)


def on_fire_detected(status: dict):
    if _loop:
        asyncio.run_coroutine_threadsafe(_save_fire_event(status), _loop)


def on_fire_cleared():
    db = database.get_db()
    if db is None or not _loop:
        return

    async def _handle():
        now = datetime.utcnow().isoformat()
        await db["system_log"].insert_one({
            "from_status": "FIRE",
            "to_status":   "SCANNING",
            "angle":       arduino.latest_status["angle"],
            "timestamp":   now,
        })
        tokens_cursor = db["fcm_tokens"].find({}, {"token": 1})
        tokens = [doc["token"] async for doc in tokens_cursor]
        firebase.send_safe_notification(tokens)

    asyncio.run_coroutine_threadsafe(_handle(), _loop)


def on_data_update(status: dict):
    if _loop:
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast(status), _loop)


arduino.on_fire_detected = on_fire_detected
arduino.on_fire_cleared  = on_fire_cleared
arduino.on_data_update   = on_data_update

# ─────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_event_loop()
    await database.connect_db()
    firebase.init_firebase()
    arduino.start_arduino_reader()
    print("🚀 Fire Detection Backend Started!")
    yield
    await database.close_db()

# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────
app = FastAPI(
    title="🔥 Fire Detection API",
    description="Real-time fire detection backend for Arduino + Flutter",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────
class FCMTokenRequest(BaseModel):
    token: str

# ─────────────────────────────────────────
# ROUTES — HEALTH
# ─────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {"message": "🔥 Fire Detection API is running!", "docs": "/docs"}

# ─────────────────────────────────────────
# ROUTES — LIVE STATUS
# ─────────────────────────────────────────
@app.get("/status", tags=["Status"])
async def get_status():
    return arduino.latest_status

@app.get("/system/live", tags=["System Log"])
async def get_live_system_status():
    return {
        "status":     arduino.latest_status["status"],
        "angle":      arduino.latest_status["angle"],
        "relay":      arduino.latest_status["relay"],
        "buzzer":     arduino.latest_status["buzzer"],
        "fire_angle": arduino.latest_status["fire_angle"],
        "timestamp":  arduino.latest_status["timestamp"],
        "ws_clients": len(ws_manager.active),
    }

# ─────────────────────────────────────────
# ROUTES — WEBSOCKET
# ─────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps(arduino.latest_status))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# ─────────────────────────────────────────
# ROUTES — FIRE HISTORY
# ─────────────────────────────────────────
@app.get("/fire/history", tags=["Fire History"])
async def get_fire_history(limit: int = 50):
    db = database.get_db()
    cursor = db["fire_events"].find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    events = await cursor.to_list(length=limit)
    return {"total": len(events), "events": events}

@app.delete("/fire/history", tags=["Fire History"])
async def clear_fire_history():
    db = database.get_db()
    result = await db["fire_events"].delete_many({})
    return {"deleted": result.deleted_count}

# ─────────────────────────────────────────
# ROUTES — FIRE ALERTS
# ─────────────────────────────────────────
@app.get("/alerts", tags=["Fire Alerts"])
async def get_alerts(limit: int = 50, unread_only: bool = False):
    db = database.get_db()
    query = {"unread": True} if unread_only else {}
    cursor = db["fire_alerts"].find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    alerts = await cursor.to_list(length=limit)
    return {"total": len(alerts), "alerts": alerts}

@app.get("/alerts/unread-count", tags=["Fire Alerts"])
async def get_unread_count():
    db = database.get_db()
    count = await db["fire_alerts"].count_documents({"unread": True})
    return {"unread_count": count}

@app.post("/alerts/mark-read", tags=["Fire Alerts"])
async def mark_alerts_read():
    db = database.get_db()
    result = await db["fire_alerts"].update_many({"unread": True}, {"$set": {"unread": False}})
    return {"updated": result.modified_count}

@app.delete("/alerts", tags=["Fire Alerts"])
async def clear_alerts():
    db = database.get_db()
    result = await db["fire_alerts"].delete_many({})
    return {"deleted": result.deleted_count}

# ─────────────────────────────────────────
# ROUTES — SERVO LOG
# ─────────────────────────────────────────
@app.get("/servo/current", tags=["Servo Log"])
async def get_current_angle():
    return {
        "angle":     arduino.latest_status["angle"],
        "status":    arduino.latest_status["status"],
        "timestamp": arduino.latest_status["timestamp"],
    }

@app.get("/servo/log", tags=["Servo Log"])
async def get_servo_log(limit: int = 100):
    db = database.get_db()
    cursor = db["servo_log"].find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    logs = await cursor.to_list(length=limit)
    return {"total": len(logs), "logs": logs}

@app.delete("/servo/log", tags=["Servo Log"])
async def clear_servo_log():
    db = database.get_db()
    result = await db["servo_log"].delete_many({})
    return {"deleted": result.deleted_count}

# ─────────────────────────────────────────
# ROUTES — SYSTEM LOG
# ─────────────────────────────────────────
@app.get("/system/log", tags=["System Log"])
async def get_system_log(limit: int = 100):
    db = database.get_db()
    cursor = db["system_log"].find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    logs = await cursor.to_list(length=limit)
    return {"total": len(logs), "logs": logs}

@app.delete("/system/log", tags=["System Log"])
async def clear_system_log():
    db = database.get_db()
    result = await db["system_log"].delete_many({})
    return {"deleted": result.deleted_count}

# ─────────────────────────────────────────
# ROUTES — STATS
# ─────────────────────────────────────────
@app.get("/stats", tags=["Stats"])
async def get_stats():
    db = database.get_db()
    total_fires   = await db["fire_events"].count_documents({})
    total_alerts  = await db["fire_alerts"].count_documents({})
    unread_alerts = await db["fire_alerts"].count_documents({"unread": True})

    last_fire_cursor = db["fire_events"].find({}, {"_id": 0}).sort("timestamp", -1).limit(1)
    last_fire_list   = await last_fire_cursor.to_list(length=1)
    last_fire        = last_fire_list[0] if last_fire_list else None

    pipeline = [
        {"$group": {"_id": "$fire_angle", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1},
    ]
    angle_result  = await db["fire_events"].aggregate(pipeline).to_list(length=1)
    hottest_angle = angle_result[0]["_id"] if angle_result else None

    return {
        "total_fires":    total_fires,
        "total_alerts":   total_alerts,
        "unread_alerts":  unread_alerts,
        "last_fire":      last_fire,
        "hottest_angle":  hottest_angle,
        "current_status": arduino.latest_status["status"],
        "current_angle":  arduino.latest_status["angle"],
        "ws_clients":     len(ws_manager.active),
    }

# ─────────────────────────────────────────
# ROUTES — FCM TOKENS
# ─────────────────────────────────────────
@app.post("/token/register", tags=["FCM Tokens"])
async def register_token(request: FCMTokenRequest):
    db = database.get_db()
    existing = await db["fcm_tokens"].find_one({"token": request.token})
    if existing:
        return {"message": "Token already registered"}
    await db["fcm_tokens"].insert_one({
        "token":      request.token,
        "created_at": datetime.utcnow().isoformat()
    })
    return {"message": "Token registered successfully"}

@app.delete("/token/{token}", tags=["FCM Tokens"])
async def remove_token(token: str):
    db = database.get_db()
    result = await db["fcm_tokens"].delete_one({"token": token})
    return {"deleted": result.deleted_count}

# ─────────────────────────────────────────
# ROUTES — SERIAL DATA (from PC forwarder)
# ─────────────────────────────────────────
class SerialDataRequest(BaseModel):
    status:     str
    angle:      int
    relay:      bool = False
    buzzer:     bool = False
    fire_angle: int  = None

@app.post("/serial/data", tags=["Serial Data"])
async def receive_serial_data(request: SerialDataRequest):
    now = datetime.utcnow().isoformat()

    prev_status = arduino.latest_status["status"]

    arduino.latest_status.update({
        "status":     request.status,
        "angle":      request.angle,
        "relay":      request.relay,
        "buzzer":     request.buzzer,
        "fire_angle": request.fire_angle,
        "timestamp":  now,
    })

    await ws_manager.broadcast(arduino.latest_status)

    if request.status == "FIRE" and prev_status != "FIRE":
        db = database.get_db()

        await db["fire_events"].insert_one({
            "status":     "FIRE",
            "angle":      request.angle,
            "fire_angle": request.fire_angle or request.angle,
            "relay":      True,
            "buzzer":     True,
            "timestamp":  now,
        })

        await db["fire_alerts"].insert_one({
            "title":      "🔥 Fire Detected!",
            "body":       f"Fire at angle {request.angle}°. Pump activated.",
            "angle":      request.angle,
            "fire_angle": request.fire_angle or request.angle,
            "relay":      True,
            "buzzer":     True,
            "unread":     True,
            "timestamp":  now,
        })

        await db["system_log"].insert_one({
            "from_status": "SCANNING",
            "to_status":   "FIRE",
            "angle":       request.angle,
            "timestamp":   now,
        })

        tokens_cursor = db["fcm_tokens"].find({}, {"token": 1})
        tokens = [doc["token"] async for doc in tokens_cursor]
        firebase.send_fire_notification(tokens, request.angle, now)
        print(f"🔥 Fire received from PC at angle {request.angle}°")

    elif request.status == "SCANNING" and prev_status == "FIRE":
        db = database.get_db()
        await db["system_log"].insert_one({
            "from_status": "FIRE",
            "to_status":   "SCANNING",
            "angle":       request.angle,
            "timestamp":   now,
        })
        tokens_cursor = db["fcm_tokens"].find({}, {"token": 1})
        tokens = [doc["token"] async for doc in tokens_cursor]
        firebase.send_safe_notification(tokens)
        print("✅ Fire cleared — back to scanning")

    return {"message": "Data received", "status": request.status}