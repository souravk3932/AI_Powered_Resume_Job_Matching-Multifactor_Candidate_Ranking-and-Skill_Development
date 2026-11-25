import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.extract import router as extract_router
from app.api.llm import router as llm_router
from app.api.match import router as match_router
from app.api.score import router as score_router
from app.matching.embedder import warm_up


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the Sentence Transformers model in the background so the service starts instantly
    threading.Thread(target=warm_up, daemon=True).start()
    yield


# Create the web application object
app = FastAPI(title="AI Service", lifespan=lifespan)
app.include_router(extract_router)
app.include_router(llm_router)
app.include_router(match_router)
app.include_router(score_router)


# Health check: "are you alive?"
@app.get("/health")
def health():
    return {"service": "ai-service", "status": "ok"}
