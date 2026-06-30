# Contributing to MemoryGraph

Thank you for your interest in contributing to MemoryGraph! This document covers everything you need to set up a development environment, follow our coding style, write tests, and submit pull requests.

## Development Environment Setup

### Prerequisites

- **Python** 3.10 or higher (3.11 recommended)
- **Git** 2.30+
- **Virtual environment** tool (`venv`, `virtualenv`, or `conda`)
- (Optional) **Docker** 24.0+ for containerized testing

### Step-by-Step Setup

1. **Fork and clone the repository**

   ```bash
   git clone https://github.com/yourusername/memorygraph.git
   cd memorygraph
   ```

2. **Create and activate a virtual environment**

   ```bash
   # Using venv
   python -m venv .venv
   source .venv/bin/activate       # Linux / macOS
   .venv\Scripts\activate          # Windows

   # Or using conda
   conda create -n memorygraph python=3.11
   conda activate memorygraph
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
   pytest tests/test_discourse_pytest.py -v
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

# Type-check the core package
mypy core/agent
```

### Style Rules (from `pyproject.toml`)

| Tool | Key Settings | Value |
|------|------------|-------|
| `ruff` | `line-length` | `120` |
| `ruff` | `select` | `E`, `F`, `W`, `I`, `N`, `UP`, `B`, `C4`, `SIM` |
| `ruff` | `ignore` | `E501` (line too long, handled by formatter), `B008` (function-call in default arg) |
| `ruff` | `pydocstyle.convention` | `google` |
| `mypy` | `python_version` | `3.10` |
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

Common scopes for this project:

- `compiler` — changes to `core/agent/compiler/`
- `discourse` — changes to `core/agent/discourse_block_tree/`
- `config` — configuration system
- `metrics` — metrics and observability
- `plugin` — plugin system
- `mcp` — MCP protocol layer
- `service` — FastAPI / service layer
- `persistence` — storage and database layers
- `docs` — documentation files
- `tests` — test suite

### Examples

```bash
# Good
feat(discourse): add BDI (Burst Drift of Intent) boundary detection
fix(compiler): handle empty clause list in SyntacticDecomposer
perf(metrics): batch embedding calls to reduce BGE overhead by 40%
docs(api): add ARCHITECTURE.md with Mermaid data-flow diagrams
refactor(config): migrate all hard-coded thresholds to DiscourseConfig

# Bad (avoid)
update stuff
fix bug
```

## Testing Requirements

All new features and bug fixes must include tests. We use **pytest** as the test runner.

### Test Structure

```
tests/
  test_<component>.py          # Unit tests for a single module
  test_integration_<name>.py  # Integration tests across multiple modules
  conftest.py                  # Shared fixtures and hooks
```

### Running Tests

```bash
# Run the full test suite
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=core/agent --cov-report=term-missing

# Run a specific test file
pytest tests/test_plugin_system.py -v

# Run only discourse block tree tests
pytest tests/test_discourse_pytest.py -v

# Run with the slow/integration marker excluded
pytest tests/ -v -m "not slow"
```

### Writing Tests

- **Unit tests**: Mock external dependencies (BGE model, SQLite, network) using `unittest.mock` or `pytest-mock`.
- **Integration tests**: Use `DiscoursePipeline` with real (but lightweight) models. Tag them with `@pytest.mark.slow` if they take > 5 seconds.
- **Fixture cleanup**: Use `pytest.fixture(autouse=True)` or `setUp`/`tearDown` to reset global state (e.g., `PluginRegistry.clear()`).
- **Assertions**: Prefer `assert result == expected` over `self.assertEqual` (we are in pytest land, not unittest).
- **Parametrize**: Use `@pytest.mark.parametrize` for testing multiple inputs against the same function.

### Example Test Template

```python
import pytest
from core.agent.discourse_block_tree.models import EDU
from core.agent.discourse_block_tree.segmenter import Segmenter


class TestSegmenter:
    """Unit tests for the Segmenter boundary detection."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        # Reset any global state if needed
        yield

    def test_single_edu_returns_one_block(self):
        edu = EDU(id="e1", turn_index=0, edu_index=0, raw_text="Hello")
        seg = Segmenter(threshold=0.5)
        blocks = seg.segment([edu])
        assert len(blocks) == 1
        assert blocks[0].edu_count == 1
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
- `feat/plugin-system`
- `fix/segmenter-threshold-race`
- `docs/api-reference`

### PR Checklist

Before marking your PR as ready for review, ensure:

- [ ] `ruff check .` passes with no errors.
- [ ] `mypy core/agent` passes (or new ignores are justified).
- [ ] `pytest tests/` passes (or explain why a test is intentionally skipped).
- [ ] New code is covered by tests (aim for > 80% line coverage on new logic).
- [ ] Docstrings and type hints are present for all public APIs.
- [ ] `CHANGELOG.md` is updated under the `[Unreleased]` section (if applicable).
- [ ] `README_EN.md` is updated if user-facing behavior changes.
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
- **Logs** (with `MEMORYGRAPH_LOGGING__LEVEL=DEBUG` if relevant).
- **Health check output** (`python core/agent/health_check.py`).

## Security

If you discover a security vulnerability, please do **not** open a public issue. Instead, email the maintainers directly or use GitHub's private vulnerability reporting feature.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Questions?** Open a [GitHub Discussion](https://github.com/yourusername/memorygraph/discussions) or reach out in the issue tracker.
