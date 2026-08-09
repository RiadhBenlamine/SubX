# SUBX — Subdomain Recon Framework

[![PyPI Version](https://img.shields.io/pypi/v/subx-recon.svg)](https://pypi.org/project/subx-recon/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

SUBX is a fast subdomain enumeration, DNS resolution, and HTTP probing tool built for security researchers, bug bounty hunters, and pentesters.

It pulls subdomains concurrently from 12 passive OSINT sources (Shodan, Censys, VirusTotal, crt.sh, Chaos, etc.), filters them against your target scope, stores everything in PostgreSQL or SQLite, and integrates with `dnsx` and `httpx` for DNS resolution and web probing.

---

## How it works

```
                       ┌─────────────────────────────────┐
                       │               CLI               │
                       └────────────────┬────────────────┘
                                        │
                                        ▼
                       ┌─────────────────────────────────┐
                       │         Services Layer          │
                       └──────┬───────────────────┬──────┘
                              │                   │
                              ▼                   ▼
                       ┌──────────────┐   ┌──────────────┐
                       │PluginManager │   │ ToolManager  │
                       └──────┬───────┘   └──────┬───────┘
                              │                   │
                              ▼                   ▼
                       ┌──────────────┐   ┌──────────────┐
                       │ Passive APIs │   │ Active Tools │
                       │ (12 sources) │   │(dnsx & httpx)│
                       └──────────────┘   └──────────────┘
```

1. **Passive Enumeration**: Queries 12 APIs concurrently using `asyncio` with real-time terminal streaming.
2. **Scope Filtering & Deduplication**: Cleans findings, checks wildcard boundaries, and deduplicates against existing target assets.
3. **DNS Probing (`dnsx`)**: Resolves subdomains to IP addresses and tracks active A/CNAME records.
4. **HTTP Probing (`httpx`)**: Probes live web targets for HTTP status codes, titles, and tech stacks.
5. **Smart Pipeline**: When both `dnsx` and `httpx` are configured, HTTP probing automatically runs only against DNS-resolved active hosts to save time.

---

## Features

- **Concurrent Async Engine** — Parallel queries across all passive OSINT sources.
- **Scope Control** — In-scope and out-of-scope domain boundary enforcement.
- **DNS & HTTP Probing** — Built-in `dnsx` (DNS resolution & IP mapping) and `httpx` (liveness, titles, technologies).
- **Smart Pipeline Optimization** — Runs HTTP probes exclusively against subdomains that resolve via DNS.
- **Database Storage** — SQLite out of the box, with full PostgreSQL support for team workflows.
- **Historical Tracking** — Tracks `first_seen`, `last_seen`, and `last_seen_alive` timestamps for asset monitoring.
- **DB Query & Views** — Terminal tables for web status (`--web`), DNS resolution (`--dns`), tech stack, or custom SQL.
- **Project Export** — Automatically generates `recon/` folders with plain-text output files (`subdomains.txt`, `alive.txt`, `ips.txt`, `techs.txt`).

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

### From PyPI (Recommended)

```bash
pip install subx-recon
```

### From Source

```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
pip install -e .
```

Or using [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
uv sync
```

### Debian / Ubuntu / Kali (.deb)

Download the `.deb` from the [latest release](https://github.com/RiadhBenlamine/SubX/releases) and install:

```bash
sudo apt install ./subx_2.1.1-1_all.deb
```

**Requirements:** Python >= 3.10

---

## Configuration

Create a `config.yaml` file (a sample is available in `config_samples/config.yaml_sample`):

```yaml
scope:
  - example.com
  - target.org

out_of_scope:
  - testing.example.com

# Omit sources to run all available plugins
sources:
  - ShodanPlugin
  - CrtshPlugin
  - ChaosPlugin

api_keys:
  SHODAN_API: "your-key-here"
  VIRUSTOTAL_API: "your-key-here"
  OTX_API: "your-key-here"
  URLSCAN_API: "your-key-here"
  CHAOS_API: "your-key-here"
  BEVIGIL_API: "your-key-here"
  VIEWDNS_API: "your-key-here"
  CENSYS_API: "your-key-here"

# Tool parameters for active probing pipeline
tools:
  dnsx:
    threads: 100
  httpx:
    threads: 50
    rate-limit: 150
```

You can also store API keys in `~/.config/subx/.env` (e.g. `SHODAN_API=your-key`). `config.yaml` values take priority.

---

## Usage

```bash
subx [COMMAND] [OPTIONS]
```

### Enumerate Subdomains

```bash
subx enum -c config.yaml
```

Runs all configured passive plugins against your scope. Results stream to your terminal in real-time and are saved to the database.

- `-c`, `--config` — Path to config file (required)
- `--save` / `--no-save` — Toggle database saving (default: save)
- `-p`, `--project` — Auto-export project directory after scan
- `--debug` — Enable verbose debug logs

### DNS Probing (`dns-probe`)

Resolve stored subdomains using `dnsx` to get IP addresses:

```bash
subx dns-probe -d example.com
```

- `-d`, `--domain` — Target domain (required)
- `-oN <file>` — Save resolved subdomains (one per line)
- `-oX '<sep>:<file>'` — Custom separator output (e.g. `';:resolved.txt'`)
- `-oI`, `--output-ip <file>` — Save resolved subdomains with IP addresses (`subdomain [ip]`)
- `-p`, `--project` — Export project directory structure after probing

### HTTP Probing (`http-probe`)

Probe stored subdomains for web liveness, HTTP codes, titles, and technologies using `httpx`:

```bash
subx http-probe -d example.com
```

*Note: If `dnsx` is configured in `config.yaml`, `http-probe` automatically resolves subdomains first and probes only active DNS hosts.*

- `-d`, `--domain` — Target domain (required)
- `-oN <file>` — Save alive subdomains
- `-oX '<sep>:<file>'` — Custom separator output
- `-oT`, `--output-tech <file>` — Save subdomains with tech stack (e.g. `app.example.com [Nginx, React]`)
- `-p`, `--project` — Export project directory after probing

### Query Database (`db`)

Inspect tracked assets, view web status or DNS mappings, and export filtered targets:

```bash
# List tracked target domains
subx db

# List subdomains for a target
subx db -d example.com

# Show DNS resolution view (Resolved status + IP Address)
subx db -d example.com --dns

# Show Web liveness view (Alive status, HTTP Code, Title, Tech)
subx db -d example.com --web

# Filter by DNS resolution status
subx db -d example.com --resolved --dns
subx db -d example.com --unresolved

# Filter by Web liveness status
subx db -d example.com --alive --web
subx db -d example.com --down

# Filter by technology or plugin source
subx db -d example.com --filter-tech Nginx
subx db -d example.com --filter-plugin ShodanPlugin

# Run custom read-only SQL query
subx db -C "SELECT subdomain, ip, status_code FROM subx_subdomain WHERE target='example.com' AND alive=true"

# Export filtered subdomains to file
subx db -d example.com --alive -oN live.txt

# Delete domain records
subx db -d example.com --delete
```

### Export Project Workspace

```bash
subx project -d example.com
```

Creates a structured output directory under `projects/`:

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

You can also pass `-p` / `--project` to `enum`, `http-probe`, `dns-probe`, or `db` commands.

### Database Setup & Migrations

```bash
# Setup PostgreSQL database connection
subx init-db -H 127.0.0.1 -u postgres -P "password" -d subx

# Import an existing SQLite database into PostgreSQL
subx import-sqlite subx.db

# Apply schema migrations when updating SUBX
subx dev-migrate
```

---

## PostgreSQL Setup

SUBX uses SQLite by default. To connect to a PostgreSQL database:

1. Run `subx init-db` (saves connection info to `~/.config/subx/config.yaml`), or
2. Set the `DATABASE_URL` environment variable:

```bash
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/subx"
```

---

## Release Automation

```bash
python scripts/release.py patch  # 2.1.0 -> 2.1.1
python scripts/release.py minor  # 2.1.0 -> 2.2.0
```

---

## Contributing

See [DEV_DOCS.md](DEV_DOCS.md) for technical architecture details, plugin development guides, and implementation rules.

---

## License

MIT — see [LICENSE](LICENSE) for details.
