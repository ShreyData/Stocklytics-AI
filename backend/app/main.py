from fastapi import FastAPI

app = FastAPI(title="Stocklytics AI")


@app.get("/health")
def health():
    return {"status": "ok"}
