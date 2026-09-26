# CLAUDE.md

This file provides context for AI assistants working on this repository.

## Repository

- **Name**: MyFitnessPal nutrient connector
- **Owner**: jonathanpowles-cpu
- **Description**: An MCP server and CLI that turns a nutrition information panel (a meal-kit recipe card, a packet label) into a private custom food in MyFitnessPal

This repository previously also held a Battle of Britain simulation. That game
was removed; see **Repository history** below for where it lives now.

## Development Setup

### Prerequisites

- Python 3.11+
- pip

### Getting Started

```bash
pip install -r requirements.txt
python -m connectors.myfitnesspal serve            # MCP server on stdio
python -m connectors.myfitnesspal parse label.txt  # parse a panel, print JSON
```

See `connectors/myfitnesspal/README.md` for install, hosting and phone usage.

## Project Structure

```
.
├── CLAUDE.md                  # AI assistant guidance (this file)
├── requirements.txt           # Python dependencies (mcp, requests, pydantic, uvicorn)
├── render.yaml                # Render blueprint for the hosted connector
├── connectors/
│   └── myfitnesspal/
│       ├── README.md          # Install, auth, hosting, phone links, tools, CLI
│       ├── __main__.py        # CLI: parse / create / serve
│       ├── nutrition.py       # NutritionFacts model, unit handling, label parsing
│       ├── mfp_client.py      # MyFitnessPal client: cookies -> token -> create food
│       ├── server.py          # MCP server and its tools
│       ├── auth.py            # Password-guarded OAuth 2.1 server for hosted mode
│       ├── links.py           # Shareable per-food links and their phone page
│       └── Dockerfile         # Build from the repo root
└── tests/
    ├── test_nutrition.py      # Label parsing and unit conversion
    ├── test_mfp_client.py     # Payload building and client (HTTP mocked)
    ├── test_mfp_server.py     # MCP tools
    ├── test_mfp_auth.py       # Hosted OAuth flow end to end
    └── test_mfp_links.py      # Shareable food links and the phone page
```

## Architecture

MyFitnessPal has **no public API**. The client uses the website's private flow
with the cookies of a logged-in browser session:

```
cookies -> GET /user/auth_token -> bearer token -> POST /v2/foods
```

Keep every request shape in `mfp_client.py` alone, so they are easy to update
when those endpoints change.

### The three ways in

| Mode | Entry point | Used by |
|------|-------------|---------|
| stdio MCP | `serve` | Claude Desktop, Claude Code |
| hosted HTTP | `serve --transport http` | claude.ai web and mobile, behind `auth.py` |
| CLI | `parse`, `create` | Terminal, scripting |

Never expose the HTTP transport without the password OAuth server in
`auth.py`: the process holds the user's MyFitnessPal session cookies. The
server refuses to start over HTTP when `CONNECTOR_PASSWORD` is unset.

### Units

Labels are Australian or European: energy in kJ, values per serving and per
100 g. MyFitnessPal wants kcal, grams, and milligrams for sodium, potassium
and cholesterol. `nutrition.py` normalises all of that, and derives the
serving weight from the ratio of the two columns.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `MFP_COOKIE_HEADER` / `MFP_COOKIES_FILE` | MyFitnessPal session cookies |
| `CONNECTOR_PASSWORD` | Guards the hosted server and the phone pages |
| `CONNECTOR_SECRET` | Signs clients, tokens and food links so a redeploy does not disconnect Claude |
| `PUBLIC_URL` / `RENDER_EXTERNAL_URL` | The public HTTPS address in hosted mode |

Never commit any of these.

## Testing

```bash
python -m pytest tests/
```

Live calls to MyFitnessPal are **not** covered: the service is unreachable
from the sandbox and all HTTP is mocked. Treat the endpoint shapes as
unverified against production until someone runs a real create.

## Code Style & Conventions

- Python 3.11+ with type hints (use `X | None` not `Optional[X]`)
- Dataclasses for models, no ORM
- Pure functions for parsing and payload building, so they stay testable
- Keep MyFitnessPal request shapes in `mfp_client.py` only

## Git Workflow

- **Branch to work from**: `main`. Base every change on it and merge back into it.
- Write clear, concise commit messages describing *why*, not just *what*
- Keep commits focused — one logical change per commit

> **GitHub's default branch setting is still `claude/claude-md-docs-06s3gq`**, a
> leftover game branch. A fresh `git clone` therefore checks out the game, not
> this connector. Until someone changes it under Settings → Branches, always
> `git checkout main` after cloning, and never assume the clone landed there.

## Repository history

The Battle of Britain simulation was removed from this repository. **It now
lives at [jonathanpowles-cpu/battle-of-britain](https://github.com/jonathanpowles-cpu/battle-of-britain)**,
with its full ten-commit history, verified running from a fresh clone.

Two branches here still hold copies of it. Both are now redundant:

| Branch | What |
|--------|------|
| `battle-of-britain-archive` | This repo immediately before the removal, game included |
| `claude/claude-md-docs-06s3gq` | The same game tree that was pushed to the new repository |

They can be deleted, but only in this order: GitHub still has the second one
set as this repository's default branch, and a default branch cannot be
deleted. Change the default to `main` first, then delete both.

## AI Assistant Guidelines

- Read this file at the start of every session for up-to-date context
- Keep this file current when adding frameworks, changing structure, or establishing new conventions
- Prefer editing existing files over creating new ones
- Do not add features or abstractions beyond what is requested
- Do not commit secrets, credentials, or `.env` files
- After changing the connector, run `python -m pytest tests/`
