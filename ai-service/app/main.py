from fastapi import FastAPI

# Create the web application object
app = FastAPI(title="AI Service")


# Health check: "are you alive?"
@app.get("/health")
def health():
    return {"service": "ai-service", "status": "ok"}
