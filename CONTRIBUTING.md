# Contributing to CRUDAdmin

Thank you for your interest in contributing to CRUDAdmin! This guide is meant to make it easy for you to get started.

## Setting Up Your Development Environment

### Cloning the Repository
Start by forking and cloning the CRUDAdmin repository:

```sh
git clone https://github.com/benavlabs/crudadmin.git
```

### Using UV for Dependency Management
CRUDAdmin uses UV for managing dependencies. If you don't have UV installed, follow the instructions on the [official UV website](https://docs.astral.sh/uv/guides/install-python/).

Once UV is installed, navigate to the cloned repository.

### Activating the Virtual Environment
UV can a virtual environment for your project. Activate it using:

```sh
uv venv
```

Then:

```sh
source .venv/bin/activate
```

This project supports Python versions `>=3.9.2`. However, for consistency and compatibility across environments, we recommend using **Python 3.9.x** (with a minimum of 3.9.2) when setting up the virtual environment, as specified in the `.python-version` file.

### Installing Dependencies
Install the required dependencies using UV:
```sh
uv sync --group dev
```

## Making Contributions

### Coding Standards
- Follow PEP 8 guidelines.
- Write meaningful tests for new features or bug fixes.

### Testing with Pytest
CRUDAdmin uses pytest for testing. Run tests using:
```sh
uv run pytest
```

### Pre-commit Hooks
CRUDAdmin uses pre-commit to automatically check code quality before each commit. It helps enforce
linting, formatting, and type checking.

After installing the development dependencies:

```sh
uv run pre-commit install
```

This will set up thee Git hooks to run automatically before every commit.

*Running hooks Manually*
To run all hooks on all files:
```sh
uv run pre-commit run --all-files
```

This will run:
- `ruff` fot linting and formatting
- `mypy` for type checking
- basic formatting checks (trailing whitespace, EOF, file size)

Make sure all pre-commit checks pass before submitting a PR.

### Linting
Use mypy for type checking:
```sh
uv run mypy crudadmin
```

Use ruff for style:
```sh
uv run ruff check --fix
uv run ruff format
```

Ensure your code passes linting before submitting.

## Submitting Your Contributions

### Creating a Pull Request
After making your changes:

- Push your changes to your fork.
- Open a pull request with a clear description of your changes.
- Update the README.md if necessary.


### Code Reviews
- Address any feedback from code reviews.
- Once approved, your contributions will be merged into the main branch.

## Code of Conduct
Please adhere to our [Code of Conduct](CODE_OF_CONDUCT.md) to maintain a welcoming and inclusive environment.

Thank you for contributing to CRUDAdmin🚀
