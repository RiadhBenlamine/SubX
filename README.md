# SUBX 🚀

`SUBX` is a modern, concurrent subdomain enumeration and asset tracking framework designed for speed, resilience, and clean usability. Powered by Python 3.14+, `uv`, `sqlmodel`, and the `rich` UI library, `SUBX` aggregates results from multiple threat intelligence and search API plugins, filters DNS wildcards, and tracks subdomain status over time in a local database.

---

## Key Features ✨

- **Fast & Concurrent Enumeration:** Queries multiple API endpoints simultaneously utilizing `asyncio` and `aiohttp`.
- **Database Asset Tracking:** Stores subdomains with `first_seen` and `last_seen` timestamps using **SQLModel** and an async SQLite backend (`aiosqlite`).
- **Resilient Plugin Architecture:** Gracefully handles rate limits, API quota exhaustion, and missing configuration keys (skips plugins without credentials).
- **Wildcard Detection:** Automatically detects wildcard DNS records and cleans/re-scans them to prevent bloat.
- **Modern CLI Dashboard:** Built with `typer` and `rich` to provide high-fidelity console tables, banners, progress indicators, and overall summary panels.
- **Database Summaries:** Instantly view tracked targets and subdomain counts with a dashboard view.

---

## Plugin Support 🔌

- **VirusTotal:** Retrieves subdomains from VirusTotal's database (supports rate limit retries and quota-exhaustion fallback).
- **Shodan:** Query DNS subdomains via Shodan API (efficient query credit management and early termination on quota exhaustion).
- **Censys:** Extract certificate-registered subdomains using the Censys Search API.
- **Urlscan:** Queries public scan search results for the target domain (supports cursor pagination and rate limit resilience).

---

## Installation & Setup 🛠️

`SUBX` uses [uv](https://github.com/astral-sh/uv) for fast, modern dependency management.

### 1. Clone the repository
```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory and add your API keys:
```env
SHODAN_API=your_shodan_api_key
VIRUSTOTAL_API=your_virustotal_api_key
CENSYS_API=your_censys_api_key
```
*Note: Any plugin without configured keys will be automatically and silently skipped during enumeration.*

### 3. Run directly with `uv`
No manual virtual environment setup required if you use `uv`:
```bash
uv run python main.py --help
```

### 4. Installation on Kali Linux (System-wide CLI)
For easy installation on Kali Linux so that the `subx` command is accessible from anywhere in your shell, you can install it via the `setup.py` configuration:

- **Using `pipx` (Strongly Recommended):**
  ```bash
  sudo apt update && sudo apt install -y pipx
  pipx ensurepath
  pipx install .
  ```
  *(Note: You may need to restart your terminal or run `source ~/.zshrc` / `source ~/.bashrc` for the PATH changes to take effect).*

- **Using standard `pip`:**
  ```bash
  pip install . --break-system-packages
  ```
This will automatically download all dependencies and register `subx` as a global executable command.

---

## Usage Guide 📖

### 1. Subdomain Enumeration
Enumerate subdomains for a target domain and save results directly to the database:
```bash
uv run python main.py enum -d example.com
```

You can also specify a custom scope (comma-separated list of domains) or run without saving to the DB:
```bash
uv run python main.py enum -d example.com --scope example.com,www.example.com --no-save
```

### 2. Database Summary (Dashboard)
To view a list of all tracked target domains, their subdomain counts, and when they were last updated:
```bash
uv run python main.py db
```

### 3. Query Stored Subdomains
Retrieve all stored subdomains for a specific target domain:
```bash
uv run python main.py db -d example.com
```

#### Filter Queries
Filter results by a specific plugin:
```bash
uv run python main.py db -d example.com --filter-plugin VirustotalPlugin
```

Filter subdomains that were first seen after a specific date (YYYY-MM-DD):
```bash
uv run python main.py db -d example.com --new-since 2026-06-01
```

---

## Project Structure 📁

```text
SubX/
├── core/
│   ├── db_models.py      # SQLModel database schema
│   ├── logger.py         # Custom CLI logger setup
│   ├── models.py         # Core data representations
│   ├── plugin.py         # Plugin base class definition
│   ├── plugin_manager.py # Plugin loader & async executor
│   ├── processor.py      # Wildcard filtering & domain matching logic
│   └── storage_manager.py# Async database engine & CRUD manager
├── plugins/
│   ├── censys_enum.py    # Censys API enum integration
│   ├── shodan_enum.py    # Shodan API enum integration
│   └── virustotal_enum.py# VirusTotal API enum integration
├── main.py               # Typer CLI application entry point
├── pyproject.toml        # Project dependencies
└── README.md             # This file
```

---

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
