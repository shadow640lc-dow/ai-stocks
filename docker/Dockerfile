FROM python:3.11-slim

WORKDIR /app

# Set PYTHONPATH to include the app directory
ENV PYTHONPATH=/app

# Install Poetry
# Pin the Poetry major that generated poetry.lock (lock format 2.1)
RUN pip install poetry==2.4.1

# Copy only dependency files first for better caching
COPY pyproject.toml poetry.lock* README.md /app/

# Install dependencies only: the project itself is run from /app via PYTHONPATH,
# and its source packages are copied in the next layer.
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy rest of the source code
COPY . /app/

# Default command (will be overridden by Docker Compose)
CMD ["python", "src/main.py"] 
