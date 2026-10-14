.PHONY: install check test fetch build eval doctor

install:
	uv sync --all-groups

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pytest

test:
	uv run pytest

fetch:
	uv run ctrag -v fetch

build:
	uv run ctrag -v build

eval:
	uv run ctrag eval --generate

doctor:
	uv run ctrag doctor
