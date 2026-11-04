import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend import rag

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_methods=["GET"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

store = rag.get_store()


@app.get("/health")
def health():
    return {"chunks": store._collection.count()}


@app.get("/ollama-status")
async def ollama_status():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
        models = [item["name"] for item in response.json().get("models", [])]
        model_available = any(
            name == model or name.split(":")[0] == model.split(":")[0]
            for name in models
        )
        return {
            "running": True,
            "model": model,
            "model_available": model_available,
            "installed_models": models,
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {
            "running": False,
            "model": model,
            "model_available": False,
            "installed_models": [],
        }

k = 10 
@app.get("/search")
def search(query: str, k_neighbours: int = k):
    hits = rag.retrieve(store, query, k_neighbours)
    res = [
        {"text": doc.page_content, "uri": doc.metadata["uri"], "score": float(score)}
        for doc, score in hits
    ]
    return {"query": query, "res": res}


@app.get("/ask")
@limiter.limit("3/minute")
def ask(request: Request, query: str, k_neighbours: int = k):
    answer, hits = rag.ask(store, query, k_neighbours)
    return {
        "query": query,
        "answer": answer,
        "sources": [
            {"text": doc.page_content, "uri": doc.metadata["uri"], "score": float(score)}
            for doc, score in hits
        ],
    }


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
