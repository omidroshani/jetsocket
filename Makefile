.PHONY: help build dev test test-all test-stress test-exchange test-coverage lint format typecheck check docs docs-serve clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Build
build: ## Build Rust extension (release)
	uv run maturin develop --release

dev: ## Build Rust extension (debug, faster compile)
	uv run maturin develop

# Test
test: ## Run tests (excludes stress/exchange)
	uv run pytest tests/ --benchmark-disable

test-all: ## Run all tests including stress
	uv run pytest tests/ -m "" --benchmark-disable

test-stress: ## Run stress tests only
	uv run pytest tests/stress/ -m stress --benchmark-disable

test-exchange: ## Run exchange integration tests (requires network)
	WSFABRIC_NETWORK_TESTS=1 uv run pytest tests/integration/exchanges/ -m exchange

test-coverage: ## Run tests with coverage report
	uv run pytest tests/ --cov=src/wsfabric --cov-report=term-missing --benchmark-disable

test-bench: ## Run benchmark tests
	uv run pytest tests/unit/test_benchmarks.py --benchmark-only

# Code quality
lint: ## Run linter
	uv run ruff check src/ tests/

format: ## Format code
	uv run ruff format src/ tests/
	uv run ruff check src/ tests/ --fix

typecheck: ## Run type checker
	uv run mypy src/wsfabric/ --strict

check: lint typecheck ## Run lint + typecheck

# Docs
docs: ## Build documentation
	uv run mkdocs build

docs-serve: ## Serve documentation locally
	uv run mkdocs serve

# Clean
clean: ## Remove build artifacts
	rm -rf site/ build/ dist/ .pytest_cache/ .mypy_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
