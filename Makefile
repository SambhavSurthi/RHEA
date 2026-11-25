.PHONY: install dev infra up down test lint eval clean help

COMPOSE := docker compose -f infra/docker-compose.yml

help:
	@echo "install  - install package + dev extras"
	@echo "dev      - run FastAPI with reload"
	@echo "infra    - start Neo4j + Qdrant"
	@echo "up       - build and run the whole stack (API + frontend)"
	@echo "down     - stop the whole stack (data volumes kept)"
	@echo "test     - run the backend test suite"
	@echo "lint     - ruff check backend and frontend"
	@echo "eval     - run the evaluation harness"
	@echo "clean    - remove caches"

install:
	python -m pip install -e '.[dev]'

dev:
	uvicorn rhea.main:app --reload

infra:
	$(COMPOSE) up -d neo4j qdrant

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

test:
	pytest

lint:
	ruff check backend/rhea backend/tests frontend/streamlit_app.py

eval:
	python -m app.pipelines.runner

clean:
	python -c "import shutil,pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; shutil.rmtree('.pytest_cache', ignore_errors=True); shutil.rmtree('.ruff_cache', ignore_errors=True)"
