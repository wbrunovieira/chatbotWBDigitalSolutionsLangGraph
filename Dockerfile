# Lightweight image - no PyTorch, uses FastEmbed (ONNX)
FROM python:3.11-slim

WORKDIR /app

# Install minimal build dependencies (for grpcio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Remove build tools to reduce image size
RUN apt-get purge -y build-essential && apt-get autoremove -y

# Copy application code (respects .dockerignore)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
