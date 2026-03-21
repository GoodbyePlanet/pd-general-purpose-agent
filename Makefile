.PHONY: install run build up down restart logs health

# Local
install:
	uv sync

run:
	uv run python main.py

# Docker
build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

health:
	curl -s http://localhost:8000/health