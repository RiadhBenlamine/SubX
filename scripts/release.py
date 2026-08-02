"""Release management script for SubX.

Automates version bumping, building wheels/sdist/debian packages,
uploading to PyPI, git tagging, and pushing to GitHub.

Usage:
  python scripts/release.py patch       # e.g., 2.0.2 -> 2.0.3
  python scripts/release.py minor       # e.g., 2.0.2 -> 2.1.0
  python scripts/release.py major       # e.g., 2.0.2 -> 3.0.0
  python scripts/release.py 2.0.5       # Set specific version
"""
import getpass
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_FILE = ROOT_DIR / "pyproject.toml"
BUILD_DEB_FILE = ROOT_DIR / "scripts" / "build_deb.py"
DIST_DIR = ROOT_DIR / "dist"


def run_cmd(cmd: list[str] | str, check: bool = True, shell: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a shell or subprocess command cleanly."""
    if isinstance(cmd, list):
        print(f"➜ Running: {' '.join(cmd)}")
    else:
        print(f"➜ Running: {cmd}")
    
    res = subprocess.run(
        cmd,
        check=check,
        shell=shell,
        cwd=str(ROOT_DIR),
        capture_output=capture,
        text=True,
    )
    return res


def get_current_version() -> str:
    content = PYPROJECT_FILE.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def bump_version(current: str, bump_type: str) -> str:
    parts = [int(p) for p in current.split(".")]
    if len(parts) != 3:
        raise ValueError(f"Version '{current}' is not standard semver X.Y.Z")

    major, minor, patch = parts
    if bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "major":
        return f"{major + 1}.0.0"
    elif re.match(r"^\d+\.\d+\.\d+$", bump_type):
        return bump_type
    else:
        raise ValueError(f"Invalid bump type or version: '{bump_type}'")


def update_version_in_files(new_version: str):
    print(f"✏️  Updating version in files to v{new_version}...")
    
    # 1. Update pyproject.toml
    pyproject_content = PYPROJECT_FILE.read_text(encoding="utf-8")
    updated_pyproject = re.sub(
        r'version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
        pyproject_content,
        count=1,
    )
    PYPROJECT_FILE.write_text(updated_pyproject, encoding="utf-8")

    # 2. Update scripts/build_deb.py
    if BUILD_DEB_FILE.exists():
        build_deb_content = BUILD_DEB_FILE.read_text(encoding="utf-8")
        updated_build_deb = re.sub(
            r'VERSION\s*=\s*"[^"]+"',
            f'VERSION = "{new_version}"',
            build_deb_content,
            count=1,
        )
        BUILD_DEB_FILE.write_text(updated_build_deb, encoding="utf-8")


def ensure_clean_git_status():
    res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(ROOT_DIR))
    if res.stdout.strip():
        print("⚠️  Warning: Uncommitted changes found in working directory:")
        print(res.stdout)
        ans = input("Do you want to stage and include them in the release commit? [Y/n]: ").strip().lower()
        if ans and not ans.startswith("y"):
            print("Aborting release due to uncommitted changes.")
            sys.exit(1)


def run_tests():
    print("🧪 Running test suite prior to release...")
    try:
        run_cmd([sys.executable, "-m", "pytest", "tests/"])
    except Exception as e:
        print(f"⚠️  Pytest run skipped/failed ({e})")
        ans = input("Do you want to continue release without running pytest? [Y/n]: ").strip().lower()
        if ans and not ans.startswith("y"):
            sys.exit(1)


def build_packages(new_version: str):
    print("🧹 Cleaning old build distributions...")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    print("📦 Building wheel and source distribution...")
    if shutil.which("uv"):
        run_cmd(["uv", "build"])
    else:
        run_cmd([sys.executable, "-m", "build"])

    print("📦 Building Debian (.deb) package...")
    run_cmd([sys.executable, str(BUILD_DEB_FILE)])

    print("🔍 Checking package distributions with twine...")
    run_cmd([sys.executable, "-m", "twine", "check", f"dist/subx_recon-{new_version}*"])


def load_env_credentials() -> dict[str, str]:
    """Load credentials from local .env or global ~/.config/subx/.env if present."""
    from dotenv import dotenv_values
    creds = {}
    candidates = [
        ROOT_DIR / ".env",
        Path.home() / ".config" / "subx" / ".env",
    ]
    for c in candidates:
        if c.exists():
            for key, val in dotenv_values(c).items():
                if val:
                    creds[key] = val
    return creds


def upload_to_pypi(new_version: str):
    print("🚀 Uploading package to PyPI...")
    
    env = os.environ.copy()
    creds = load_env_credentials()
    for k, v in creds.items():
        env[k] = v

    if not env.get("TWINE_PASSWORD"):
        pypi_token = env.get("PYPI_TOKEN")
        if pypi_token:
            env["TWINE_USERNAME"] = "__token__"
            env["TWINE_PASSWORD"] = pypi_token
        else:
            pypi_token = input("Enter PyPI API Token (pypi-...): ").strip()
            if not pypi_token:
                print("Aborting upload: No PyPI token provided.")
                sys.exit(1)
            env["TWINE_USERNAME"] = "__token__"
            env["TWINE_PASSWORD"] = pypi_token
    elif not env.get("TWINE_USERNAME"):
        env["TWINE_USERNAME"] = "__token__"

    cmd = [
        sys.executable,
        "-m",
        "twine",
        "upload",
        "--verbose",
        f"dist/subx_recon-{new_version}-py3-none-any.whl",
        f"dist/subx_recon-{new_version}.tar.gz",
    ]
    
    subprocess.run(cmd, check=True, env=env, cwd=str(ROOT_DIR))


def git_tag_and_push(new_version: str):
    tag = f"v{new_version}"
    print(f"🏷️  Creating Git commit and tag '{tag}'...")

    run_cmd(["git", "add", "pyproject.toml", "scripts/build_deb.py", "scripts/release.py", "README.md", "debian/", ".gitignore"], check=False)

    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, cwd=str(ROOT_DIR)).stdout
    if ".env" in staged or ".pypirc" in staged:
        print("⚠️  CRITICAL SECURITY PREVENTATIVE ACTION: Secret file detected in git index! Removing from staging...")
        subprocess.run(["git", "rm", "--cached", "-f", ".env", ".pypirc"], capture_output=True, cwd=str(ROOT_DIR))

    run_cmd(["git", "commit", "-m", f"bump: version {new_version}"], check=False)
    run_cmd(["git", "tag", "-f", tag], check=False)

    print(f"⬆️  Pushing main branch and tag '{tag}' to GitHub...")
    run_cmd(["git", "push", "origin", "main"], check=False)
    run_cmd(["git", "push", "origin", tag, "--force"], check=False)


def main():
    current_version = get_current_version()
    print(f"SubX Release Automation tool")
    print(f"Current version: v{current_version}")

    bump_arg = sys.argv[1] if len(sys.argv) > 1 else "patch"
    new_version = bump_version(current_version, bump_arg)

    print(f"Target release version: v{new_version}")
    ans = input(f"Proceed with releasing v{new_version}? [Y/n]: ").strip().lower()
    if ans and not ans.startswith("y"):
        print("Release cancelled.")
        sys.exit(0)

    ensure_clean_git_status()
    run_tests()
    update_version_in_files(new_version)
    build_packages(new_version)
    upload_to_pypi(new_version)
    git_tag_and_push(new_version)

    print(f"\n🎉 Successfully released SubX v{new_version}!")
    print(f"• PyPI: https://pypi.org/project/subx-recon/{new_version}/")
    print(f"• GitHub Tag: https://github.com/RiadhBenlamine/SubX/releases/tag/v{new_version}")


if __name__ == "__main__":
    main()
