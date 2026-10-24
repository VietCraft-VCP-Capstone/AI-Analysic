FROM python:3.12-slim

WORKDIR /app

# Install system compiler tools for packages requiring compiling
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .

# Install requirements (using --no-cache-dir to decrease image size)
RUN pip install --no-cache-dir -r requirements.txt

ENV LI_MODEL_DIR=/opt/vietcraft-li/siglip2-base-patch16-224
COPY app/core/listing_intel/embedder.py app/core/listing_intel/
COPY scripts/li/fetch_models.py scripts/li/
RUN python -m scripts.li.fetch_models

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
