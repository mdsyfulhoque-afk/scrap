# Data_Fetcher_Ubuntu Documentation Package

This package contains the documentation and Copilot handover files for the current Data_Fetcher_Ubuntu project state.

## Files

- `01_PROJECT_DOCUMENTATION.md` — complete project documentation and requirements context.
- `02_CURRENT_STATUS.md` — verified current state and completed work.
- `03_ARCHITECTURE_OVERVIEW.md` — system architecture and data flow.
- `04_DATABASE_DOCUMENTATION.md` — current PostgreSQL/schema documentation.
- `05_PHASE1B_CONTINUATION.md` — exact continuation sequence.
- `06_COPILOT_MASTER_PROMPT.md` — task-specific master prompt for GitHub Copilot.

## Important

The existing permanent Copilot instruction file is intentionally NOT included in this package because it already exists in the repository:

```text
.github/copilot-instructions.md
```

Verified current size:

```text
14K
676 lines
```

Do not overwrite it with a shortened copy.

## Installation

Extract this package into:

```text
/run/media/farhan/New Volume/Projects/Data_Fetcher_Ubuntu
```

The `docs/` directory should contain the six Markdown documentation files.

Then use:

```text
docs/06_COPILOT_MASTER_PROMPT.md
```

as the task-specific Copilot handover.

## Usage

Run a controlled fetch demo against a local or allowed URL:

```bash
python -m data_fetcher.demo http://127.0.0.1:8000/ok
```

## Current next step

The immediate infrastructure task is to verify/create the MinIO:

```text
raw
```

bucket, then continue with Phase 1B database/storage assessment.

Do not start broad crawling or Phase 2 preprocessing.

## Windows Setup

This project requires Docker Desktop for PostgreSQL and MinIO services.

**Prerequisites:**
- Python 3.14+
- Docker Desktop for Windows

**Setup:**
1. Install Docker Desktop for Windows
2. Start Docker Desktop
3. Copy `.env.example` to `.env` and configure credentials
4. Run `docker compose up -d` from project root
5. Create Python virtual environment: `python -m venv venv_windows`
6. Activate: `venv_windows\Scripts\activate`
7. Install dependencies: `pip install -e .`
8. Run tests: `pytest tests/`
