# Contributing to Ultrawhale

Thanks for your interest! Here's how to get started.

## Setup

```bash
git clone https://github.com/peterlodri-sec/ultrawhale-dogfood-pipeline.git
cd ultrawhale-dogfood-pipeline

# Install Python 3.12+ and uv, then:
uv sync --all-extras
```

## Development Workflow

1. **Create a branch** from `main`
2. **Make changes** — follow existing code style
3. **Run tests**: `uv run pytest`
4. **Run linter**: `uv run ruff check src/ tests/`
5. **Run type checker**: `uv run mypy src/`
6. **Format**: `uv run ruff format src/ tests/`
7. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat(scoring): add topic-weighting to quality score
   fix(upload): handle HF API rate limiting with backoff
   docs(readme): add quickstart section
   ```
8. **Open a PR** against `main`

## Running Tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/test_scoring.py -v

# With coverage
uv run pytest --cov=src/ultrawhale --cov-report=term-missing

# Skip tests that need HF_TOKEN
uv run pytest -m "not requires_hf_token"
```

## Code Style

- **Formatter**: ruff (via `ruff format`)
- **Linter**: ruff (via `ruff check`)
- **Type checker**: mypy
- **Line length**: 120 characters
- **Docstrings**: Google-style for public functions
- **Imports**: sorted via isort (standard library → third-party → ultrawhale)

Pre-commit hooks are configured in `.pre-commit-config.yaml`:

```bash
pre-commit install
pre-commit run --all-files
```

## Package Structure

```
src/ultrawhale/
├── __init__.py      # Package version
├── cli.py           # CLI entry point (ultrawhale command)
├── config.py        # Centralized configuration
├── logging.py       # Structured logging
├── generate.py      # Core generation engine
├── scoring.py       # Quality scoring functions
├── difficulty.py    # Difficulty sampling + active learning
├── curation.py      # LLM-judge curation
├── hf.py            # HuggingFace Inference client
├── orchestrator.py  # Parallel worker coordinator
├── resources.py     # Resource monitoring
├── kompress.py      # Post-processing compression
└── upload.py        # HF dataset upload
```

## PR Process

1. PR title follows Conventional Commits
2. CI must pass (lint, type-check, test, coverage)
3. At least one approval required
4. Squash-merge to `main`

## Release Process

Releases are cut by tagging:

```bash
git tag v2.0.0
git push origin v2.0.0
```

GitHub Actions builds the package and creates a GitHub Release automatically.
