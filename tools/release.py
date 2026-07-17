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


def log(msg):
    print(f"[release] {msg}", flush=True)


def die(msg, code=1):
    log(f"FATAL: {msg}")
    sys.exit(code)


def parse_tag(tag: str) -> str:
    m = re.match(r"^v?(\d+\.\d+\.\d+.*)$", tag.strip())
    if not m:
        die(f"Invalid tag: {tag!r}. Expected vMAJOR.MINOR.PATCH")
    return m.group(1)


def inject_version(version: str):
    with open(PKG_JSON, "r") as f:
        data = json.load(f)
    old = data.get("version", "(none)")
    data["version"] = version
    with open(PKG_JSON, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    log(f"package.json: {old} -> {version}")


def build_wheel():
    log("Building wheel ...")
    subprocess.check_call(
        [sys.executable, "-m", "build", "--wheel", str(ROOT)],
        stdout=sys.stdout, stderr=sys.stderr,
    )
    wheels = list((ROOT / "dist").glob("*.whl"))
    if not wheels:
        die("Wheel not found after build")
    log(f"Wheel: {wheels[0].name}")


def push_upm_branch():
    log("Pushing UPM branch ...")
    pkg_dir = ROOT / "Packages" / "com.bci-runtime.shm"
    if not pkg_dir.is_dir():
        die(f"Package dir not found: {pkg_dir}")

    # Ensure git user is configured (CI runners may not have it)
    for key, val in (("user.name", "github-actions[bot]"),
                     ("user.email", "github-actions[bot]@users.noreply.github.com")):
        try:
            subprocess.run(["git", "config", key, val],
                           cwd=ROOT, capture_output=True, check=False)
        except Exception:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "pkg"
        shutil.copytree(pkg_dir, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.meta"))

        # Create or reset UPM orphan branch
        try:
            subprocess.check_call(
                ["git", "checkout", "--orphan", UPM_BRANCH],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            die(f"git checkout --orphan failed (exit {e.returncode})")

        # Remove everything except .git and dist/ (wheel artifacts)
        KEEP = {".git", "dist"}
        for item in ROOT.iterdir():
            if item.name not in KEEP:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)

        shutil.copytree(dst, ROOT, dirs_exist_ok=True)

        # Stage package files, explicitly exclude dist/ (wheel artifacts)
        subprocess.check_call(["git", "add", "-A"], cwd=ROOT)
        # Remove any staged dist/ files from the UPM commit
        dist_dir = ROOT / "dist"
        if dist_dir.is_dir():
            subprocess.check_call(
                ["git", "rm", "-r", "--cached", "--ignore-unmatch", "dist/"],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        try:
            subprocess.check_call(
                ["git", "commit", "-m", f"release {version} [UPM]"],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            die(f"git commit failed (exit {e.returncode}): staging issue?")

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
        log(f"Pushed {UPM_BRANCH} branch")


if __name__ == "__main__":
    args = sys.argv[1:]
    tag = args[0] if args else os.environ.get("GITHUB_REF_NAME", "")
    do_push = "--push" in args

    if not tag:
        die("No tag provided and GITHUB_REF_NAME not set")

    version = parse_tag(tag)
    log(f"Tag: {tag} -> version: {version}")

    # Step 1: inject version
    inject_version(version)

    # Step 2: build wheel
    try:
        build_wheel()
    except Exception as e:
        die(f"Wheel build failed: {e}")

    # Step 3: upload to PyPI
    pypi_token = os.environ.get("PYPI_TOKEN", "")
    if pypi_token:
        log("Uploading to PyPI ...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "twine", "upload",
                "--username", "__token__",
                "--password", pypi_token,
                *[str(p) for p in (ROOT / "dist").glob("*.whl")],
            ], stdout=sys.stdout, stderr=sys.stderr)
            log("Uploaded to PyPI")
        except Exception as e:
            log(f"PyPI upload failed (non-fatal): {e}")
    else:
        log("PYPI_TOKEN not set; skipping PyPI upload")

    # Step 4: push UPM branch
    if do_push:
        github_token = os.environ.get("GITHUB_TOKEN", "")
        if github_token:
            try:
                push_upm_branch()
            except Exception as e:
                die(f"UPM branch push failed: {e}")
        else:
            log("--push requires GITHUB_TOKEN; skipping branch push")
    else:
        log("Dry-run; skipping branch push (pass --push to push)")

    log("Done")
