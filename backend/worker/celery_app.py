import os
from celery import Celery
from kombu import Queue, Exchange
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "task_processor",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker.task_worker"],
)

# --- Define 3 separate queues, one per priority ---
# This is the key design decision: separate queues (not one sorted queue)
# so dedicated workers can drain HIGH before touching MEDIUM or LOW.
high_exchange = Exchange("high", type="direct")
medium_exchange = Exchange("medium", type="direct")
low_exchange = Exchange("low", type="direct")

celery_app.conf.task_queues = (
    Queue("high",   high_exchange,   routing_key="high"),
    Queue("medium", medium_exchange, routing_key="medium"),
    Queue("low",    low_exchange,    routing_key="low"),
)

# Default queue for any task not explicitly routed
celery_app.conf.task_default_queue = "medium"
celery_app.conf.task_default_exchange = "medium"
celery_app.conf.task_default_routing_key = "medium"

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Prevent a task from being acknowledged before it finishes.
    # If a worker crashes mid-task, the task goes back to the queue.
    task_acks_late=True,
    # Only prefetch one task at a time per worker.
    # This ensures priority is respected — a worker won't grab a LOW
    # task while a HIGH task is waiting.
    worker_prefetch_multiplier=1,
)