from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URL   = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "fire_detection")

client = None
db     = None

async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGODB_URL)
    db     = client[DATABASE_NAME]
    print("✅ MongoDB connected")

async def close_db():
    global client
    if client:
        client.close()
        print("✅ MongoDB disconnected")

def get_db():
    return db