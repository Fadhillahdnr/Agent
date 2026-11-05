FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# Model embedding multibahasa diunduh saat build agar runtime tidak butuh internet untuk embedding.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN mkdir -p /opt/models && python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}', cache_dir='/opt/models')" \
    && chmod -R a+rX /opt/models
COPY copilot ./copilot
COPY pytest.ini docker-compose.yml ./
COPY tests ./tests
COPY scripts ./scripts
COPY examples ./examples
RUN useradd -u 10001 -m copilot && chown -R copilot /app
USER copilot
EXPOSE 8000
CMD ["uvicorn", "copilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
