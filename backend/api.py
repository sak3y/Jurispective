import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend import rag

app = FastAPI(title="Wiggle Room API")
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
    base_url = rag.OLLAMA_HOST.rstrip("/")
    model = rag.LLM_MODEL
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
        models = [item["name"] for item in response.json().get("models", [])]
        available = any(name == model or name.split(":")[0] == model.split(":")[0] for name in models)
        return {"running": True, "model": model, "model_available": available, "installed_models": models}
    except (httpx.HTTPError, ValueError, KeyError):
        return {"running": False, "model": model, "model_available": False, "installed_models": []}


@app.get("/search")
def search(query: str, k_neighbours: int = 10):
    hits = rag.retrieve(store, query, k_neighbours)
    return {
        "query": query,
        "res": [
            {"text": doc.page_content, "uri": doc.metadata.get("uri", ""), "score": float(score)}
            for doc, score in hits
        ],
    }


@app.get("/ask")
@limiter.limit("3/minute")
def ask(request: Request, query: str, k_neighbours: int = 10):
    answer, hits = rag.ask(store, query, k_neighbours)
    return {
        "query": query,
        "answer": answer,
        "sources": [
            {"text": doc.page_content, "uri": doc.metadata.get("uri", ""), "score": float(score)}
            for doc, score in hits
        ],
    }


app.mount(
    "/",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True),
    name="frontend",
)
