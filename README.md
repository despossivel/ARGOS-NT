<p align="center">
  <img src="argos.jpeg" alt="Argos Panoptes — the hundred-eyed watcher" width="480"/>
</p>

<h1 align="center">ARGOS-NT</h1>

<p align="center">
  <em>Named after Argos Panoptes — the hundred-eyed giant of Greek mythology who sees everything.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue?style=flat-square" alt="version"/>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python" alt="python"/>
  <img src="https://img.shields.io/badge/LLM-Ollama%20%7C%20OpenAI%20%7C%20Anthropic%20%7C%20DeepSeek-blueviolet?style=flat-square" alt="LLM providers"/>
  <img src="https://img.shields.io/badge/graph-Neo4j-008CC1?style=flat-square&logo=neo4j" alt="Neo4j"/>
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="license"/>
</p>

---

**ARGOS-NT** is an open-source OSINT intelligence pipeline that transforms raw investigation briefs into structured, graph-persisted intelligence — powered by LLMs and orchestrated external tooling.

It extracts entities, fires the right OSINT tools automatically, correlates findings, and stores everything in Neo4j — giving analysts a connected knowledge graph instead of scattered outputs.

---

## Features

- **LLM-powered entity extraction** — identifies emails, usernames, phone numbers, and domains from free-text investigation briefs
- **Automated tool orchestration** — selects and runs the right OSINT tools per entity type
- **Multi-provider LLM support** — Ollama (local/offline), OpenAI, Anthropic, DeepSeek; switch without code changes
- **Graph intelligence persistence** — all findings written to Neo4j for cross-case correlation
- **Dork generation** — produces TXT and JSON structured Google dork plans per target
- **Dual interface** — interactive CLI menu (`argos-menu`) and Textual TUI (`argos-tui`)
- **Boot health checks** — validates config, tools, provider, and Neo4j before any run

---

## Architecture

```
Investigation Brief (text/markdown)
        │
        ▼
   [ Sifter Agent ]   ← entity extraction via LLM
        │
        ▼
   [ Scout Agent ]    ← OSINT tool orchestration
        │
        ▼
   [ Analyst Agent ]  ← result correlation & enrichment
        │
        ▼
  [ Architect Agent ] ← graph persistence (Neo4j)
        │
        ▼
   [ Pipeline ]       ← report + dork artifact generation
```

---

## Project Layout

```
argos_nt/
├── agents/       # Sifter, Scout, Analyst, Architect, Pipeline
├── core/         # Boot checks, history, scan & report services
├── drivers/      # Neo4j driver, provider manager
├── tools/        # OSINT tool executor wrappers
└── ui/           # Textual TUI app & banner manager
config/
└── config.json   # Runtime configuration (providers, paths, flags)
data/
├── input/        # Investigation briefs (.md / .txt)
└── output/       # Artifacts, dorks, reports
```

---

## Installation

```bash
pip install -e .
```

Development dependencies:

```bash
pip install -e .[dev]
```

---

## Start Services

Neo4j only:

```bash
docker compose up -d
```

Neo4j + Ollama (local LLM):

```bash
docker compose --profile ai up -d
```

---

## Configure LLM Provider

```bash
argos-menu
```

Navigate to:

- `Configure provider` → select Ollama, OpenAI, Anthropic, or DeepSeek
- `Configure credentials` → add API keys where required
- `View all provider status` → verify active provider readiness

---

## Startup Health Check

Before opening the menu, `argos-menu` runs an automated boot sequence that validates:

| Check | Description |
|---|---|
| Config loading | `config/config.json` is valid |
| I/O directories | `data/input` and `data/output` exist |
| OSINT tools | Required binaries are available in PATH |
| Active provider | LLM provider is reachable and responding |
| Neo4j | Database connection is alive |

Critical failures block startup and surface actionable error messages.

---

## Run the Pipeline

**Direct run:**

```bash
argos-run data/input/target_001.md
```

**Full scan** (enables all optional tools):

```bash
argos-run data/input/target_001.md --full-scan
```

**Interactive CLI menu:**

```bash
argos-menu --verbose
```

**Textual TUI:**

```bash
argos-tui
```

---

## OSINT Tooling Flow

ARGOS-NT selects tools automatically based on extracted entity types:

| Entity | Tools |
|---|---|
| Email | `holehe`, `leaker`, `ghunt` · `h8mail` *(full scan)* |
| Username | `sherlock`, `leaker`, `maigret` · `toutatis`, `socialscan` *(full scan)* |
| Phone | `ignorant`, `whatspy` |
| Domain | `s3scanner` *(full scan)* |
| Person / Any | Dork plan generation (TXT + JSON) |

All artifacts are written to `data/output/`.

---

## Dork Artifacts

For every person, email, or username entity found, ARGOS-NT generates:

- `dorks_<target>_<timestamp>.txt` — human-readable dork plan
- `dorks_<target>_structured_<timestamp>.json` — machine-readable structured plan

---

## OSINT Tool Installation

See [`install-tools.md`](install-tools.md) for the full setup guide for all supported external tools.

---

## Contributing

Issues and pull requests are welcome. If you integrate a new OSINT tool or LLM provider, please open a PR with tests and update `install-tools.md` accordingly.

---

<p align="center">
  Built with eyes wide open.<br/>
  <a href="https://github.com/despossivel">@despossivel</a>
</p>
