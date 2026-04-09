from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime, timezone
from enum import Enum
import uuid


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Maps priority string to a number for internal sorting
# Lower number = higher priority
PRIORITY_WEIGHT = {
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}

# Maps priority to its Celery queue name
PRIORITY_QUEUE = {
    Priority.HIGH: "high",
    Priority.MEDIUM: "medium",
    Priority.LOW: "low",
}


class TaskCreate(BaseModel):
    """Request body for creating a task."""
    payload: Dict[str, Any]
    priority: Priority = Priority.MEDIUM


class TaskResponse(BaseModel):
    """Response model returned to the client."""
    id: str
    payload: Dict[str, Any]
    priority: str
    status: str
    retry_count: int
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None


def make_task_doc(payload: dict, priority: Priority) -> dict:
    """Create a new task document ready for MongoDB insertion."""
    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "payload": payload,
        "priority": priority.value,
        "priority_weight": PRIORITY_WEIGHT[priority],
        "status": TaskStatus.PENDING.value,
        "retry_count": 0,
        "created_at": now,
        "updated_at": now,
        "error": None,
    }