# Attribution and modifications

This repository is based on Giovanni Pasqualino's MIT-licensed
[`agentic-rag-for-dummies`](https://github.com/GiovanniPasq/agentic-rag-for-dummies).
The original copyright notice is preserved in [`LICENSE`](LICENSE).

The enterprise-oriented version in this repository independently adds or
rewrites the following areas:

- PDF, DOCX, XLSX, Markdown and TXT ingestion;
- Parent-Child chunking with persistent parent recovery;
- Milvus Dense + BM25 retrieval, RRF fusion and BGE reranking;
- explicit LangGraph routing, bounded retries and evidence checking;
- allow-listed structured-data and mock business tools;
- FastAPI, validated SSE output and a Gradio management interface;
- deterministic synthetic-data generators and frozen evaluation protocols;
- Docker Compose deployment, regression tests and benchmark reporting.

All companies, people, product identifiers, prices and internal policies used
by the demo or benchmark generators are fictional.
