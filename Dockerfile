FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files. loobric.py is here too because pyproject.toml
# force-includes it for the `loobric` console script, and hatchling resolves
# that include eagerly at install time (before the `COPY . .` below).
COPY pyproject.toml setup.py README.md loobric.py ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 smooth && chown -R smooth:smooth /app
USER smooth

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "smooth.main:app", "--host", "0.0.0.0", "--port", "8000"]
