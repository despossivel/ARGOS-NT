from __future__ import annotations

import json
from importlib.util import find_spec
from urllib.error import URLError
from urllib.request import Request, urlopen

from argos_nt.core.constants import SUPPORTED_PROVIDERS


def get_provider_model(config, provider: str) -> str:
    name = provider.lower().strip()
    if name == "ollama":
        return config.ai.ollama_model or config.ai.model
    if name == "openai":
        return config.ai.openai_model or config.ai.model
    if name == "anthropic":
        return config.ai.anthropic_model or config.ai.model
    if name == "deepseek":
        return config.ai.deepseek_model or config.ai.model
    return config.ai.model


def mask_secret(value: str | None) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def provider_dependency_name(provider: str) -> str | None:
    mapping = {
        "ollama": "langchain_ollama",
        "openai": "langchain_openai",
        "anthropic": "langchain_anthropic",
        "deepseek": "langchain_openai",
    }
    return mapping.get(provider)


def verify_ollama_reachability(
    base_url: str, expected_model: str, timeout_seconds: float = 4.0
) -> None:
    normalized_base = base_url.rstrip("/")
    tags_url = f"{normalized_base}/api/tags"
    request = Request(tags_url, method="GET")  # noqa: S310

    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(
            f"Ollama is not reachable at {tags_url}. "
            "Start Ollama locally or via Docker before scanning."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to query Ollama health endpoint at {tags_url}: {exc}") from exc

    models = payload.get("models", []) if isinstance(payload, dict) else []
    available = {str(item.get("name", "")).strip() for item in models if isinstance(item, dict)}
    if expected_model and expected_model not in available:
        available_preview = ", ".join(sorted(n for n in available if n)) or "none"
        raise RuntimeError(
            f"Ollama is reachable, but model '{expected_model}' is not available. "
            f"Available models: {available_preview}"
        )


def check_active_provider(config) -> tuple[str, str]:
    """Return (status, detail) for the currently active provider."""
    provider = str(config.ai.provider).lower().strip()
    model = get_provider_model(config, provider)

    if provider not in SUPPORTED_PROVIDERS:
        return "ERR", f"unsupported provider '{provider}'"

    dep = provider_dependency_name(provider)
    if dep and find_spec(dep) is None:
        return "ERR", f"missing Python package '{dep}' for provider '{provider}'"

    if provider == "ollama":
        try:
            verify_ollama_reachability(config.ai.ollama_base_url, model)
            return "OK", f"ollama model={model} url={config.ai.ollama_base_url}"
        except Exception as exc:
            return "ERR", str(exc)

    if provider == "openai":
        if not config.api_keys.openai:
            return "ERR", "OPENAI_API_KEY is not set"
        return "OK", f"openai model={model} key={mask_secret(config.api_keys.openai)}"

    if provider == "anthropic":
        if not config.api_keys.anthropic:
            return "ERR", "ANTHROPIC_API_KEY is not set"
        return "OK", f"anthropic model={model} key={mask_secret(config.api_keys.anthropic)}"

    if provider == "deepseek":
        if not config.api_keys.deepseek:
            return "ERR", "DEEPSEEK_API_KEY is not set"
        if not config.ai.deepseek_base_url.strip():
            return "ERR", "DeepSeek base URL is not set"
        return "OK", f"deepseek model={model} url={config.ai.deepseek_base_url}"

    return "ERR", f"unsupported provider '{provider}'"


def all_provider_status(config) -> list[dict[str, str | bool]]:
    """Return status for every supported provider (used by both CLI and TUI)."""
    active = str(config.ai.provider).lower().strip()
    results: list[dict[str, str | bool]] = []

    for provider in SUPPORTED_PROVIDERS:
        model = get_provider_model(config, provider)
        is_active = provider == active

        if provider == "ollama":
            try:
                verify_ollama_reachability(config.ai.ollama_base_url, model)
                results.append(
                    {"provider": provider, "model": model, "status": "OK",
                     "detail": f"url={config.ai.ollama_base_url}", "active": is_active}
                )
            except Exception as exc:
                results.append(
                    {"provider": provider, "model": model, "status": "ERR",
                     "detail": str(exc), "active": is_active}
                )

        elif provider == "openai":
            ok = bool(config.api_keys.openai)
            results.append(
                {"provider": provider, "model": model,
                 "status": "OK" if ok else "ERR",
                 "detail": "API key set" if ok else "missing OPENAI_API_KEY",
                 "active": is_active}
            )

        elif provider == "anthropic":
            ok = bool(config.api_keys.anthropic)
            results.append(
                {"provider": provider, "model": model,
                 "status": "OK" if ok else "ERR",
                 "detail": "API key set" if ok else "missing ANTHROPIC_API_KEY",
                 "active": is_active}
            )

        elif provider == "deepseek":
            has_key = bool(config.api_keys.deepseek)
            has_url = bool(config.ai.deepseek_base_url.strip())
            ok = has_key and has_url
            if ok:
                detail = f"API key set, url={config.ai.deepseek_base_url}"
            elif not has_key:
                detail = "missing DEEPSEEK_API_KEY"
            else:
                detail = "missing DeepSeek base URL"
            results.append(
                {"provider": provider, "model": model,
                 "status": "OK" if ok else "ERR",
                 "detail": detail, "active": is_active}
            )

    return results
