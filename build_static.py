"""
Vercel-only build step.

Vercel's Flask integration serves static assets from a top-level public/**
directory via its CDN, instead of through Flask's own static_folder
(https://vercel.com/docs/frameworks/backend/flask#serving-static-assets).
EventOps' templates all reference static files the normal Flask way
( url_for('static', filename=...) -> /static/... ), so this script mirrors
static/ into public/static/ at deploy time, keeping that same /static/...
URL path working — Vercel's CDN intercepts it before it reaches the Flask
function, and Flask's own static handling is simply unused there.

This only runs on Vercel (see pyproject.toml's [tool.vercel.scripts]).
Local development and Render both serve static/ directly through Flask and
never touch this script.
"""

import shutil
from pathlib import Path


def main():
    root = Path(__file__).parent
    src = root / "static"
    dst = root / "public" / "static"

    if not src.exists():
        print("No static/ directory found — nothing to copy.")
        return

    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    print(f"Copied {src} -> {dst} for Vercel's static asset CDN.")


if __name__ == "__main__":
    main()
