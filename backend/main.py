from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routers.tasks import router as tasks_router

load_dotenv()

app = FastAPI(
    title="Prioritized Async Task Processor",
    description="Submit tasks with HIGH/MEDIUM/LOW priority. Tasks are processed asynchronously with retry logic and race condition protection.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)


@app.get("/")
def root():
    return {"message": "Task Processor API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}