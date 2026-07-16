#!/usr/bin/env python3
"""Release automation for bci-runtime dual publishing.

Usage:
    python tools/release.py v1.2.3          # dry-run (no push)
    python tools/release.py v1.2.3 --push   # push UPM branch + build wheel

Environment:
    PYPI_TOKEN   — (optional) API token for PyPI upload
    GITHUB_TOKEN — (optional) token for git push to upm branch
"""

import sys, os, json, shutil, subprocess, tempfile, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_JSON = ROOT / "Packages" / "com.bci-runtime.shm" / "package.json"
UPM_BRANCH = "upm"


def parse_tag(tag: str) -> str:
    m = re.match(r"^v?(\d+\.\d+\.\d+.*)$", tag.strip())
    if not m:
        raise SystemExit(f"Invalid tag: {tag!r}. Expected vMAJOR.MINOR.PATCH")
    return m.group(1)


def inject_version(version: str):
    with open(PKG_JSON, "r") as f:
        data = json.load(f)
    old = data.get("version", "(none)")
    data["version"] = version
    with open(PKG_JSON, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"[release] package.json: {old} → {version}")


def build_wheel():
    subprocess.check_call(
        [sys.executable, "-m", "build", "--wheel", str(ROOT)],
        stdout=sys.stdout, stderr=sys.stderr,
    )
    wheels = list((ROOT / "dist").glob("*.whl"))
    print(f"[release] Wheel: {wheels[0].name if wheels else 'NOT FOUND'}")


def push_upm_branch():
    """Extract Packages/com.bci-runtime.shm/ into a clean 'upm' branch."""
    pkg_dir = ROOT / "Packages" / "com.bci-runtime.shm"
    with tempfile.TemporaryDirectory() as tmp:
        # Copy package contents to temp dir
        dst = Path(tmp) / "pkg"
        shutil.copytree(pkg_dir, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.meta"))

        # Create/overwrite upm branch
        subprocess.check_call(
            ["git", "checkout", "--orphan", UPM_BRANCH],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # Remove everything, copy package contents
        for item in ROOT.iterdir():
            if item.name != ".git":
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)

        shutil.copytree(dst, ROOT, dirs_exist_ok=True)

        subprocess.check_call(["git", "add", "-A"], cwd=ROOT)
        subprocess.check_call(
            ["git", "commit", "-m", f"release {version} [UPM]"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # Push
        token = os.environ.get("GITHUB_TOKEN", "")
        remote = os.environ.get("GIT_REMOTE", "origin")
        if token:
            push_url = f"https://x-access-token:{token}@github.com/{os.environ['GITHUB_REPOSITORY']}.git"
            subprocess.check_call(
                ["git", "remote", "set-url", "origin", push_url],
                cwd=ROOT, stdout=subprocess.DEVNULL,
            )

        subprocess.check_call(
            ["git", "push", "--force", remote, UPM_BRANCH],
            cwd=ROOT, stdout=sys.stdout, stderr=sys.stderr,
        )
        print(f"[release] Pushed {UPM_BRANCH} branch")


if __name__ == "__main__":
    args = sys.argv[1:]
    tag = args[0] if args else os.environ.get("GITHUB_REF_NAME", "")
    do_push = "--push" in args

    version = parse_tag(tag)
    print(f"[release] Tag: {tag} → version: {version}")

    inject_version(version)

    build_wheel()

    pypi_token = os.environ.get("PYPI_TOKEN", "")
    if pypi_token:
        subprocess.check_call([
            sys.executable, "-m", "twine", "upload",
            "--username", "__token__",
            "--password", pypi_token,
            *[str(p) for p in (ROOT / "dist").glob("*.whl")],
        ], stdout=sys.stdout, stderr=sys.stderr)
        print("[release] Uploaded to PyPI")

    if do_push and os.environ.get("GITHUB_TOKEN"):
        push_upm_branch()
    elif do_push:
        print("[release] --push requires GITHUB_TOKEN; skipping branch push")

    print("[release] Done")
