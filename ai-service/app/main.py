from fastapi import FastAPI

from app.api.extract import router as extract_router

# Create the web application object
app = FastAPI(title="AI Service")
app.include_router(extract_router)


# Health check: "are you alive?"
@app.get("/health")
def health():
    return {"service": "ai-service", "status": "ok"}
