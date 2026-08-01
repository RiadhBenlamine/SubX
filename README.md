# SUBX 🚀 — Subdomain Recon Framework

`SUBX` is a fast, asynchronous attack-surface mapping and subdomain enumeration tool designed for security researchers, penetration testers, and bug bounty hunters.

It aggregates reconnaissance findings from multiple passive sources (like Shodan, VirusTotal, Censys, and ProjectDiscovery Chaos), filters results against custom target scopes, and manages the lifecycle of discovered assets inside a centralized SQLite database. 

It also supports integrated network active checks (like HTTP liveness, response codes, and HTML titles probing) utilizing external Go tools like `httpx`.

---

## Architecture Blueprint

```
                      ┌─────────────────────────────────┐
                      │           Typer CLI             │
                      └────────────────┬────────────────┘
                                       │
                                       ▼
                      ┌─────────────────────────────────┐
                      │         Services Layer          │
                      └──────┬───────────────────┬──────┘
                             │                   │
                             ▼                   ▼
                      ┌──────────────┐   ┌──────────────┐
                      │ PluginManager│   │ ToolManager  │
                      └──────┬───────┘   └──────┬───────┘
                             │                   │
                             ▼                   ▼
                      ┌──────────────┐   ┌──────────────┐
                      │ Passive APIs │   │ Active Tools │
                      │  (12 sources)│   │   (httpx)    │
                      └──────────────┘   └──────────────┘
```

---

## Features

* 🚀 **Asynchronous & Concurrent Execution**: Enumerates across all APIs concurrently using Python's `asyncio`.
* 🔌 **Dynamic Plugin System**: Auto-discovers and registers passive query engines dropped inside the `plugins/` directory.
* 🛡️ **Scope Isolation**: Prevents out-of-scope leakages by verifying targets against precise inclusions and exclusions defined in yaml format.
* 🗄️ **Persistent Asset Database**: Incremental saving to local SQLite via SQLModel/SQLAlchemy. Keeps track of `first_seen`, `last_seen`, and `last_seen_alive` timestamps.
* ⚡ **Integrated Probe & Tech Detection**: Built-in orchestration for probing stored domains using `httpx` with automatic web technology stack detection (e.g., Nginx, React, Cloudflare).
* 🕒 **Historical Liveness Tracking**: Preserves `last_seen_alive` timestamps when domains go down, allowing historical records of when a host was last active.
* 📁 **Structured Plain-Text Project Layout**: Automatically exports organized plain-text recon directories per target domain (`<domain>/recon/subdomains.txt`, `alive.txt`, `dead.txt`, `techs.txt`, `ips.txt`, `status.txt`, `sources.txt`).
* 💻 **Cross-Platform Tool Engine**: Seamless binary resolution across Windows, Linux (Kali/Debian), and macOS. Automatically checks bundled binaries, system `PATH`, and `~/go/bin`.
* 📊 **Rich Output Interfaces**: Visually appealing terminals powered by `Rich` tables, statuses, and panels.

---

## Passive Reconnaissance Sources

SubX queries the following platforms for subdomain listings.

| Source Engine | Requires API Key | Key Name in Config |
|---|---|---|
| **AlienVault OTX** | Yes | `OTX_API` |
| **AnubisDB** | No | — |
| **BeVigil** | Yes | `BEVIGIL_API` |
| **BGP Tools** | No | — |
| **Censys** | Yes | `CENSYS_API` |
| **Chaos (ProjectDiscovery)** | Yes | `CHAOS_API` |
| **crt.sh** | No | — |
| **HackerTarget** | No | — |
| **Shodan** | Yes | `SHODAN_API` |
| **urlscan.io** | Yes | `URLSCAN_API` |
| **ViewDNS** | Yes | `VIEWDNS_API` |
| **VirusTotal** | Yes | `VIRUSTOTAL_API` |

---

## Installation & Setup

### Prerequisites
* Python **>= 3.10**
* [uv](https://github.com/astral-sh/uv) (Recommended for simple execution without manual virtualenvs setup)

### 1. Clone & Install Dependencies
Clone the repository and install requirements:
```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
python -m pip install -e .
```

### 2. Configure Settings & API Keys
Create a config file (e.g., `config.yaml`) in your workspace. You can use the template inside [config_samples/config.yaml_sample](file:///c:/Users/DELL/PycharmProjects/SubX/config_samples/config.yaml_sample) as a starting point.

```yaml
# Target domains you want to enumerate
scope:
  - example.com
  - target.org

# Exclude specific domains/subdomains from results
out_of_scope:
  - testing.example.com
  - dev.target.org

# Omit to run all discoverable plugins, or specify names to restrict runs
sources:
  - ShodanPlugin
  - CrtshPlugin

# API keys for authenticating with passive services
api_keys:
  SHODAN_API: "YOUR_SHODAN_KEY_HERE"
  VIRUSTOTAL_API: "YOUR_VIRUSTOTAL_KEY_HERE"
  OTX_API: "YOUR_OTX_KEY_HERE"
  URLSCAN_API: "YOUR_URLSCAN_KEY_HERE"
  CHAOS_API: "YOUR_CHAOS_KEY_HERE"
  BEVIGIL_API: "YOUR_BEVIGIL_KEY_HERE"
  VIEWDNS_API: "YOUR_VIEWDNS_KEY_HERE"
  CENSYS_API: "YOUR_CENSYS_KEY_HERE"
```

> [!NOTE]
> Alternatively, you can store API keys as environment variables inside a file at `~/.config/subx/.env` (e.g., `SHODAN_API=key`). Projects-specific `config.yaml` values always override global `.env` settings.

---

## Installation

### Option 1: Install from PyPI
```bash
pip install subx
```

### Option 2: Install from Source
```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
uv sync
```

---

## Usage Guide

All CLI subcommands can be executed directly using `subx`:
```bash
subx [COMMAND] [OPTIONS]

# Or running from source checkout:
uv run python main.py [COMMAND] [OPTIONS]
```

### 1. Subdomain Enumeration (`enum`)
Start passive subdomain enumeration for target domains configured in your configuration file.

```bash
subx enum -c ./config.yaml
```

**Options:**
* `-c`, `--config` (Required): Path to your YAML or JSON config file.
* `--save` / `--no-save`: Toggle database persistence (Defaults to `--save`).

### 2. Probe & Detect Technologies (`http-probe`)
Check HTTP liveness, response status codes, page titles, and **web technology stacks** for subdomains stored in the database.

```bash
subx http-probe -d example.com
```

This command reads subdomains from the database, runs `httpx` with `-tech-detect` under the hood, and updates the database records with status codes (`200`, `404`), title tags, detected technologies (e.g., `Nginx, React, Cloudflare`), and timestamps (`last_seen` and `last_seen_alive`).

**Options:**
* `-d`, `--domain` (Required): Target domain to probe.
* `-oN <file>`: Output alive subdomain hostnames to a line-separated file.
* `-oX '<separator>:<file>'`: Output alive subdomains with a custom separator (e.g. `';:alive.txt'`).
* `-oT <file>`, `--output-tech <file>`: Save alive subdomains alongside their detected technology stack (e.g. `app.example.com [Nginx, React]`).

### 3. View & Query Assets (`db`)
List, filter, query, export, or delete records from the local asset database.

#### Summary of All Assets
```bash
subx db
```
Lists targets currently tracked in the database along with total subdomain counts and timestamps.

#### List Subdomains for a Target Domain
```bash
subx db -d example.com
```

#### List Subdomains with HTTP & Technology Details
View web liveness status, HTTP response status, page titles, detected tech stack, and `LAST ALIVE` timestamps:
```bash
subx db -d example.com --web
```

#### Filter Results
Filter domains discovered by a specific source engine:
```bash
subx db -d example.com --filter-plugin ShodanPlugin
```

Filter subdomains running a specific technology (e.g. `Nginx`, `WordPress`, `Cloudflare`):
```bash
subx db -d example.com --filter-tech Nginx
```

Filter subdomains that are currently **ALIVE** or currently **DOWN**:
```bash
# Only live subdomains
subx db -d example.com --alive

# Only subdomains currently down (preserves LAST ALIVE timestamp)
subx db -d example.com --down --web
```

Filter subdomains discovered after a specific date:
```bash
subx db -d example.com --new-since 2026-06-01
```

#### Custom Raw Queries
Execute raw SQL queries against your assets:
```bash
subx db -C "SELECT subdomain, alive, status_code, tech, last_seen_alive FROM subdomain WHERE target='example.com' AND alive=1"
```

#### Clean Up (Delete Target Records)
```bash
subx db -d example.com --delete
```

#### Export Subdomains & Tech to Files
Save filtered query results to a file:
```bash
# Line-separated subdomains
subx db -d example.com --alive -oN live_subs.txt

# Custom separator
subx db -d example.com --filter-tech Nginx -oX ';:nginx_subs.txt'

# Export subdomains with technology stack
subx db -d example.com --web -oT tech_export.txt
```

### 4. Project Directory Export (`project` & `--project`)
Set up a structured, plain-text recon directory layout for your target domains.

```bash
subx project -d example.com
```

This creates the following organized folder structure on disk:
```
projects/
  └── example.com/
        └── recon/
              ├── subdomains.txt   # All discovered subdomains
              ├── alive.txt        # Verified ALIVE subdomains
              ├── dead.txt         # Subdomains currently DOWN
              ├── techs.txt        # Subdomains with detected tech stack
              ├── status.txt       # Subdomains with HTTP status & title
              ├── ips.txt          # Subdomains with IP addresses
              └── sources.txt      # Subdomains with discovery sources
```

You can also pass `--project` / `-p` during `enum`, `http-probe`, or `db` commands to automatically generate/sync the project folder structure:
```bash
# Auto-generate project folder after passive enumeration
subx enum -c ./config.yaml --project

# Auto-generate project folder after HTTP probing
subx http-probe -d example.com --project
```

**Options:**
* `-d`, `--domain` (Required): Target domain name.
* `-o`, `--output-dir`: Base directory for projects (Default: `projects`).

### 5. PostgreSQL Database Engine Support
SubX natively supports both **SQLite** (default) and **PostgreSQL** database engines.

To connect SubX to a PostgreSQL database, set the `DATABASE_URL` environment variable:
```bash
export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/subx"
```

SubX will automatically create and manage all schema tables, indexes, constraints, and dialect-agnostic upsert statements on PostgreSQL.

### 6. Import SQLite Database into PostgreSQL (`import-sqlite`)
Migrate an existing SQLite database (e.g. `subx.db`) into your PostgreSQL database:

```bash
# Import into active PostgreSQL database (reads DATABASE_URL env var)
subx import-sqlite subx.db

# Import with explicit target PostgreSQL URL
subx import-sqlite subx.db -t "postgresql+asyncpg://user:pass@localhost:5432/subx"
```

This utility migrates all stored target domains, subdomains, status codes, page titles, tech tags, host IPs, first/last seen timestamps, and plugin source linkages cleanly.

### 7. Database Migrations (`dev-migrate`)
As SubX development progresses and database models change, migrate your database schema to keep it up to date:

```bash
subx dev-migrate
```

This command:
1. Creates a safety backup file: `subx.backup-<timestamp>.db`.
2. Inspects your existing SQLite tables and compares them to the latest Python models.
3. Automatically alters tables to add new, nullable columns safely.

**Options:**
* `--no-backup`: Skip creating the safety backup database before migrating.

---

## Development & Extension
If you want to contribute, build custom components, add discovery APIs, or write command wrappers, see the [Developer Documentation (DEV_DOCS.md)](file:///c:/Users/DELL/PycharmProjects/SubX/DEV_DOCS.md) for full API reference, layering rules, and extension workflows.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
