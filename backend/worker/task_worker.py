import random
import time
import logging
from datetime import datetime, timezone
from celery import Task
from worker.celery_app import celery_app
from database import sync_tasks_collection

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
FAILURE_RATE = 0.3  # 30% simulated failure rate


class IdempotentTask(Task):
    """
    Base task class that enforces idempotency.
    Before processing, atomically claims the task by flipping status
    from 'pending' to 'processing'. If another worker already claimed
    it, this worker exits immediately — no duplicate processing.
    """

    def claim_task(self, task_id: str) -> bool:
        """
        Atomically set status to 'processing' only if currently 'pending'.
        Returns True if this worker successfully claimed the task.
        Returns False if another worker already claimed it.
        """
        result = sync_tasks_collection.find_one_and_update(
            {"id": task_id, "status": "pending"},
            {"$set": {
                "status": "processing",
                "updated_at": datetime.now(timezone.utc),
            }},
            return_document=True,
        )
        return result is not None

    def mark_completed(self, task_id: str):
        sync_tasks_collection.update_one(
            {"id": task_id},
            {"$set": {
                "status": "completed",
                "updated_at": datetime.now(timezone.utc),
                "error": None,
            }},
        )

    def mark_failed(self, task_id: str, error: str):
        sync_tasks_collection.update_one(
            {"id": task_id},
            {"$set": {
                "status": "failed",
                "updated_at": datetime.now(timezone.utc),
                "error": error,
            }},
        )

    def increment_retry(self, task_id: str):
        sync_tasks_collection.update_one(
            {"id": task_id},
            {
                "$inc": {"retry_count": 1},
                "$set": {
                    "status": "pending",  # back to pending so it can be reclaimed
                    "updated_at": datetime.now(timezone.utc),
                },
            },
        )


@celery_app.task(
    bind=True,
    base=IdempotentTask,
    max_retries=MAX_RETRIES,
    name="worker.task_worker.process_task",
)
def process_task(self, task_id: str):
    """
    Main task processor.

    Flow:
    1. Atomically claim the task (idempotency check)
    2. Simulate ~30% random failure
    3. On failure: increment retry_count, re-queue with exponential backoff
    4. After MAX_RETRIES failures: mark as permanently failed
    5. On success: mark as completed
    """
    logger.info(f"[WORKER] Picked up task {task_id} (attempt {self.request.retries + 1})")

    # --- Step 1: Idempotency check ---
    # Only proceed if we successfully claimed this task atomically.
    # If another worker already claimed it, exit silently.
    if not self.claim_task(task_id):
        logger.warning(f"[WORKER] Task {task_id} already claimed by another worker. Skipping.")
        return

    try:
        # --- Step 2: Simulate real work ---
        time.sleep(1)  # Simulate processing time

        # --- Step 3: Simulate ~30% failure rate ---
        if random.random() < FAILURE_RATE:
            raise ValueError(f"Simulated processing failure for task {task_id}")

        # --- Step 4: Success ---
        self.mark_completed(task_id)
        logger.info(f"[WORKER] Task {task_id} completed successfully.")

    except Exception as exc:
        retry_number = self.request.retries + 1
        logger.warning(f"[WORKER] Task {task_id} failed (attempt {retry_number}): {exc}")

        if retry_number < MAX_RETRIES:
            # Re-queue the task with exponential backoff: 2s, 4s, 8s
            self.increment_retry(task_id)
            backoff = 2 ** retry_number
            logger.info(f"[WORKER] Retrying task {task_id} in {backoff}s...")
            raise self.retry(exc=exc, countdown=backoff)
        else:
            # All retries exhausted — mark as permanently failed
            self.mark_failed(task_id, str(exc))
            logger.error(f"[WORKER] Task {task_id} permanently failed after {MAX_RETRIES} retries.")