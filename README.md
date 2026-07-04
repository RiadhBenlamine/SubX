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
* 🗄️ **Persistent Asset Database**: Incremental saving to local SQLite via SQLModel/SQLAlchemy. Keeps track of `first_seen` and `last_seen` timestamps.
* ⚡ **Integrated Probe Engine**: Built-in orchestration for probing stored domains using external tools without leaving the CLI.
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

## Usage Guide

All CLI subcommands are executed using `subx` or directly via python:
```bash
uv run python main.py [COMMAND] [OPTIONS]
# OR if installed in environment:
subx [COMMAND] [OPTIONS]
```

### 1. Subdomain Enumeration (`enum`)
Start passive subdomain enumeration for target domains configured in your configuration file.

```bash
subx enum -c ./config.yaml
```

**Options:**
* `-c`, `--config` (Required): Path to your YAML or JSON config file.
* `--save` / `--no-save`: Toggle database persistence (Defaults to `--save`).

### 2. Probe Discovered Targets (`http-probe`)
Filter, check, and update the HTTP status for subdomains discovered and saved for a target domain.

```bash
subx http-probe -d example.com
```

This commands reads the subdomains from the database, feeds them to `httpx` under the hood, and updates the database records with status codes (`200`, `404`, etc.), title tags, and liveness states (`alive = True`).

**Options:**
* `-d`, `--domain` (Required): Target domain to probe.
* `-oN <file>`: Output alive subdomain hostnames to a line-separated file.
* `-oX '<separator>:<file>'`: Output alive subdomains with a custom separator (e.g. `';:alive.txt'` for semicolon separation).

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

#### List Subdomains with HTTP Details
If you've run the `http-probe` command, you can view the HTTP liveness data:
```bash
subx db -d example.com --web
```

#### Filter Results
Filter domains that were discovered by a specific source engine:
```bash
subx db -d example.com --filter-plugin ShodanPlugin
```

Filter subdomains discovered after a specific date:
```bash
subx db -d example.com --new-since 2026-06-01
```

#### Custom Raw Queries
Execute raw SQL queries against your assets:
```bash
subx db -C "SELECT subdomain, alive, status_code FROM subdomain WHERE target='example.com' AND alive=1"
```

#### Clean Up (Delete Target Records)
```bash
subx db -d example.com --delete
```

#### Export Subdomains to Files
Save the query results to a file:
```bash
subx db -d example.com -oN subs.txt
```

Save with custom separators:
```bash
subx db -d example.com -oX ';:delimited_subs.txt'
```

### 4. Database Migrations (`dev-migrate`)
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
