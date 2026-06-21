FROM python:3.14-slim

WORKDIR /app

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files terlebih dahulu untuk memanfaatkan Docker layer cache
COPY pyproject.toml uv.lock ./

# Install dependencies tanpa project (agar cache tidak invalidate saat source berubah)
RUN uv sync --frozen --no-install-project

# Copy seluruh source code
COPY . .

# Install project itu sendiri
RUN uv sync --frozen

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
