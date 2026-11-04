
import hashlib
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.chat_models import init_chat_model


load_dotenv(override=True)


# Configuration
DB_DIR = os.getenv("DB_DIR", "./chroma_db")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)

DEFAULT_K = 10


# Legislation included in the corpus
ACT_IDS = [
    "ukpga/1968/60",   # Theft Act 1968
    "ukpga/1971/48",   # Criminal Damage Act 1971
    "ukpga/1971/38",   # Misuse of Drugs Act 1971
    "ukpga/2006/35",   # Fraud Act 2006
    "ukpga/1990/18",   # Computer Misuse Act 1990
]

ACT_URLS = [
    f"https://www.legislation.gov.uk/{act}/data.xml"
    for act in ACT_IDS
]

NS = "{http://www.legislation.gov.uk/namespaces/legislation}"


def load(url):
    """
    Download an Act and parse its XML.
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return ET.fromstring(response.content)

    except (requests.RequestException, ET.ParseError) as exc:
        print(f"Failed to fetch {url}: {exc}")
        return None


def text_of(para):
    """
    Extract text from a legislative paragraph.

    Skip paragraph numbering elements while preserving
    their surrounding text.
    """
    if para is None:
        return ""

    parts = []

    for node in para.iter():
        if node.tag == f"{NS}Pnumber":
            continue

        if node.text and node.text.strip():
            parts.append(node.text.strip())

        if node.tail and node.tail.strip():
            parts.append(node.tail.strip())

    return " ".join(parts)


def split(root, url):
    """
    Split legislation into subsection-level documents.

    Each document contains:
    - Section or paragraph number
    - Subsection number
    - Legislative text
    - Source URL and metadata
    """
    docs = []

    for p1 in root.iter(f"{NS}P1"):
        number_node = p1.find(f"{NS}Pnumber")

        if number_node is None:
            continue

        section = "".join(number_node.itertext()).strip()
        p1_uri = p1.get("DocumentURI")

        if not p1_uri:
            continue

        if "/schedule/" in p1_uri:
            label = "Paragraph"
        else:
            label = "Section"

        for p2 in p1.iter(f"{NS}P2"):
            # Skip quoted provisions without their own URI.
            if p2.get("DocumentURI") is None:
                continue

            sub_node = p2.find(f"{NS}Pnumber")

            if sub_node is None:
                continue

            sub = "".join(sub_node.itertext()).strip()
            content = text_of(p2.find(f"{NS}P2para"))

            if not content:
                continue

            # Construct the URI from the parent provision.
            uri = f"{p1_uri.rstrip('/')}/{sub}"

            docs.append(
                Document(
                    page_content=(
                        f"{label} {section}({sub}): {content}"
                    ),
                    metadata={
                        "source": url,
                        "section": section,
                        "subsection": sub,
                        "uri": uri,
                        "type": label.lower(),
                    },
                )
            )

    return docs


def chunk_id(doc):
    """
    Generate a stable ID for each provision.
    """
    return hashlib.md5(
        doc.metadata["uri"].encode("utf-8")
    ).hexdigest()


def get_store():
    """
    Connect to the existing ChromaDB collection.
    """
    return Chroma(
        collection_name="legislation",
        embedding_function=OllamaEmbeddings(
            model=EMBED_MODEL,
            base_url=OLLAMA_HOST,
        ),
        persist_directory=DB_DIR,
    )


def index(urls=ACT_URLS, rebuild=False):
    """
    Download, split, embed and index legislation.

    Documents are inserted in batches to avoid
    oversized requests to the vector database.
    """
    store = get_store()

    if rebuild:
        store.delete_collection()
        store = get_store()

    docs = []

    for url in urls:
        root = load(url)

        if root is None:
            continue

        act_docs = split(root, url)
        docs.extend(act_docs)

        print(
            f"Loaded {len(act_docs)} provisions from {url}"
        )

    batch_size = 100

    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]

        store.add_documents(
            documents=batch,
            ids=[chunk_id(doc) for doc in batch],
        )

        print(
            f"Indexed {i + len(batch)}/{len(docs)}"
        )

    total = store._collection.count()

    print(
        f"{len(docs)} provisions processed, "
        f"{total} documents in ChromaDB."
    )

    return store


def retrieve(store, question, k=DEFAULT_K):
    """
    Retrieve the k most similar legislation chunks.

    ChromaDB returns a document and distance score
    for each result. Lower distances indicate
    greater embedding similarity.
    """
    if not question or not question.strip():
        return []

    if k < 1:
        raise ValueError("k must be at least 1")

    return store.similarity_search_with_score(
        question,
        k=k,
    )


_llm = None


def get_llm():
    """
    Initialise the Ollama language model on first use.
    """
    global _llm

    if _llm is None:
        _llm = init_chat_model(
            LLM_MODEL,
            model_provider=LLM_PROVIDER,
            base_url=OLLAMA_HOST,
        )

    return _llm


def build_prompt(question, hits):
    """
    Construct a prompt grounded in retrieved legislation.
    """
    context_parts = []

    for index_number, (doc, score) in enumerate(
        hits,
        start=1,
    ):
        uri = doc.metadata.get("uri", "Unknown source")

        context_parts.append(
            f"Source {index_number}\n"
            f"URL: {uri}\n"
            f"Legislation: {doc.page_content}"
        )

    context = "\n\n".join(context_parts)

    return (
        "You are a UK legislation research assistant.\n\n"
        "Answer the user's question using only the "
        "legislation provided in the context.\n\n"

        "Rules:\n"
        "1. Identify the most directly relevant provisions.\n"
        "2. Explain how those provisions apply to the facts.\n"
        "3. Cite the section numbers supporting your answer.\n"
        "4. Distinguish between different offences where relevant.\n"
        "5. Do not assume that an exception or defence applies "
        "unless the facts support it.\n"
        "6. Do not invent legislation, facts or legal conclusions.\n"
        "7. If the context does not contain enough information "
        "to answer, explicitly say so.\n"
        "8. Keep the answer clear and concise.\n\n"

        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )


def ask(store, question, k=DEFAULT_K):
    """
    Retrieve relevant legislation and generate an answer.

    Returns:
        answer: Generated response text.
        hits: Retrieved legislation and distance scores.
    """
    hits = retrieve(
        store=store,
        question=question,
        k=k,
    )

    if not hits:
        return (
            "I could not find relevant legislation "
            "in the available context.",
            [],
        )

    prompt = build_prompt(question, hits)

    response = get_llm().invoke(prompt)

    answer = response.content

    if isinstance(answer, list):
        answer = " ".join(
            str(part) for part in answer
        )

    return str(answer), hits


if __name__ == "__main__":
    index(rebuild=False)
