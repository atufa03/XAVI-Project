import os
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://samreenzaidi:Mocha2016@cluster0.dmeztk9.mongodb.net/?appName=Cluster0")

# Async client — used by FastAPI endpoints
async_client = AsyncIOMotorClient(MONGODB_URI)
async_db = async_client.taskdb
tasks_collection = async_db.tasks

# Sync client — used by Celery workers (Celery is not async)
sync_client = MongoClient(MONGODB_URI)
sync_db = sync_client.taskdb
sync_tasks_collection = sync_db.tasks