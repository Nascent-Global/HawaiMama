FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY server.py ./

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision && \
    python -m pip install .

COPY .env.example ./.env.example
COPY data ./data

RUN mkdir -p surveillance surveillance/output output wwwroots input models

EXPOSE 8000

CMD ["python", "server.py"]
