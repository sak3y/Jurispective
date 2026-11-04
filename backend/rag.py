import hashlib
import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.chat_models import init_chat_model

load_dotenv(override=True)

DB_DIR = os.getenv("DB_DIR", "./chroma_db")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
LLM_MODEL = os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

ACT_IDS = [
    "ukpga/1968/60",  # Theft Act 1968
    "ukpga/1971/48",  # Criminal Damage Act 1971
    "ukpga/1971/38",  # Misuse of Drugs Act 1971
    "ukpga/2006/35",  # Fraud Act 2006
    "ukpga/1990/18",  # Computer Misuse Act 1990
]
ACT_URLS = [f"https://www.legislation.gov.uk/{act}/data.xml" for act in ACT_IDS]
NS = "{http://www.legislation.gov.uk/namespaces/legislation}"


def load(url):
    try:
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        return ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"Failed to fetch {url}: {exc}")
        return None


def text_of(element):
    if element is None:
        return ""
    parts = []
    for node in element.iter():
        if node.tag == f"{NS}Pnumber":
            continue
        if node.text and node.text.strip():
            parts.append(node.text.strip())
        if node.tail and node.tail.strip():
            parts.append(node.tail.strip())
    return " ".join(parts)


def split(root, url):
    docs = []
    for p1 in root.iter(f"{NS}P1"):
        number = p1.find(f"{NS}Pnumber")
        p1_uri = p1.get("DocumentURI")
        if number is None or not p1_uri:
            continue
        section = "".join(number.itertext()).strip()
        label = "Paragraph" if "/schedule/" in p1_uri else "Section"

        for p2 in p1.iter(f"{NS}P2"):
            if p2.get("DocumentURI") is None:
                continue
            sub_number = p2.find(f"{NS}Pnumber")
            if sub_number is None:
                continue
            subsection = "".join(sub_number.itertext()).strip()
            content = text_of(p2.find(f"{NS}P2para"))
            if not content:
                continue
            uri = f"{p1_uri.rstrip('/')}/{subsection}"
            docs.append(Document(
                page_content=f"{label} {section}({subsection}): {content}",
                metadata={
                    "source": url,
                    "section": section,
                    "subsection": subsection,
                    "uri": uri,
                    "type": label.lower(),
                },
            ))
    return docs


def chunk_id(doc):
    return hashlib.md5(doc.metadata["uri"].encode("utf-8")).hexdigest()


def get_store():
    return Chroma(
        collection_name="legislation",
        embedding_function=OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_HOST),
        persist_directory=DB_DIR,
    )


def index(urls=ACT_URLS, rebuild=False):
    store = get_store()
    if rebuild:
        store.delete_collection()
        store = get_store()

    docs = []
    for url in urls:
        root = load(url)
        if root is not None:
            docs.extend(split(root, url))

    for start in range(0, len(docs), 100):
        batch = docs[start:start + 100]
        store.add_documents(batch, ids=[chunk_id(doc) for doc in batch])
        print(f"Indexed {start + len(batch)}/{len(docs)}")

    print(f"{len(docs)} subsections processed; store holds {store._collection.count()}")
    return store


def retrieve(store, question, k=10):
    """Return k vector matches. Chroma scores here are distances: lower is better."""
    if k < 1:
        raise ValueError("k must be at least 1")
    return store.similarity_search_with_score(question, k=k)


_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = init_chat_model(LLM_MODEL, model_provider="ollama", base_url=OLLAMA_HOST)
    return _llm


def build_prompt(question, hits):
    context = "\n\n".join(
        f"Source {i} | {doc.metadata.get('uri', 'unknown')}\n{doc.page_content}"
        for i, (doc, _) in enumerate(hits, start=1)
    )
    return (
        "You are explaining UK legislation. Use ONLY the statutory extracts below. "
        "Identify the provision most directly applicable to the question, and distinguish "
        "related offences from the offence asked about. Consider relevant exceptions "
        "and qualifications in the supplied extracts. Cite precise sections and "
        "subsections. Do not assume a legal element is satisfied without facts to "
        "support it. If the extracts do not establish an answer, say what is missing. "
        "Do not invent legislation, cases or citations.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )


def ask(store, question, k=10):
    hits = retrieve(store, question, k)
    response = get_llm().invoke(build_prompt(question, hits))
    answer = response.content
    if isinstance(answer, list):
        answer = " ".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in answer)
    return str(answer), hits


if __name__ == "__main__":
    index()
