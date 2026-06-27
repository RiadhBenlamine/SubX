from setuptools import find_packages, setup

setup(
    name="subx",
    version="0.1.0",
    description="SUBX — Subdomain Recon Framework",
    py_modules=["main"],
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "aiohttp>=3.11.0",
        "dnspython>=2.8.0",
        "feedparser>=6.0.12",
        "python-dotenv>=1.2.2",
        "requests>=2.34.2",
        "shodan>=1.31.0",
        "vt-py>=0.22.0",
        "censys-platform>=0.14.0",
        "pyyaml>=6.0.3",
        "aiosqlite>=0.22.1",
        "sqlmodel>=0.0.38",
        "sqlalchemy>=2.0.50",
        "typer>=0.26.7",
        "rich>=15.0.0",
        
    ],
    entry_points={
        "console_scripts": [
            "subx=main:app",
        ],
    },
    python_requires=">=3.10",
)
