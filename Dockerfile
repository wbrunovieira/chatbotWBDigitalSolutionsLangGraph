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

# Run as a non-root user — this is a public endpoint, so the process must not be root.
# /app stays root-owned (read-only to the app); the user gets a writable HOME so FastEmbed
# can cache its ONNX model there at runtime.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /home/appuser/.cache \
    && chown -R appuser:appuser /home/appuser
ENV HOME=/home/appuser \
    XDG_CACHE_HOME=/home/appuser/.cache \
    HF_HOME=/home/appuser/.cache/huggingface
USER appuser

EXPOSE 8000

# In-image healthcheck (compose overrides with an equivalent one). Uses Python, NOT curl —
# the slim base has no curl, which previously left the container perpetually unhealthy.
# Assert an exact 200. Generous start period to cover the first-boot FastEmbed model download.
HEALTHCHECK --interval=30s --timeout=5s --start-period=150s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
