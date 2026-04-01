# Traffic Monitoring Hackathon Scaffold

This repository contains the initial scaffold for a modular traffic monitoring system.

The current product scope is:

- detect vehicles and track them across frames
- classify vehicle type
- detect traffic violations such as overspeeding, no helmet, and wrong lane
- detect and read license plates when visible
- optionally capture a motorbike rider face when feasible

## What Is In Place

- `pyproject.toml` for `uv`-managed Python packaging
- `src/traffic_monitoring/` for application code
- `docs/` for design and implementation notes
- `todo.md` for a granular execution checklist

## Setup

```bash
uv sync
```

After dependencies are available, the package should be importable from the source tree:

```bash
uv run python -c "from traffic_monitoring.config import build_default_config; print(build_default_config())"
```

Run the smoke test pipeline on the bundled sample:

```bash
uv run traffic-monitor --input input.mp4 --output output/annotated.mp4
```

## Repository Conventions

- model weights belong in `models/`
- generated videos and snapshots belong in `output/`
- sample videos can live at the repository root or in a dedicated data directory
- configuration should stay in code, not scattered across scripts

## Notes On Scope

Helmet detection is a violation module, not the entire product.
The core demo should focus on traffic violation detection and plate identification, with motorbike face capture treated as best-effort if visibility allows.

## Next Implementation Layer

The next step is to add the runtime pipeline modules for:

- video input and output
- detection and tracking
- violation evaluation
- plate OCR
- speed estimation
- annotation and persistence
