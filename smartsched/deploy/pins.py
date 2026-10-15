#!/usr/bin/env python3
"""Base image pins: every third-party image the stack runs or builds FROM is ``name:version@sha256:<digest>``.

Where the pins live (one reference may appear in several places; they must agree):
  * docker-compose.yml / docker-compose.caddy.yml ``image:`` of third-party services
  * docker-compose.yml ``build.args`` ``*_IMAGE`` for the three Dockerfiles (backend PYTHON_IMAGE, frontend
    NODE_IMAGE, legacy PHP_IMAGE). The Dockerfile ``ARG *_IMAGE=`` defaults stay tag-only and must name the
    same tag (plain ``docker build`` keeps working; compose and the pod CI images gate pass the digest).
  * pod CI: podci/config.py ``python_image`` and gates/python-ci.Dockerfile = the backend's PYTHON_IMAGE

    python3 pins.py check                  # validate.sh: exit 1 on an unpinned or drifting reference
    python3 pins.py build-args SERVICE     # images gate: the compose build args, one per line (--build-arg K=V)
    python3 pins.py refresh                # pin-digests.sh: re-resolve each tag's current multi-arch digest

PyYAML only (validate.sh already needs it). Index digests are multi-arch (amd64 + the arm64 pod).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

DIGEST = re.compile(r"^(?P<tag>[\w./-]+:[\w.-]+)@(?P<digest>sha256:[0-9a-f]{64})$")
DEPLOY = Path("smartsched/deploy")
COMPOSE = DEPLOY / "docker-compose.yml"
CADDY = DEPLOY / "docker-compose.caddy.yml"
DOCKERFILES = {  # compose service -> Dockerfile
    "backend": Path("smartsched/backend/Dockerfile"),
    "frontend": Path("smartsched/frontend/Dockerfile"),
    "crbs": DEPLOY / "legacy/Dockerfile",
}
POD_CONFIG = DEPLOY / "pod-ci/podci/config.py"
POD_DOCKERFILE = DEPLOY / "pod-ci/gates/python-ci.Dockerfile"
POD_CONFIG_RX = re.compile(r'python_image: str = "([^"]+)"')
ARG_RX = re.compile(r"^ARG\s+(\w+_IMAGE)=(\S+)", re.M)


def _yaml(path: Path) -> dict[str, Any]:
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_multi_constructor("!", lambda loader, suffix, node: None)  # compose !reset / !override
    return yaml.load(path.read_text(encoding="utf-8"), Loader=Loader) or {}  # noqa: S506 - SafeLoader subclass


def _resolve_default(value: str) -> str:
    """``${X:-default}`` -> default (the images gate builds without an .env)."""
    return re.sub(r"\$\{\w+:?-([^}]*)\}", r"\1", str(value))


def _services(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in (COMPOSE, CADDY):
        if (root / f).exists():  # override files merge per service (compose semantics)
            for name, svc in (_yaml(root / f).get("services") or {}).items():
                out.setdefault(name, {}).update(svc or {})
    return out


def tag_of(ref: str) -> str:
    m = DIGEST.match(ref)
    return m.group("tag") if m else ref


def check(root: Path) -> list[str]:
    errors: list[str] = []
    services = _services(root)
    compose_args: dict[str, str] = {}
    for name, svc in services.items():
        svc = svc or {}
        build = svc.get("build")
        image = str(svc.get("image") or "")
        if isinstance(build, dict):
            for k, v in (build.get("args") or {}).items():
                if k.endswith("_IMAGE"):
                    compose_args[f"{name}.{k}"] = str(v)
                    if not DIGEST.match(str(v)):
                        errors.append(f"{name}: build arg {k}={v} has no @sha256 digest")
        elif image and not DIGEST.match(image):
            errors.append(f"{name}: image {image} has no @sha256 digest")
    for service, df in DOCKERFILES.items():
        if not (root / df).exists():
            continue
        for arg, default in ARG_RX.findall((root / df).read_text(encoding="utf-8")):
            ref = compose_args.get(f"{service}.{arg}")
            if ref is None:
                errors.append(f"{service}: compose passes no build arg {arg} (Dockerfile default {default})")
            elif tag_of(ref) != tag_of(default):
                errors.append(f"{service} {arg}: compose {tag_of(ref)}, Dockerfile default {default} (bump both)")
    backend_py = compose_args.get("backend.PYTHON_IMAGE")
    if backend_py:
        for path, rx in ((POD_CONFIG, POD_CONFIG_RX), (POD_DOCKERFILE, re.compile(r"^ARG PYTHON_IMAGE=(\S+)", re.M))):
            if not (root / path).exists():
                continue
            m = rx.search((root / path).read_text(encoding="utf-8"))
            if not m or m.group(1) != backend_py:
                errors.append(f"pod CI python image in {path} ({m.group(1) if m else 'missing'}) != backend "
                              f"PYTHON_IMAGE {backend_py}")
    return errors


def build_args(root: Path, service: str) -> list[str]:
    build = (_services(root).get(service) or {}).get("build") or {}
    out: list[str] = []
    for k, v in (build.get("args") or {}).items() if isinstance(build, dict) else ():
        out += ["--build-arg", f"{k}={_resolve_default(v)}"]
    return out


def references(root: Path) -> set[str]:
    refs: set[str] = set()
    for svc in _services(root).values():
        svc = svc or {}
        build = svc.get("build")
        if isinstance(build, dict):
            refs |= {str(v) for k, v in (build.get("args") or {}).items() if k.endswith("_IMAGE")}
        elif svc.get("image") and "${" not in str(svc["image"]):
            refs.add(str(svc["image"]))
    return refs


def docker_resolver(tag: str) -> str:
    out = subprocess.run(["docker", "buildx", "imagetools", "inspect", tag, "--format", "{{json .Manifest}}"],
                         check=True, capture_output=True, text=True, timeout=120).stdout
    return str(json.loads(out)["digest"])


def refresh(root: Path, resolve: Callable[[str], str] = docker_resolver) -> dict[str, str]:
    """Re-resolve the digest of every pinned tag; rewrite compose + the pod CI files. Returns old -> new."""
    changed: dict[str, str] = {}
    for ref in sorted(references(root)):
        tag = tag_of(ref)
        new = f"{tag}@{resolve(tag)}"
        if new != ref:
            changed[ref] = new
    files = [COMPOSE, CADDY, POD_CONFIG, POD_DOCKERFILE]
    for f in files:
        p = root / f
        if not p.exists():
            continue
        text = original = p.read_text(encoding="utf-8")
        for old, new in changed.items():  # a tag-only ref must not match inside an already pinned one
            text = re.sub(re.escape(old) + r"(?![@\w.-])", new, text)
        if text != original:
            p.write_text(text, encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[2]
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        errors = check(root)
        for ref in sorted(references(root)):
            print(f"  {'ok  ' if DIGEST.match(ref) else 'FAIL'} {ref}")
        for e in errors:
            print(f"  FAIL {e}")
        return 1 if errors else 0
    if cmd == "build-args":
        print("\n".join(build_args(root, argv[1])))
        return 0
    if cmd == "refresh":
        changed = refresh(root)
        for old, new in changed.items():
            print(f"{old}\n  -> {new}")
        print(f"{len(changed)} pin(s) updated" if changed else "all pins current")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
