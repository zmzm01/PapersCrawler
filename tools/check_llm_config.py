#!/usr/bin/env python3
"""Validate the active LLM provider and its configured model catalogue."""

import argparse
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import CFG, LLM_ROLE_CONFIG_TARGETS  # noqa: E402


def fetch_model_ids(session=requests):
    """Fetch model IDs exposed by the active provider.

    Parameters
    ----------
    session : module or requests.Session, optional
        HTTP client used for the catalogue request.

    Returns
    -------
    set[str]
        Model IDs returned by the provider.

    Raises
    ------
    RuntimeError
        If no catalogue URL is configured or the response is malformed.
    """
    if not CFG.LLM_MODEL_LIST_URL:
        raise RuntimeError("active provider does not configure model_list_url")
    response = session.get(
        CFG.LLM_MODEL_LIST_URL,
        headers={"Authorization": f"Bearer {CFG.LLM_API_KEY}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError("model catalogue response does not contain a data list")
    return {
        str(entry["id"]).strip()
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("id", "")).strip()
    }


def configured_models():
    """Return active-provider role-to-model mappings."""
    return {
        role_name: str(getattr(CFG, target_name).get("model", "")).strip()
        for role_name, target_name in LLM_ROLE_CONFIG_TARGETS.items()
    }


def similar_model_ids(model_id, available_models, limit=10):
    """Return catalogue IDs that share a meaningful model-family token.

    Parameters
    ----------
    model_id : str
        Missing configured model ID.
    available_models : set[str]
        IDs returned by the provider.
    limit : int, optional
        Maximum suggestions to return.

    Returns
    -------
    list[str]
        Sorted candidate IDs from the same apparent model family.
    """
    tokens = [
        token.lower()
        for token in model_id.replace("/", "-").replace(".", "-").split("-")
        if len(token) >= 3 and not token.isdigit()
    ]
    matches = [
        candidate for candidate in available_models
        if any(token in candidate.lower() for token in tokens)
    ]
    return sorted(matches)[:limit]


def main():
    """Run configuration and non-billing model-catalogue checks."""
    parser = argparse.ArgumentParser(
        description="Check the active LLM provider without sending prompts",
    )
    parser.parse_args()
    print(f"Active provider: {CFG.LLM_ACTIVE_PROVIDER}")
    print(f"API endpoint: {CFG.LLM_BASE_URL}")
    models = configured_models()
    try:
        available_models = fetch_model_ids()
    except (requests.RequestException, RuntimeError, ValueError) as error:
        print(f"Model catalogue check failed: {error}", file=sys.stderr)
        return 2
    missing = []
    for role_name, model_id in models.items():
        available = model_id in available_models
        print(f"{role_name}: {model_id} [{'ok' if available else 'missing'}]")
        if not available:
            missing.append(model_id)
    if missing:
        print(
            "Configured model IDs missing from provider catalogue: "
            + ", ".join(sorted(set(missing))),
            file=sys.stderr,
        )
        for model_id in sorted(set(missing)):
            suggestions = similar_model_ids(model_id, available_models)
            if suggestions:
                print(f"Available IDs similar to {model_id}:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
