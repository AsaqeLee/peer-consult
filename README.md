# Peer-Consult

English | [简体中文](./README_ZH.md)

A multi-agent **peer consultation** skill and small Python toolkit for collecting independent coding or architecture advice from several AI systems before you commit to a decision.

## Overview

Peer-Consult orchestrates isolated consultations so answers are gathered separately, then synthesized under explicit rules (agreement first, then verifiability / lower risk). It is a developer workflow aid—not an automated production decision engine.

## Features / scope

- Skill / CLI oriented consultation flow for coding and architecture questions
- Independent agent responses with a deterministic synthesis preference order:
  1. Overlapping recommendations across agents
  2. Preference for options that are easier to verify (e.g., stronger test coverage)
  3. Preference for options with fewer architectural side effects when agents diverge
- Python package under `src/peer_consult/` with tests under `tests/`
- Supporting references under `reference/` and `reference.md`
- Tooling via `pyproject.toml` (Ruff) and `requirements.txt`

## Requirements

- Python 3.8+
- Dependencies from `requirements.txt`
- Downstream AI CLIs or skills as documented in `README_ZH.md` / `reference.md` (Codex, Claude Code, etc.)

## Getting started

```bash
git clone https://github.com/AsaqeLee/peer-consult.git
cd peer-consult
pip install -r requirements.txt
pytest tests/
```

Inspect `bin/`, `src/peer_consult/`, and `reference.md` for skill installation and consultation commands specific to your agent host.

## Project layout

```text
peer-consult/
├── pyproject.toml
├── requirements.txt
├── bin/
├── src/peer_consult/
├── tests/
├── reference.md
├── reference/
└── README_ZH.md
```

## Status / limitations

Research / personal tooling. Synthesis heuristics are simple and transparent; they do not replace human judgment. Earlier “high-integrity / military” marketing language is intentionally avoided here.

## License

MIT. See [LICENSE](LICENSE).
