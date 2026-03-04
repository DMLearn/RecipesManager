# RecipesManager

**RecipesManager** is a Django REST Framework application for managing recipes. It exposes a REST API for creating, reading, updating, and deleting recipes, and includes an AI-powered agent that automatically reviews pull requests on GitHub.

## Features

- CRUD operations for recipes via a REST API
- AI agent (`agent.py`) that reviews GitHub pull requests using a multi-agent LlamaIndex workflow
- CI/CD pipeline with GitHub Actions (runs migrations, tests, and coverage on every push and PR)
- Dependency management with Poetry

## Project Structure

```
RecipesManager/
├── agent.py              # Multi-agent PR review workflow (LlamaIndex + OpenAI)
├── app/
│   ├── models.py         # Recipe model
│   ├── serializers.py    # DRF serializers
│   ├── views.py          # API views
│   ├── urls.py           # App URL routes
│   └── tests/            # Pytest test suite
├── recipes/              # Django project settings and root URLs
├── manage.py
├── pyproject.toml        # Poetry dependencies
└── .github/workflows/    # CI pipeline configuration
```

## Installation

```bash
# Clone the repo
git clone https://github.com/your-org/RecipesManager.git
cd RecipesManager

# Install dependencies and activate the virtual environment
poetry install
poetry shell
```

## Quickstart

```bash
# Apply database migrations
poetry run python manage.py migrate

# Create a superuser for the admin interface
poetry run python manage.py createsuperuser

# Run the development server
poetry run python manage.py runserver
```

Open your browser and navigate to:

| Endpoint | Description |
|---|---|
| `GET  /api/recipes/` | List all recipes |
| `POST /api/recipes/` | Create a new recipe |
| `GET  /api/recipes/<id>/` | Retrieve a single recipe |
| `PUT  /api/recipes/<id>/` | Update a recipe |
| `DELETE /api/recipes/<id>/` | Delete a recipe |

## AI Agent

`agent.py` implements a multi-agent workflow that automatically reviews GitHub pull requests. It uses three agents:

- **ContextAgent** — fetches PR details and changed files from the GitHub API
- **CommentorAgent** — drafts a structured review comment in markdown
- **ReviewAndPostingAgent** — validates the draft and posts it to the PR

To run the agent, set the required environment variables and execute:

```bash
# Required environment variables (create a .env file)
GITHUB_TOKEN=your_github_token
OPENAI_API_KEY=your_openai_key
REPOSITORY=https://github.com/owner/repo
PR_NUMBER=42

poetry run python agent.py
```

## Development

1. **Install dependencies** (including dev dependencies):
   ```bash
   poetry install
   ```

2. **Run tests**:
   ```bash
   poetry run pytest
   ```

3. **Run tests with coverage**:
   ```bash
   poetry run pytest --cov=app
   ```

4. **Format & Lint**:
   ```bash
   poetry run black . && poetry run isort . && poetry run flake8 .
   ```

## CI/CD

The GitHub Actions workflow runs on every push and pull request to `main`. It:

1. Sets up Python and installs Poetry dependencies
2. Runs database migrations
3. Executes the full test suite with coverage reporting

See `.github/workflows/` for the workflow configuration.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on issues, pull requests, coding style, and testing.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

