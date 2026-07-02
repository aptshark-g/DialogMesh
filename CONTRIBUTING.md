# Contributing to DialogMesh

Thank you for your interest in contributing to DialogMesh! This document covers everything you need to set up a development environment, follow our coding style, write tests, and submit pull requests.

## Development Environment Setup

### Prerequisites

- **Python** 3.11 or higher (3.11 recommended)
- **Git** 2.30+
- **Virtual environment** tool (`venv`, `virtualenv`, or `conda`)
- (Optional) **Docker** 24.0+ for containerized testing

### Step-by-Step Setup

1. **Fork and clone the repository**

   ```bash
   git clone https://github.com/yourusername/DialogMesh.git
   cd DialogMesh
   ```

2. **Create and activate a virtual environment**

   ```bash
   # Using venv
   python -m venv .venv
   source .venv/bin/activate       # Linux / macOS
   .venv\Scripts\activate          # Windows

   # Or using conda
   conda create -n dialogmesh python=3.11
   conda activate dialogmesh
   ```

3. **Install the project in editable mode with all optional dependencies**

   ```bash
   pip install -e ".[all]"
   ```

   If you only need the core + dev tools:

   ```bash
   pip install -e ".[dev,metrics,config]"
   ```

4. **Download models (required for integration tests)**

   ```bash
   python scripts/download_models.py --bge-only
   ```

5. **Verify the installation**

   ```bash
   python core/agent/health_check.py
   pytest core/agent/v3_0/planning/tests/test_planning.py -v
   ```

## Code Style

We use **ruff** for linting and formatting, and **mypy** for static type checking.

### Running the linters

```bash
# Check all files
ruff check .

# Auto-fix issues where possible
ruff check . --fix

# Format all files
ruff format .

# Type-check the v3.0 core packages
mypy core/agent/v3_0 core/service/v3_0
```

### Style Rules (from `pyproject.toml`)

| Tool | Key Settings | Value |
|------|------------|-------|
| `ruff` | `line-length` | `120` |
| `ruff` | `select` | `E`, `F`, `W`, `I`, `N`, `UP`, `B`, `C4`, `SIM` |
| `ruff` | `ignore` | `E501` (line too long, handled by formatter), `B008` (function-call in default arg) |
| `ruff` | `pydocstyle.convention` | `google` |
| `mypy` | `python_version` | `3.11` |
| `mypy` | `warn_return_any` | `true` |
| `mypy` | `ignore_missing_imports` | `true` |

### General Guidelines

- **Docstrings**: Use Google-style docstrings for all public classes and methods.
- **Type hints**: All function signatures must include type hints. Use `from __future__ import annotations` to avoid runtime `typing` imports where possible.
- **Naming**: `PascalCase` for classes, `snake_case` for functions and variables, `UPPER_SNAKE_CASE` for constants.
- **No mutable default arguments**: Use `dataclasses.field(default_factory=list)` or `None` with an explicit guard.
- **Prefer early returns** over deeply nested `if` blocks.
- **Keep functions focused**: A single function should do one thing. If it exceeds ~60 lines, consider splitting it.
- **Chinese comments**: Core algorithm comments may be bilingual (Chinese + English) for readability, but **docstrings and public API docs must be in English**.
- **Technical terms**: English technical terms (LLM, Cognitive Tree, Fusion Engine, SchemaGuard, etc.) should NOT be translated in Chinese comments.

## Commit Convention

We follow the **Conventional Commits** specification. This enables automated changelog generation and semantic versioning.

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

| Type | Use When |
|------|----------|
| `feat` | Adding a new feature or capability |
| `fix` | Fixing a bug |
| `docs` | Documentation-only changes |
| `style` | Code style changes (formatting, semicolons, etc.) that do not affect logic |
| `refactor` | Code changes that neither fix a bug nor add a feature |
| `perf` | Performance improvements |
| `test` | Adding or correcting tests |
| `chore` | Build process, dependency updates, auxiliary tooling |
| `ci` | CI/CD configuration changes |
| `revert` | Reverting a previous commit |

### Scopes

Common scopes for this project (v3.0):

- `cognitive_tree` — changes to `core/agent/v3_0/cognitive_tree/`
- `cognitive_compiler` — changes to `core/agent/v3_0/cognitive_compiler/`
- `llm_providers` — changes to `core/agent/v3_0/llm_providers/`
- `context_manager` — changes to `core/agent/v3_0/context_manager/`
- `planning` — changes to `core/agent/v3_0/planning/`
- `tool_registry` — changes to `core/agent/v3_0/tool_registry/`
- `observability` — changes to `core/agent/v3_0/observability/`
- `orchestrator` — changes to `core/agent/v3_0/orchestrator/`
- `service` — changes to `core/service/v3_0/`
- `config` — configuration system
- `docs` — documentation files
- `tests` — test suite

### Examples

```bash
# Good
feat(planning): add TreeOfThought skill primitive with backtracking
fix(cognitive_tree): handle concurrent transaction edge case
perf(llm_providers): batch embedding calls to reduce API overhead by 40%
docs(api): add v3.0 architecture diagram with Mermaid
test(observability): add Prometheus metrics exporter tests

# Bad (avoid)
update stuff
fix bug
```

## Testing Requirements

All new features and bug fixes must include tests. We use **pytest** as the test runner.

### Test Structure

```
core/agent/v3_0/<module>/tests/
  test_<component>.py          # Unit tests for a single module
core/service/v3_0/tests/
  test_service.py               # Service layer tests
tests/
  test_integration_<name>.py   # Integration tests across multiple modules
  conftest.py                   # Shared fixtures and hooks
```

### Running Tests

```bash
# Run the full v3.0 test suite (327 tests)
pytest core/agent/v3_0/ core/service/v3_0/ -v

# Run with coverage report
pytest core/agent/v3_0/ core/service/v3_0/ --cov=core --cov-report=term-missing

# Run a specific module's tests
pytest core/agent/v3_0/planning/tests/ -v
pytest core/agent/v3_0/cognitive_tree/tests/ -v
pytest core/agent/v3_0/tool_registry/tests/ -v

# Run only fast tests (exclude integration/slow tests)
pytest core/agent/v3_0/ core/service/v3_0/ -v -m "not slow"
```

### Writing Tests

- **Unit tests**: Mock external dependencies (LLM API, SQLite, network) using `unittest.mock` or `pytest-mock`.
- **Integration tests**: Use real (but lightweight) models. Tag them with `@pytest.mark.slow` if they take > 5 seconds.
- **Fixture cleanup**: Use `pytest.fixture(autouse=True)` or `setUp`/`tearDown` to reset global state.
- **Assertions**: Prefer `assert result == expected` over `self.assertEqual` (we are in pytest land, not unittest).
- **Parametrize**: Use `@pytest.mark.parametrize` for testing multiple inputs against the same function.

### Example Test Template

```python
import pytest
from core.agent.v3_0.planning.models import PlanNode, SkillInvocation
from core.agent.v3_0.planning.planner import Planner


class TestPlanner:
    """Unit tests for the Planner task decomposition."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        # Reset any global state if needed
        yield

    def test_single_task_returns_single_node(self):
        planner = Planner()
        plan = planner.plan("What is the capital of France?")
        assert len(plan.nodes) == 1
        assert plan.nodes[0].skill_name == "SearchVerifyExecute"
```

## Pull Request Workflow

### Before You Start

1. **Check existing issues** to avoid duplicate work.
2. **Open a draft PR early** if the change is large (> 200 lines) so maintainers can provide directional feedback.
3. **Discuss breaking changes** in an issue before coding.

### Branch Naming

```
<category>/<description>
```

Examples:
- `feat/planning-tree-of-thought`
- `fix/cognitive-tree-transaction-race`
- `docs/v3.0-api-reference`

### PR Checklist

Before marking your PR as ready for review, ensure:

- [ ] `ruff check .` passes with no errors.
- [ ] `mypy core/agent/v3_0 core/service/v3_0` passes (or new ignores are justified).
- [ ] `pytest core/agent/v3_0/ core/service/v3_0/ -v` passes (or explain why a test is intentionally skipped).
- [ ] New code is covered by tests (aim for > 80% line coverage on new logic).
- [ ] Docstrings and type hints are present for all public APIs.
- [ ] `CHANGELOG.md` is updated under the `[Unreleased]` section (if applicable).
- [ ] `README.md` and `README_EN.md` are updated if user-facing behavior changes.
- [ ] Commit messages follow the Conventional Commits format.

### Review Process

1. **Automated checks**: CI runs `ruff`, `mypy`, and `pytest` on every push.
2. **Maintainer review**: At least one approval from a core maintainer is required.
3. **Squash merge**: PRs are squash-merged into `main`. The merge commit title should match the Conventional Commits format.
4. **Release tagging**: After merge, maintainers may tag a release if the change warrants a version bump.

## Reporting Bugs

Use the GitHub issue tracker and include:

- **Python version** and **OS**.
- **Steps to reproduce** (minimal code snippet).
- **Expected vs. actual behavior**.
- **Logs** (with `DIALOGMESH_LOGGING__LEVEL=DEBUG` if relevant).
- **Health check output** (`python core/agent/health_check.py`).

## Security

If you discover a security vulnerability, please do **not** open a public issue. Instead, email the maintainers directly or use GitHub's private vulnerability reporting feature.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Questions?** Open a [GitHub Discussion](https://github.com/yourusername/DialogMesh/discussions) or reach out in the issue tracker.
