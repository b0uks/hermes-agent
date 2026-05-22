#!/usr/bin/env python3
"""Sync RDSec AI Endpoint models into a Hermes config.yaml provider."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ENDPOINT = "https://api.rdsec.trendmicro.com/prod/aiendpoint/v1"
DEFAULT_PROVIDER = "trendai"
DEFAULT_CONFIG = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "config.yaml"
DEFAULT_DOCKER_CONFIG = Path.home() / "hermes-data" / "config.yaml"

SKIP_RE = re.compile(
    r"embed|tts|whisper|transcribe|diarize|realtime|audio|image|stable-diffusion|"
    r"stable-image|dall-e|text-embedding",
    re.IGNORECASE,
)


def _token_from_env() -> str:
    for key in ("RDSEC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config is not a YAML object: {path}")
    return data


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    tmp.replace(path)


def _extract_token_from_config(config: dict[str, Any], provider: str) -> str:
    providers = config.get("providers")
    if isinstance(providers, dict):
        entry = providers.get(provider)
        if isinstance(entry, dict):
            token = str(entry.get("api_key") or "").strip()
            if token:
                return token
            key_env = str(entry.get("key_env") or entry.get("api_key_env") or "").strip()
            if key_env and os.environ.get(key_env, "").strip():
                return os.environ[key_env].strip()

    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        token = str(model_cfg.get("api_key") or "").strip()
        if token:
            return token
    return ""


def _fetch_models(endpoint: str, token: str, timeout: float) -> Any:
    headers_to_try: list[dict[str, str]] = []
    if token:
        headers_to_try.extend(
            [
                {"Authorization": f"Bearer {token}"},
                {"x-api-key": token},
                {"api-key": token},
            ]
        )
    headers_to_try.append({})

    url = endpoint.rstrip("/") + "/models"
    last_error: Exception | None = None
    for auth_headers in headers_to_try:
        headers = {"Content-Type": "application/json", "User-Agent": "hermes-rdsec-model-sync"}
        headers.update(auth_headers)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            continue
    raise SystemExit(f"Failed to fetch models from {url}: {last_error}")


def _model_ids(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        raw = payload.get("data", payload.get("models", []))
    elif isinstance(payload, list):
        raw = payload
    else:
        raise SystemExit("Unexpected /models response shape")

    ids: list[str] = []
    for item in raw:
        model_id = item.get("id", "") if isinstance(item, dict) else str(item)
        model_id = model_id.strip()
        if model_id and not SKIP_RE.search(model_id):
            ids.append(model_id)
    return sorted(dict.fromkeys(ids))


def _parse_version(value: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", value)
    return tuple(int(n) for n in nums) if nums else (0,)


def _family_key_and_version(model_id: str) -> tuple[str, tuple[int, ...]]:
    alt = re.match(r"^(claude)-(opus|sonnet|haiku)-(\d[\d.-]*\d?)(-.+)?$", model_id)
    if alt:
        version = alt.group(3).replace("-", ".")
        provider_suffix = alt.group(4) or ""
        model_id = f"{alt.group(1)}-{version}-{alt.group(2)}{provider_suffix}"

    match = re.match(r"^([a-z]+)-(\d+(?:\.\d+)?)-(.+)$", model_id)
    if match:
        prefix, version, suffix = match.groups()
        return f"{prefix}-{suffix}", _parse_version(version)

    match = re.match(r"^([a-z]+-?[a-z]*)-v?(\d+(?:\.\d+)?)$", model_id)
    if match:
        prefix, version = match.groups()
        return prefix, _parse_version(version)

    match = re.match(r"^(.+?)-(\d+(?:\.\d+)?b?)$", model_id)
    if match and re.search(r"\d", match.group(2)):
        prefix, version = match.groups()
        return prefix, _parse_version(version)

    return model_id, (0,)


def _dedupe_latest(models: list[str]) -> list[str]:
    families: dict[str, list[tuple[tuple[int, ...], str]]] = defaultdict(list)
    for model in models:
        family, version = _family_key_and_version(model)
        families[family].append((version, model))
    latest = {sorted(entries, reverse=True)[0][1] for entries in families.values()}
    return sorted(latest)


def _provider_entry(config: dict[str, Any], provider: str, endpoint: str) -> dict[str, Any]:
    providers = config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise SystemExit("config.yaml providers must be a mapping")
    entry = providers.setdefault(provider, {})
    if not isinstance(entry, dict):
        entry = {}
        providers[provider] = entry
    entry.setdefault("name", "RDSec AI Endpoint")
    entry["base_url"] = endpoint.rstrip("/") + "/"
    entry.setdefault("transport", "chat_completions")
    return entry


def _sync_aliases(config: dict[str, Any], models: list[str], provider: str, endpoint: str) -> None:
    aliases = config.setdefault("model_aliases", {})
    if not isinstance(aliases, dict):
        return
    alias_patterns = {
        "codex": ("gpt-5.3-codex", "gpt-5.1-codex-max", "codex", "gpt-"),
        "gemini": ("gemini-3.1-pro", "gemini-3-flash", "gemini"),
        "claude": ("claude-sonnet-4-6", "claude-4.6-sonnet", "claude"),
        "opus": ("claude-opus-4-7", "opus"),
        "sonnet": ("claude-sonnet-4-6", "sonnet"),
        "kimi": ("kimi-k2.6", "kimi"),
        "deepseek": ("deepseek-v3.2", "deepseek-r1", "deepseek"),
        "glm": ("glm-5", "glm"),
    }
    for alias, needles in alias_patterns.items():
        match = next((m for n in needles for m in models if n in m.lower()), None)
        if match:
            aliases[alias] = {"model": match, "provider": provider, "base_url": endpoint.rstrip("/") + "/"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="Hermes config.yaml path")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="OpenAI-compatible endpoint base URL")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="providers: key to update")
    parser.add_argument("--token", default="", help="API token; otherwise env/config token is used")
    parser.add_argument("--all", action="store_true", help="Keep every chat model instead of latest per family")
    parser.add_argument("--dry-run", action="store_true", help="Print planned models without writing config")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config or (DEFAULT_DOCKER_CONFIG if DEFAULT_DOCKER_CONFIG.exists() else DEFAULT_CONFIG)
    config = _read_yaml(config_path)
    token = args.token.strip() or _token_from_env() or _extract_token_from_config(config, args.provider)

    payload = _fetch_models(args.endpoint, token, args.timeout)
    all_models = _model_ids(payload)
    models = all_models if args.all else _dedupe_latest(all_models)

    print(f"Fetched {len(all_models)} chat models from {args.endpoint}/models", file=sys.stderr)
    if not args.all:
        print(f"Keeping {len(models)} latest-per-family models", file=sys.stderr)

    if args.dry_run:
        for model in models:
            print(model)
        return 0

    entry = _provider_entry(config, args.provider, args.endpoint)
    existing = entry.get("models")
    old_models = set(existing if isinstance(existing, list) else existing.keys() if isinstance(existing, dict) else [])
    entry["models"] = models
    entry.setdefault("default_model", config.get("model", {}).get("default") if isinstance(config.get("model"), dict) else models[0])
    if "synced_at" in entry or True:
        entry["synced_at"] = int(time.time())
    _sync_aliases(config, models, args.provider, args.endpoint)
    _write_yaml(config_path, config)

    new_models = set(models)
    print(f"Updated {config_path}", file=sys.stderr)
    print(f"  {len(new_models - old_models)} added, {len(old_models & new_models)} kept, {len(old_models - new_models)} removed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
