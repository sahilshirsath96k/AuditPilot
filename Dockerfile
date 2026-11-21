# Use the Python version tested by AuditPilot
FROM python:3.14-slim

# Production environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AUDIT_TRAIL_LOG_PATH=/app/runtime/audit_trail.jsonl

WORKDIR /app

# Install production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only application files and required operational data
COPY main.py .
COPY auditpilot/ ./auditpilot/
COPY data/ ./data/
COPY docs/ ./docs/

# Create a non-root user and persistent output directories
RUN useradd --system --uid 10001 --create-home auditpilot \
    && mkdir -p /app/runtime \
    && chown -R auditpilot:auditpilot /app

USER auditpilot

# Application port
EXPOSE 8080

# Health check without calling Gemini
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

# Start the production API server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
