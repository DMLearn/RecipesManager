# RecipesManager

**RecipesManager** is a Django REST Framework application used as a **test-bed and showcase** for running a multi-agent LLM cluster inside a GitHub Actions CI pipeline. The Django app itself is a simple recipe CRUD API — the real focus is `agent.py`, which wires together three LlamaIndex agents that automatically review every pull request.

Use this repo as a reference when integrating an agent cluster into your own GitHub Actions workflows.

---

## What the agent cluster does

On every pull request the CI pipeline runs a three-agent LlamaIndex `AgentWorkflow`:

```
ReviewAndPostingAgent  (root / entry point)
       │
       ├──► ContextAgent        — fetches PR metadata & diffs from the GitHub API
       │
       └──► CommentorAgent      — writes a structured markdown review comment
```

Each agent can hand off control to another agent and they share state through a workflow-level key-value store (`ctx.store`). When the review is ready, `ReviewAndPostingAgent` posts it directly to the PR via the GitHub API.

### Agents at a glance

| Agent | Tools available | Responsibility |
|---|---|---|
| `ContextAgent` | `get_pr_details`, `get_commit_details`, `get_changed_files`, `get_file_content`, `store_context_state` | Gather PR info and persist it in shared state |
| `CommentorAgent` | `retrieve_context_state`, `submit_draft_review` | Read context, draft a 200-300 word markdown review, save to shared state |
| `ReviewAndPostingAgent` | `retrieve_context_state`, `post_review_to_github` | Quality-check the draft, then post it to the PR |

---

## Repository structure

```
RecipesManager/
├── agent.py                  # Multi-agent PR review workflow (LlamaIndex + OpenAI)
├── app/
│   ├── models.py             # Recipe model
│   ├── serializers.py        # DRF serializers
│   ├── views.py              # API views
│   ├── urls.py               # App URL routes
│   └── tests/                # Pytest test suite
├── recipes/                  # Django project settings and root URLs
├── manage.py
├── pyproject.toml            # Poetry dependencies
└── .github/workflows/ci.yml  # CI pipeline (tests + agent review)
```

---

## CI/CD integration

The GitHub Actions workflow (`.github/workflows/ci.yml`) triggers on every pull request and does two things:

1. **Tests** — runs migrations and the full pytest suite with coverage reporting
2. **Agent review** — invokes `agent.py` with the PR context, which runs the agent cluster and posts a review comment back to the PR

### How it works in the workflow

```yaml
- name: Review agent
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    REPOSITORY: ${{ github.repository }}
    PR_NUMBER: ${{ github.event.pull_request.number }}
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    OPENAI_API_BASE: ${{ secrets.OPENAI_API_BASE }}   # optional — for custom endpoints
  run: poetry run python agent.py $GITHUB_TOKEN $REPOSITORY $PR_NUMBER $OPENAI_API_KEY $OPENAI_API_BASE
```

`agent.py` accepts config via **both environment variables and positional CLI arguments** so it works in any CI environment.

### Required GitHub Actions permissions

The workflow job needs these permissions to post PR reviews:

```yaml
permissions:
  checks: write
  pull-requests: write
```

`GITHUB_TOKEN` is automatically provided by Actions; you only need to set it as a secret if running outside Actions.

---

## Setup guide

### 1. GitHub repository secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `OPENAI_API_BASE` | No | Custom OpenAI-compatible base URL (e.g. Azure OpenAI, local Ollama proxy) |

`GITHUB_TOKEN` is injected automatically by GitHub Actions — no manual setup needed.

### 2. Install dependencies locally

```bash
git clone https://github.com/your-org/RecipesManager.git
cd RecipesManager
poetry install
poetry shell
```

### 3. Run the agent locally

Create a `.env` file:

```dotenv
GITHUB_TOKEN=ghp_your_token_here
OPENAI_API_KEY=sk-your_key_here
OPENAI_API_BASE=                   # leave blank to use api.openai.com
REPOSITORY=owner/repo              # or full URL: https://github.com/owner/repo
PR_NUMBER=42
```

Then run:

```bash
poetry run python agent.py
```

The agent streams its progress to stdout — you can follow each agent transition and tool call in real time.

---

## How the agent cluster communicates

Agents share data through a workflow-level store (`ctx.store`). Here is the data flow:

```
ContextAgent
  → stores PR metadata under key "pr_<number>_context"

CommentorAgent
  → reads "pr_<number>_context"
  → stores finished draft under key "draft_review"

ReviewAndPostingAgent
  → reads "draft_review"
  → posts to GitHub if quality check passes
  → or hands back to CommentorAgent with feedback
```

Hand-offs between agents are declared with `can_handoff_to` on each `FunctionAgent`. The `AgentWorkflow` routes execution based on these declarations.

---

## Quickstart (Django app)

```bash
# Apply database migrations
poetry run python manage.py migrate

# Create a superuser for the admin interface
poetry run python manage.py createsuperuser

# Run the development server
poetry run python manage.py runserver
```

### API endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/recipes/` | List all recipes |
| `POST` | `/api/recipes/` | Create a recipe |
| `GET` | `/api/recipes/<id>/` | Retrieve a recipe |
| `PUT` | `/api/recipes/<id>/` | Update a recipe |
| `DELETE` | `/api/recipes/<id>/` | Delete a recipe |

---

## Development

```bash
# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=app

# Format & lint
poetry run black . && poetry run isort . && poetry run flake8 .
```

---

## Key dependencies

| Package | Purpose |
|---|---|
| `llama-index-core` | `AgentWorkflow`, `FunctionAgent`, `FunctionTool`, `Context` |
| `llama-index-llms-openai` | OpenAI LLM adapter (supports custom base URLs) |
| `PyGithub` | GitHub API client for PR/commit data and posting reviews |
| `python-dotenv` | Load secrets from `.env` locally |
| `djangorestframework` | REST API for the recipes app |
| `poetry` | Dependency management |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on issues, pull requests, coding style, and tests.

## License

MIT License. See [LICENSE](LICENSE) for details.
