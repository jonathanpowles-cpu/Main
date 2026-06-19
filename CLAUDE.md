# CLAUDE.md

This file provides context for AI assistants working on this repository.

## Repository

- **Name**: Battle of Britain — Operational Simulation
- **Owner**: jonathanpowles-cpu
- **Description**: A strategic/operational simulation of the Battle of Britain (July–October 1940), playable as either RAF Fighter Command or Luftwaffe

## Development Setup

### Prerequisites

- Python 3.11+
- pip

### Getting Started

```bash
pip install -r requirements.txt
python run.py
# Open http://localhost:5000
```

## Project Structure

```
.
├── CLAUDE.md                  # AI assistant guidance (this file)
├── requirements.txt           # Python dependencies (Flask)
├── run.py                     # Entry point — starts Flask dev server on port 5000
├── app/
│   ├── __init__.py            # Flask app factory (create_app)
│   ├── routes.py              # API endpoints and page routes
│   ├── templates/
│   │   └── index.html         # Single-page game UI
│   └── static/
│       ├── css/style.css      # Dark-themed military UI styles
│       └── js/game.js         # Frontend: map rendering, UI updates, API calls
├── simulation/
│   ├── engine.py              # Core GameEngine — turn processing, player commands
│   ├── combat.py              # Air combat resolution (fighter vs fighter, bomber attacks)
│   ├── weather.py             # Weather system with Markov chain transitions
│   └── ai.py                  # AI opponent logic — raid generation, RAF intercepts, radar detection
├── models/
│   ├── enums.py               # All enumerations (Side, AircraftStatus, GamePhase, etc.)
│   ├── aircraft.py            # AircraftType specs and Aircraft instances
│   ├── pilot.py               # Pilot with experience, fatigue, morale, status
│   ├── squadron.py            # Squadron management and sortie strength
│   ├── airfield.py            # Airfield damage, repair, fuel/ammo supply
│   ├── radar.py               # Chain Home / Chain Home Low radar stations
│   └── game_state.py          # GameState container — loads all data, tracks stats
├── data/
│   ├── aircraft_types.json    # 11 aircraft types with historical specs
│   ├── raf_squadrons.json     # 54 RAF Fighter Command squadrons (July 1940 OOB)
│   ├── luftwaffe_units.json   # 33 Luftwaffe Geschwader (July 1940 OOB)
│   ├── airfields.json         # 51 airfields (34 RAF + 17 Luftwaffe)
│   └── radar_stations.json    # 22 radar stations (17 CH + 5 CHL)
└── tests/
    └── __init__.py
```

## Architecture

### Backend (Python / Flask)

- **GameEngine** (`simulation/engine.py`) orchestrates the game loop: weather, phase updates, repairs, production, AI raids, combat resolution, aircraft return
- **GameState** (`models/game_state.py`) holds all data in memory — no database. Loads from JSON at startup and generates pilot/aircraft instances procedurally
- **Combat** (`simulation/combat.py`) resolves fighter-vs-fighter and fighter-vs-bomber engagements using skill, aircraft stats, and random rolls
- **AI** (`simulation/ai.py`) generates Luftwaffe raids (target selection by phase) and RAF intercepts; handles radar detection with range/altitude checks

### Frontend (Vanilla JS / Canvas)

- Single-page app with setup screen and game screen
- Canvas-based map of southern England with coastlines, airfield markers, radar coverage arcs, and raid indicators
- Side panel with tabs: Overview (force stats), Squadrons (filterable list), Orders (scramble/raid controls), Intel (event log)
- All state fetched via REST API — no websockets

### Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/state` | Full game state for UI rendering |
| POST | `/api/advance` | Advance one turn (time step) |
| POST | `/api/scramble` | Scramble a squadron (RAF player) |
| POST | `/api/launch_raid` | Launch a bombing raid (Luftwaffe player) |
| POST | `/api/set_side` | Change player side |
| POST | `/api/set_time_scale` | Set hours per turn (1/4/12/24) |
| POST | `/api/new_game` | Reset and start new game |

### Historical Data

All JSON data files use historical orders of battle as of approximately July 10, 1940. Aircraft specs (speed, armament, firepower ratings) are based on documented performance. Airfield and radar coordinates use real-world lat/lon.

### Simulation Phases

The game progresses through four historical phases based on date:
1. **Kanalkampf** (Jul 10–Aug 3): Channel convoy attacks, small raids
2. **Adlerangriff** (Aug 4–Aug 28): Eagle Attack, radar/airfield strikes
3. **Airfield Attacks** (Aug 29–Oct 2): Sustained attacks on sector stations
4. **London Blitz** (Oct 3+): Strategic shift to bombing London

## Build & Run

```bash
python run.py              # Start dev server at http://localhost:5000
python -c "from simulation.engine import GameEngine; e = GameEngine()"  # Quick load test
```

No build step needed — Flask serves static files directly.

## Testing

```bash
python -m pytest tests/    # Run test suite (tests are minimal currently)
```

## Code Style & Conventions

- Python 3.11+ with type hints (use `X | None` not `Optional[X]`)
- Dataclasses for models, no ORM
- All game data in `data/*.json`, loaded at startup
- Enum values are lowercase snake_case strings
- Frontend uses vanilla JS — no framework, no build tools
- CSS custom properties for theming in `:root`

## Git Workflow

- **Default branch**: `main`
- Write clear, concise commit messages describing *why*, not just *what*
- Keep commits focused — one logical change per commit

## AI Assistant Guidelines

- Read this file at the start of every session for up-to-date context
- Keep this file current when adding frameworks, changing structure, or establishing new conventions
- Prefer editing existing files over creating new ones
- Do not add features or abstractions beyond what is requested
- Do not commit secrets, credentials, or `.env` files
- When modifying data JSON files, validate them with `python -c "import json; json.load(open('data/FILE.json'))"`
- After changing simulation logic, test with a quick run: `python -c "from simulation.engine import GameEngine; e = GameEngine(); e.advance_turn()"`
