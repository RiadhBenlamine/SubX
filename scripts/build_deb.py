"""Cross-platform Debian (.deb) package generator script for SubX."""
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build_deb"
VERSION = "2.0.8"
PACKAGE_NAME = "subx"
DEB_FILENAME = f"{PACKAGE_NAME}_{VERSION}-1_all.deb"


def create_subx_launcher() -> str:
    """Generate executable standalone /usr/bin/subx python wrapper script."""
    return """#!/usr/bin/env python3
import sys

# Ensure installed package path is available
sys.path.insert(0, "/usr/lib/python3/dist-packages")

from core.cmd import app

if __name__ == "__main__":
    app()
"""


def compute_md5(file_path: Path) -> str:
    hash_md5 = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def build_deb_package():
    print(f"📦 Building Debian package for {PACKAGE_NAME} v{VERSION}...")

    # Clean build directories
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Directory Structure
    debian_dir = BUILD_DIR / "DEBIAN"
    usr_bin_dir = BUILD_DIR / "usr" / "bin"
    python_pkg_dir = BUILD_DIR / "usr" / "lib" / "python3" / "dist-packages"
    doc_dir = BUILD_DIR / "usr" / "share" / "doc" / "subx"
    man_dir = BUILD_DIR / "usr" / "share" / "man" / "man1"

    for d in (debian_dir, usr_bin_dir, python_pkg_dir, doc_dir, man_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 2. Copy Control Files
    shutil.copy2(ROOT_DIR / "debian" / "control", debian_dir / "control")

    # 3. Create Executable Launcher /usr/bin/subx
    launcher_file = usr_bin_dir / "subx"
    launcher_file.write_text(create_subx_launcher(), encoding="utf-8")
    launcher_file.chmod(0o755)

    # 4. Copy Python Source Code
    for item in ("main.py", "core", "plugins", "tools", "config_samples"):
        src = ROOT_DIR / item
        dst = python_pkg_dir / item
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.is_file():
            shutil.copy2(src, dst)

    # 5. Copy Documentation & License
    shutil.copy2(ROOT_DIR / "README.md", doc_dir / "README.md")
    shutil.copy2(ROOT_DIR / "debian" / "copyright", doc_dir / "copyright")

    # Compress changelog
    changelog_src = ROOT_DIR / "debian" / "changelog"
    changelog_gz = doc_dir / "changelog.Debian.gz"
    with changelog_src.open("rb") as f_in, gzip.open(changelog_gz, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    # Compress man page
    man_src = ROOT_DIR / "debian" / "subx.1"
    man_gz = man_dir / "subx.1.gz"
    with man_src.open("rb") as f_in, gzip.open(man_gz, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    # 6. Generate DEBIAN/md5sums
    md5_lines = []
    usr_root = BUILD_DIR / "usr"
    for path in usr_root.rglob("*"):
        if path.is_file():
            rel_path = path.relative_to(BUILD_DIR)
            md5_lines.append(f"{compute_md5(path)}  {rel_path.as_posix()}\n")
    (debian_dir / "md5sums").write_text("".join(md5_lines), encoding="utf-8")

    # 7. Package build using dpkg-deb or fallback python ar packager
    target_deb = DIST_DIR / DEB_FILENAME

    if shutil.which("dpkg-deb"):
        print("Executing dpkg-deb tool...")
        subprocess.run(
            ["dpkg-deb", "--build", "--root-owner-group", str(BUILD_DIR), str(target_deb)],
            check=True,
        )
    else:
        print("dpkg-deb not found on platform — constructing standard .deb archive via Python...")
        build_deb_python(BUILD_DIR, target_deb)

    print(f"✨ Successfully generated Debian package: {target_deb}")
    return target_deb


def build_deb_python(build_dir: Path, output_deb: Path):
    """Pure-Python fallback implementation of standard Debian .deb ar archive creation."""
    control_tar = build_dir / "control.tar.gz"
    data_tar = build_dir / "data.tar.gz"
    deb_binary = build_dir / "debian-binary"

    deb_binary.write_bytes(b"2.0\n")

    # 1. Create control.tar.gz
    with tarfile.open(control_tar, "w:gz") as tar:
        for p in (build_dir / "DEBIAN").iterdir():
            tar.add(p, arcname=f"./{p.name}")

    # 2. Create data.tar.gz
    with tarfile.open(data_tar, "w:gz") as tar:
        for p in (build_dir / "usr").rglob("*"):
            rel = p.relative_to(build_dir)
            tar.add(p, arcname=f"./{rel.as_posix()}")

    # 3. Create debian ar archive format
    def ar_header(name: str, size: int) -> bytes:
        # Standard ar header format: filename (16), mtime (12), owner (6), group (6), mode (8), size (10), magic (2)
        return (
            f"{name:<16}0           0     0     100644  {size:<10}`\n"
        ).encode("ascii")

    with output_deb.open("wb") as f:
        f.write(b"!<arch>\n")

        # debian-binary
        bin_data = deb_binary.read_bytes()
        f.write(ar_header("debian-binary", len(bin_data)))
        f.write(bin_data)
        if len(bin_data) % 2 != 0:
            f.write(b"\n")

        # control.tar.gz
        c_data = control_tar.read_bytes()
        f.write(ar_header("control.tar.gz", len(c_data)))
        f.write(c_data)
        if len(c_data) % 2 != 0:
            f.write(b"\n")

        # data.tar.gz
        d_data = data_tar.read_bytes()
        f.write(ar_header("data.tar.gz", len(d_data)))
        f.write(d_data)
        if len(d_data) % 2 != 0:
            f.write(b"\n")

    # Cleanup temporary tar files
    control_tar.unlink()
    data_tar.unlink()
    deb_binary.unlink()


if __name__ == "__main__":
    build_deb_package()
