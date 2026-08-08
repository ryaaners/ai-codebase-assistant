FROM python:3.12-slim

# git: needed to clone GitHub repos. build-essential: some deps
# (tree-sitter's language packages) ship prebuilt wheels for common
# platforms, but this keeps a source build working as a fallback.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/repos

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
