# List available commands
default:
    @just --list

# Run the FastAPI backend
run-api:
    @echo "🚀 Starting FastAPI backend on http://localhost:8089..."
    uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8089

# Run the Next.js frontend
run-frontend:
    @echo "🚀 Starting Next.js frontend on http://localhost:3000..."
    cd src/frontend && npm run dev

# Run linting checks for both Python and Next.js
lint: lint-python lint-frontend

# Run formatting checks for both Python and Next.js
fmt: fmt-python fmt-frontend

# Lint Python code with ruff
lint-python:
    @echo "🐍 Linting Python code with ruff..."
    uv run ruff check src/

# Format Python code with ruff
fmt-python:
    @echo "🐍 Formatting Python code with ruff..."
    uv run ruff format src/

# Lint Next.js frontend
lint-frontend:
    @echo "⚛️  Linting Next.js frontend..."
    cd src/frontend && npm run lint

# Format Next.js frontend (check only)
fmt-frontend:
    @echo "⚛️  Checking Next.js frontend formatting..."
    cd src/frontend && npm run lint

# Fix Python linting issues automatically
fix-python:
    @echo "🐍 Fixing Python linting issues..."
    uv run ruff check --fix src/

# Auto-fix all issues (Python)
fix: fix-python
    @echo "✅ Auto-fix complete"
