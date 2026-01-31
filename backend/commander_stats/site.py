from __future__ import annotations

import shutil
from pathlib import Path


def copy_static_site(frontend_site_dir: str, docs_dir: str) -> None:
    """Copy the frontend/site folder into docs_dir (static site root).

    This function replaces the destination directory to avoid partial/stale copies.
    """
    src = Path(frontend_site_dir).resolve()
    dst = Path(docs_dir).resolve()

    if not src.exists():
        raise FileNotFoundError(f"Frontend site directory not found: {src}")

    # Replace destination atomically-ish: remove then copy.
    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst, dirs_exist_ok=True)
