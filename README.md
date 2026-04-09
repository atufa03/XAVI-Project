# Prioritized Async Task Processing System

A production-grade async task queue built with **FastAPI + Celery + Redis + MongoDB**. Tasks are processed with strict priority enforcement (HIGH > MEDIUM > LOW), automatic retries, and full race condition protection.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python) |
| Queue Broker | Redis |
| Workers | Celery |
| Database | MongoDB Atlas |
| Containerization | Docker + Docker Compose |

---

## Quick Start

### Prerequisites
- Docker Desktop installed and running
- MongoDB Atlas account (free tier)

### 1. Clone the repo
```bash
git clone https://github.com/atufa03/XAVI-Project.git
cd XAVI-Project
```

### 2. Set up environment
```bash
cp .env.example .env
```
Edit `.env` and fill in your MongoDB URI:
```
MONGODB_URI=mongodb+srv://youruser:yourpassword@cluster.mongodb.net/taskdb
REDIS_URL=redis://redis:6379/0
```

### 3. Run with Docker
```bash
docker compose up --build
```

### 4. Open API docs
```
http://localhost:8000/docs
```

---

## API Endpoints

### Submit a task
```
POST /tasks
```
```json
{
  "payload": { "any": "json data here" },
  "priority": "HIGH"
}
```
**Priority values:** `HIGH` | `MEDIUM` | `LOW`

**Response:**
```json
{
  "id": "abc-123-uuid",
  "payload": { "any": "json data here" },
  "priority": "HIGH",
  "status": "pending",
  "retry_count": 0,
  "created_at": "2026-04-09T10:00:00",
  "updated_at": "2026-04-09T10:00:00",
  "error": null
}
```

---

### Get task status
```
GET /tasks/{task_id}
```
**Response:**
```json
{
  "id": "abc-123-uuid",
  "status": "completed",
  "retry_count": 1
}
```

---

### List tasks with filters
```
GET /tasks?status=pending&priority=HIGH&limit=50
```
**Query params:**
- `status` — `pending` | `processing` | `completed` | `failed`
- `priority` — `HIGH` | `MEDIUM` | `LOW`
- `limit` — number of results (default 50, max 200)

---

## Task Lifecycle

```
submitted → pending → processing → completed
                              ↘
                            failed (after 3 retries)
```

Every state change is saved to MongoDB with a timestamp.

---

## System Architecture

```
Client (HTTP Request)
        │
        ▼
  FastAPI API (port 8000)
        │
        ├── Saves task to MongoDB (status: pending)
        │
        └── Dispatches to Redis queue by priority
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
      Queue:     Queue:    Queue:
       high      medium     low
          │         │         │
          ▼         ▼         ▼
    worker-high  worker-   worker-low
    (2 workers)  medium    (1 worker)
                (2 workers)
                    │
                    ▼
              MongoDB Atlas
           (full task history)
```

---

## Queue Design

**Why 3 separate queues instead of 1 sorted queue?**

With a single shared queue and multiple workers, sorting by priority is not reliable:

- Worker A pulls task #1 (LOW priority)
- HIGH priority task arrives as task #2
- Worker B correctly picks up task #2
- But Worker A is already running the LOW task — priority violated

With **dedicated queues per priority and dedicated workers per queue**, HIGH workers are always available exclusively for HIGH tasks. They never touch MEDIUM or LOW queues. This is a guarantee, not a best-effort.

---

## Priority Handling

| Priority | Queue | Workers | Weight |
|---|---|---|---|
| HIGH | `high` | 2 concurrent | 1 |
| MEDIUM | `medium` | 2 concurrent | 2 |
| LOW | `low` | 1 concurrent | 3 |

`worker_prefetch_multiplier=1` ensures workers do not pre-fetch tasks. Priority decisions are made at dispatch time, not speculatively.

---

## Retry Logic

- 30% simulated failure rate per task execution
- On failure: task re-queued with **exponential backoff** (2s → 4s → 8s)
- Maximum **3 retries** — after that, status = `failed` permanently
- `retry_count` increments in MongoDB on each retry
- `task_acks_late=True` — if a worker crashes mid-task, the task returns to the queue automatically

---

## Concurrency and Race Condition Protection

**Problem:** With multiple workers polling the same queue, two workers could pick up the same task simultaneously.

**Solution:** Atomic MongoDB `find_one_and_update`:

```python
result = db.tasks.find_one_and_update(
    {"id": task_id, "status": "pending"},  # only matches pending tasks
    {"$set": {"status": "processing"}},    # atomically claims it
    return_document=True
)
if not result:
    return  # another worker already claimed it — exit immediately
```

MongoDB guarantees only one write wins this race. The losing worker receives `None` and exits without doing any work.

---

## Idempotency

Before processing any task, the worker atomically claims it by flipping `pending → processing`. If the flip fails (task already claimed or already completed), the worker exits immediately. This means:

- No task is ever processed twice simultaneously
- Safe for Celery's at-least-once delivery guarantee
- Worker crash recovery is automatic — unclaimed tasks stay in queue

---

## Worker Crash Recovery

`task_acks_late=True` in Celery config means:

- Task is only acknowledged (removed from queue) **after** successful completion
- If a worker crashes mid-execution, the task is **not lost**
- Redis automatically re-queues it for another worker to pick up

---

## MongoDB — What Gets Stored

Every task is a document tracking its full lifecycle:

```json
{
  "id": "uuid-string",
  "payload": { "user_defined": "data" },
  "priority": "HIGH",
  "priority_weight": 1,
  "status": "completed",
  "retry_count": 0,
  "created_at": "2026-04-09T10:00:00Z",
  "updated_at": "2026-04-09T10:00:03Z",
  "error": null
}
```

---

## Assumptions and Trade-offs

**LOW task starvation:** If HIGH tasks arrive continuously, LOW tasks may wait indefinitely. In production, a starvation timeout would auto-promote tasks waiting longer than N minutes.

**In-memory Redis:** Redis data is lost on restart without persistence. For production, enable Redis AOF persistence.

**Simulated failures:** The 30% failure rate is random. In production this represents real errors such as network failures and timeouts.

**No authentication:** Endpoints are open. Production would add API key or JWT middleware.

---

## Potential Improvements

- Add Flower dashboard for real-time Celery monitoring
- Starvation prevention — auto-promote tasks waiting longer than 10 minutes
- Dead letter queue for permanently failed tasks requiring manual review
- Webhook callbacks to notify clients when task status changes
- Rate limiting per client to prevent queue flooding
