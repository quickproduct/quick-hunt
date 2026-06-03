# Contributing to QuickHunt

First off, thank you for considering contributing to QuickHunt! Contributions from developers like you are what make open-source projects sustainable and robust.

---

## Code of Conduct

We expect all contributors to adhere to respect, inclusive terminology, and collaboration. Please be welcoming and supportive.

---

## Local Development Setup

To configure the application locally:

### 1. Backend (Python)
1. Ensure you have **Python 3.11+**, PostgreSQL (with pgvector), and Redis available.
2. Install dependencies:
   ```bash
   pip install -r backend/requirements-shared.txt
   pip install -r backend/services/api/requirements.txt
   pip install -r backend/services/scraper/requirements.txt
   ```
3. Run the test suite to confirm your setup:
   ```bash
   python -m pytest -c backend/pytest.ini backend/tests/unit/
   ```

### 2. Frontend (Next.js)
1. Ensure you have **Node.js 20+** installed.
2. Install dependencies:
   ```bash
   cd frontend/dashboard
   npm install
   ```
3. Run the Next.js dev server:
   ```bash
   npm run dev
   ```

---

## Coding Guidelines

### 1. Python Style Guide
- Code must pass `flake8` (max line length 120) and be formatted with `black`.
- Add or update tests under `backend/tests/unit/` or `backend/tests/integration/` for new logic.
- Use Alembic migrations for any schema change — never edit the database by hand.

### 2. Next.js / TypeScript Style Guide
- Prefer typed components and hooks; avoid un-typed `any`.
- Keep `next lint` clean.
- Format all files using Prettier standards.

---

## Submitting Pull Requests (PRs)

1. Fork the repository and create your branch from `main`.
2. Write unit tests for new logic where possible.
3. Verify that the build completes successfully:
   - Python: `python -m pytest -c backend/pytest.ini backend/tests/unit/`
   - Next.js: `cd frontend/dashboard && npm run build`
4. Follow commit naming conventions:
   - `feat: ...` for new features
   - `fix: ...` for bug fixes
   - `docs: ...` for documentation changes
   - `chore: ...` for config or linter updates
5. Open your PR against the QuickHunt `main` branch.
