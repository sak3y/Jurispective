# Jurispective

A Retrieval-Augmented Generation (RAG) application that answers questions about UK criminal law using legislation from [legislation.gov.uk](https://www.legislation.gov.uk/).

Instead of relying on the knowledge LLM's obtained during training, the application retrieves relevant legislation and uses it to generate answers with source references.

## 🎥 Demo


https://github.com/user-attachments/assets/7c4b2fb8-870e-4891-ac76-0c43e5ec127c


## Tech Stack

- **Backend:** Python, FastAPI, LangChain
- **Frontend:** HTML, CSS, JavaScript
- **LLM:** Ollama (Llama 3.2)
- **Embeddings:** nomic-embed-text
- **Vector Database:** ChromaDB
- **Containerisation:** Docker Compose

## How It Works

1. Fetches UK legislation as XML from legislation.gov.uk.
2. Splits legislation into chunks based on individual subsections.
3. Generates embeddings and stores them in ChromaDB.
4. Retrieves the four most relevant chunks for a user's question.
5. Uses an LLM to generate an answer based on the retrieved legislation.

The application currently covers five Acts (for now):

- Theft Act 1968
- Criminal Damage Act 1971
- Misuse of Drugs Act 1971
- Fraud Act 2006
- Computer Misuse Act 1990

The database contains **568 legislative subsections**.

## Running Locally

Requires Python 3.12, uv and Ollama.

```bash
uv venv --python 3.12
uv pip install -r backend/requirements.txt

ollama pull nomic-embed-text
ollama pull llama3.2

python -m backend.rag
```

Start the backend:

```bash
uv run python -m uvicorn backend.api:app --reload
```

Start the frontend in a separate terminal:

```bash
python -m http.server 5500 --directory frontend
```

Open `http://localhost:5500`.

Alternatively, run the application using Docker:

```bash
docker compose up -d
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3.2
docker compose exec api python -m backend.rag
```

## Retrieval Evaluation

Statyra includes a self-made evaluation JSON file that measures how effectively the retrieval pipeline identifies relevant legislative provisions for natural-language questions.

The evaluation dataset contains **34 questions**, each associated with expected legislative references.

### Evaluation Results

| Metric | Result |
|--------|--------|
| Evaluation questions | 34 |
| Recall@15 | 79.4% |
| Minimum CI threshold | 70% |
| Indexed legislative subsections | 568 |

Recall@15 measures the proportion of evaluation questions for which the correct legislative provision appears within the top 15 retrieved results.

The evaluation can be run using:

```bash
python -m tests.test_rag --k 5 15 --min-recall 0.70
```

Results may vary if the indexed data, embedding model, or retrieval configuration changes.

## Current Limitations

- Covers only five UK criminal law Acts.
- Legislation is stored as a snapshot, without automatic amendment tracking.
- Retrieval uses vector similarity rather than hybrid search.
- The evaluation dataset is relatively small.
- The application currently runs locally and has not been deployed.

## References

- [UK Legislation API](https://www.legislation.gov.uk/developer)
- [LangChain RAG From Scratch](https://www.youtube.com/playlist?list=PLfaIDFEXuae2LXbO1_PKyVJiQ23ZztA0x)
