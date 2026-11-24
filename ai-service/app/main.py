from fastapi import FastAPI

from app.api.extract import router as extract_router
from app.api.llm import router as llm_router

# Create the web application object
app = FastAPI(title="AI Service")
app.include_router(extract_router)
app.include_router(llm_router)


# Health check: "are you alive?"
@app.get("/health")
def health():
    return {"service": "ai-service", "status": "ok"}
