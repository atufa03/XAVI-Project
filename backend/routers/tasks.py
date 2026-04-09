from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from database import tasks_collection
from models import TaskCreate, TaskResponse, TaskStatus, Priority, make_task_doc, PRIORITY_QUEUE
from worker.task_worker import process_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
async def submit_task(body: TaskCreate):
    """
    Submit a new task for async processing.
    The task is immediately saved to MongoDB with status 'pending',
    then dispatched to the correct priority queue in Redis/Celery.
    """
    # Create task document
    doc = make_task_doc(body.payload, body.priority)

    # Save to MongoDB first — so status is trackable immediately
    await tasks_collection.insert_one(doc)

    # Dispatch to the correct Celery queue based on priority
    queue_name = PRIORITY_QUEUE[body.priority]
    process_task.apply_async(
        args=[doc["id"]],
        queue=queue_name,
    )

    return _format(doc)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """
    Get the current status and details of a specific task.
    """
    doc = await tasks_collection.find_one({"id": task_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return _format(doc)


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    priority: Optional[Priority] = Query(None, description="Filter by priority"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List tasks with optional filters for status and priority.
    Results are sorted by priority weight (HIGH first), then by creation time.
    """
    query = {}
    if status:
        query["status"] = status.value
    if priority:
        query["priority"] = priority.value

    cursor = tasks_collection.find(query).sort(
        [("priority_weight", 1), ("created_at", 1)]
    ).limit(limit)

    docs = await cursor.to_list(length=limit)
    return [_format(d) for d in docs]


def _format(doc: dict) -> dict:
    """Strip MongoDB's internal _id field before returning."""
    doc.pop("_id", None)
    return doc