"""HB-16 local-model host: the optional compose profile ``ollama`` and the runbook ``docs/deploy/local-models.md``.

* the ``ollama`` service runs only with ``--profile ollama`` (never by default, so never on the 8 GB pod by
  default), is pinned by digest (``deploy/pins.py check`` stays clean), publishes no port, keeps a context of at
  least 16 384 tokens and has a memory cap; nothing in the default stack depends on it;
* ``docker compose --profile ollama config`` validates when the compose CLI is installed (no daemon needed);
* the runbook carries the GPU table, the vLLM and Ollama commands, ``--tool-call-parser``, the firewall rule,
  ``allow_local``, the KVKK note, and the steps that register the server (HB-12 sync, HB-13 local provider).
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "smartsched" / "deploy"
RUNBOOK = ROOT / "docs" / "deploy" / "local-models.md"


def _compose() -> dict:  # type: ignore[type-arg]
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_multi_constructor("!", lambda loader, suffix, node: None)
    return yaml.load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"), Loader=Loader)  # noqa: S506


def _pins():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("deploy_pins", DEPLOY / "pins.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hb_16_ollama_profile_is_optional_pinned_and_internal() -> None:
    services = _compose()["services"]
    o = services["ollama"]
    assert o["profiles"] == ["ollama"]
    assert o["image"].startswith("ollama/ollama:0.") and "@sha256:" in o["image"]
    assert "ports" not in o and o.get("expose") == ["11434"]
    env = o["environment"]
    ctx = str(env["OLLAMA_CONTEXT_LENGTH"])
    assert int(ctx.rsplit("-", 1)[-1].rstrip("}")) >= 16384
    assert str(env["OLLAMA_HOST"]).endswith(":11434")
    assert o["deploy"]["resources"]["limits"]["memory"]
    assert any(str(v).startswith("ollama-models:") for v in o["volumes"])
    assert "ollama-models" in _compose()["volumes"]
    for name, svc in services.items():
        if name == "ollama":
            continue
        deps = svc.get("depends_on") or {}
        assert "ollama" not in deps, name
    env_example = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    assert "OLLAMA_MEMORY=" in env_example and "OLLAMA_CONTEXT_LENGTH=" in env_example


def test_hb_16_pins_cover_the_ollama_image() -> None:
    pins = _pins()
    assert pins.check(ROOT) == []
    assert any(r.startswith("ollama/ollama:") for r in pins.references(ROOT))


def test_hb_16_compose_config_validates_with_the_profile(tmp_path) -> None:
    docker = shutil.which("docker")
    if docker is None or subprocess.run([docker, "compose", "version"], capture_output=True).returncode != 0:
        # validate.sh runs the same check where the compose plugin is installed; the static checks above hold
        return
    env = tmp_path / ".env"
    env.write_text((DEPLOY / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    out = subprocess.run(
        [docker, "compose", "--env-file", str(env), "-f", str(DEPLOY / "docker-compose.yml"),
         "--profile", "ollama", "config", "--services"],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert out.returncode == 0, out.stderr
    assert "ollama" in out.stdout.split()
    default = subprocess.run(
        [docker, "compose", "--env-file", str(env), "-f", str(DEPLOY / "docker-compose.yml"), "config", "--services"],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert default.returncode == 0, default.stderr
    assert "ollama" not in default.stdout.split()


def test_hb_16_runbook_covers_the_ticket() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for needle in (
        "OLLAMA_CONTEXT_LENGTH",
        "--tool-call-parser",
        "--enable-auto-tool-choice",
        "vllm/vllm-openai:",
        "ollama/ollama:",
        "allow_local",
        "KVKK",
        "--profile ollama",
        "/ai/admin/providers/openai_compatible",
        "sync",
        "probe=true",
        "GPU",
        "iptables",
        "Qwen3.5",
    ):
        assert needle in text, needle
    readme = (DEPLOY / "README.md").read_text(encoding="utf-8")
    assert "local-models.md" in readme and "--profile ollama" in readme
