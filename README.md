# SUBX — Subdomain Recon Framework

A fast, async subdomain enumeration and asset management toolkit for security researchers, pentesters, and bug bounty hunters.

SUBX pulls subdomains from 12 passive sources (Shodan, VirusTotal, Censys, crt.sh, Chaos, etc.), filters them against your scope, stores everything in a database, and optionally probes for HTTP liveness with `httpx`. It's built to fit into real-world recon workflows without getting in the way.

---

## How it works

```
                      ┌─────────────────────────────────┐
                      │               CLI               │
                      └────────────────┬────────────────┘
                                       │
                                       ▼
                      ┌─────────────────────────────────┐
                      │         Services Layer           │
                      └──────┬───────────────────┬──────┘
                             │                   │
                             ▼                   ▼
                      ┌──────────────┐   ┌──────────────┐
                      │PluginManager │   │ ToolManager   │
                      └──────┬───────┘   └──────┬───────┘
                             │                   │
                             ▼                   ▼
                      ┌──────────────┐   ┌──────────────┐
                      │ Passive APIs │   │ Active Tools  │
                      │ (12 sources) │   │   (httpx)     │
                      └──────────────┘   └──────────────┘
```

Plugins run concurrently via asyncio. Results are deduplicated, scope-filtered, and persisted with `first_seen` / `last_seen` timestamps so you can track changes over time.

---

## What's included

- **Async everything** — all API calls run concurrently, not sequentially
- **Plugin auto-discovery** — drop a `.py` file in `plugins/` and it's loaded automatically
- **Scope enforcement** — in-scope / out-of-scope filtering from your config
- **Persistent storage** — SQLite by default, PostgreSQL supported natively
- **HTTP probing** — built-in httpx integration for liveness, status codes, titles, and tech detection
- **Historical tracking** — `first_seen`, `last_seen`, and `last_seen_alive` timestamps
- **Project export** — auto-generated `recon/` directories with `subdomains.txt`, `alive.txt`, `dead.txt`, etc.
- **Cross-platform** — works on Linux, macOS, and Windows
- **Live progress** — real-time streaming of discovered subdomains during enumeration

---

## Passive Sources

| Source | API Key Required | Config Key |
|---|---|---|
| AlienVault OTX | Yes | `OTX_API` |
| AnubisDB | No | — |
| BeVigil | Yes | `BEVIGIL_API` |
| BGP Tools | No | — |
| Censys | Yes | `CENSYS_API` |
| Chaos (ProjectDiscovery) | Yes | `CHAOS_API` |
| crt.sh | No | — |
| HackerTarget | No | — |
| Shodan | Yes | `SHODAN_API` |
| urlscan.io | Yes | `URLSCAN_API` |
| ViewDNS | Yes | `VIEWDNS_API` |
| VirusTotal | Yes | `VIRUSTOTAL_API` |

---

## Installation

### From PyPI (recommended)

```bash
pip install subx-recon
```

### From source

```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
pip install -e .
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
uv sync
```

### Debian/Ubuntu/Kali (.deb)

Download the `.deb` from the [latest release](https://github.com/RiadhBenlamine/SubX/releases) and install:

```bash
sudo apt install ./subx_2.1.0-1_all.deb
```

**Requirements:** Python >= 3.10

---

## Setup

Create a `config.yaml` (there's a sample in `config_samples/`):

```yaml
scope:
  - example.com
  - target.org

out_of_scope:
  - testing.example.com

# Leave blank to run all plugins, or list specific ones
sources:
  - ShodanPlugin
  - CrtshPlugin

api_keys:
  SHODAN_API: "your-key-here"
  VIRUSTOTAL_API: "your-key-here"
  OTX_API: "your-key-here"
  URLSCAN_API: "your-key-here"
  CHAOS_API: "your-key-here"
  BEVIGIL_API: "your-key-here"
  VIEWDNS_API: "your-key-here"
  CENSYS_API: "your-key-here"
```

You can also keep API keys in `~/.config/subx/.env` (e.g. `SHODAN_API=your-key`). Config file values take priority.

---

## Usage

```bash
subx [COMMAND] [OPTIONS]

# From source:
uv run python main.py [COMMAND] [OPTIONS]
```

### Enumerate subdomains

```bash
subx enum -c config.yaml
```

Runs all configured plugins against your scope targets. Results are saved to the database by default. Subdomains stream to your terminal in real-time as each plugin returns results.

Options:
- `-c`, `--config` — path to your config file (required)
- `--save` / `--no-save` — toggle database persistence (default: save)
- `--project`, `-p` — auto-export project directory after scan
- `--debug` — verbose logging

### Probe for HTTP liveness

```bash
subx http-probe -d example.com
```

Reads subdomains from the database, runs `httpx` with tech detection, and updates records with status codes, titles, technologies, and timestamps.

Options:
- `-d`, `--domain` — target domain (required)
- `-oN <file>` — save alive subdomains, one per line
- `-oX '<sep>:<file>'` — custom separator output (e.g. `';:alive.txt'`)
- `-oT <file>` — save subdomains with tech stack (e.g. `app.example.com [Nginx, React]`)

### Query the database

```bash
# Show all tracked targets
subx db

# List subdomains for a target
subx db -d example.com

# Show web details (alive status, HTTP code, title, tech)
subx db -d example.com --web

# Filter by plugin source
subx db -d example.com --filter-plugin ShodanPlugin

# Filter by technology
subx db -d example.com --filter-tech Nginx

# Only alive / only dead
subx db -d example.com --alive
subx db -d example.com --down --web

# Subdomains discovered after a date
subx db -d example.com --new-since 2025-01-01

# Raw SQL query
subx db -C "SELECT subdomain, status_code, tech FROM subx_subdomain WHERE target='example.com' AND alive=1"

# Delete all records for a target
subx db -d example.com --delete

# Export to file
subx db -d example.com --alive -oN live_subs.txt
```

### Export project directories

```bash
subx project -d example.com
```

Creates a structured recon folder:

```
projects/
  └── example.com/
        └── recon/
              ├── subdomains.txt
              ├── alive.txt
              ├── dead.txt
              ├── techs.txt
              ├── status.txt
              ├── ips.txt
              └── sources.txt
```

You can also pass `--project` / `-p` to `enum`, `http-probe`, or `db` commands to auto-generate this after any operation.

### Initialize PostgreSQL

```bash
# Interactive setup
subx init-db

# Non-interactive
subx init-db -H 127.0.0.1 -u postgres -P "mypassword" -d subx
```

This creates the database, sets up schema tables, and saves the connection to `~/.config/subx/config.yaml` so all future commands use PostgreSQL.

### Import from SQLite

```bash
# Into your configured database
subx import-sqlite subx.db

# With explicit target
subx import-sqlite subx.db -t "postgresql+asyncpg://user:pass@localhost:5432/subx"
```

Migrates all targets, subdomains, probe results, timestamps, and source linkages.

### Database migrations

```bash
subx dev-migrate
```

Compares your database schema against current models and adds any missing columns. Creates a backup first by default (skip with `--no-backup`).

---

## PostgreSQL support

SUBX works with SQLite out of the box. To switch to PostgreSQL, either:

1. Run `subx init-db` (recommended), or
2. Set the `DATABASE_URL` environment variable:

```bash
export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/subx"
```

All commands work identically on both backends.

---

## Release automation

```bash
# Bump patch (2.0.19 → 2.0.20)
python scripts/release.py patch

# Bump minor (2.0.19 → 2.1.0)
python scripts/release.py minor

# Set exact version
python scripts/release.py 2.1.0
```

Handles version bumping, tests, wheel/sdist/deb builds, PyPI upload, git tagging, and GitHub push.

---

## Contributing

See [DEV_DOCS.md](DEV_DOCS.md) for the architecture guide, API reference, layering rules, and how to add new plugins or tool wrappers.

---

## License

MIT — see [LICENSE](LICENSE) for details.
