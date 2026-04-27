# ================================================
# Dockerfile - FastAPI Chat Application
# Multi-stage build for production deployment
# ================================================

# Stage 1: Dependencies
FROM python:3.12-slim AS dependencies

WORKDIR /tmp
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Application
FROM python:3.12-slim AS runtime

# Create non-root user for security
RUN groupadd -r chatapp && useradd -r -g chatapp -d /home/chatapp -m chatapp

# Copy installed packages from build stage
COPY --from=dependencies /install /usr/local

# Set working directory to parent — app is a sub-package
WORKDIR /home/chatapp

# Copy application code as 'app' package
COPY . ./app/

# Change ownership
RUN chown -R chatapp:chatapp /home/chatapp

# Switch to non-root user
USER chatapp

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start the application — app.main:app since app is a package
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
