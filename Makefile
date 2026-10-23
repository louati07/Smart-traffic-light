.PHONY: help up down test lint demo build clean

help:
	@echo "Available commands:"
	@echo "  make up      - Start Docker Compose stack (api, mongo, web)"
	@echo "  make down    - Stop Docker Compose stack"
	@echo "  make test    - Run unit, golden, and integration tests"
	@echo "  make lint    - Run code linting and style checks"
	@echo "  make demo    - Seed demo runs and start mock environment"
	@echo "  make build   - Build all Docker images"
	@echo "  make clean   - Clean cache and temporary files"

up:
	docker compose up -d mongo api web

down:
	docker compose down

build:
	docker compose build

test:
	python -m pytest server/tests vision/tests -v
	cd web && npm test -- --run

lint:
	python -m ruff check server vision
	cd web && npm run lint

demo:
	python scripts/seed_demo_data.py
	@echo "Starting full system in mock demo mode..."
	python server/app/mock_esp32.py &
	uvicorn server.app.main:app --host 0.0.0.0 --port 8000

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
