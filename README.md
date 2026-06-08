# SUBX 🚀

`SUBX` is a fast, modular, and extensible asset discovery framework designed for security researchers, bug bounty hunters, and penetration testers.
It helps identify and map an organization's external attack surface through subdomain enumeration, asset discovery, and intelligence gathering from multiple passive and active sources.
Built with an asynchronous plugin-based architecture, SubX allows new reconnaissance sources to be integrated with minimal effort while maintaining high performance and scalability.

---
## Features

- 🚀 Asynchronous enumeration engine
- 🔌 Plugin-based architecture
- ⚙️ Configuration-driven workflows
- 🎯 Scope and out-of-scope management
- 🌐 Multiple passive enumeration sources
- 🗄️ Database-backed asset storage
- 🧹 Automatic cleaning

---
## Data sources
| Source | API Key Required |
|----------|----------|
| Shodan | Yes |
| AlienVault OTX | Yes |
| urlscan.io | Yes |
| VirusTotal | Yes |
| ProjectDiscovery Chaos | Yes |
| HackerTarget | No |
| AnubisDB | No |
| BeVigil | Yes |
| ViewDNS.info | Yes |
| BGP.Tools | No |
---

## Installation & Setup 🛠️

### 1. Clone the repository
```bash
git clone https://github.com/RiadhBenlamine/SubX.git
cd SubX
python setup.py install
```

### 2. Configure Environment Variables
Create a `config.yaml` file and fill all data needed
*Note: Any plugin without configured keys will be automatically and silently skipped during enumeration.*

### 3. Run directly with `uv`
No manual virtual environment setup required if you use `uv`:
```bash
uv run python main.py --help
```

## Usage Guide 📖

### 1. Subdomain Enumeration
Enumerate subdomains for a target domain and save results directly to the database:
```bash
uv run python main.py enum -c ./config.yaml
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
## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
