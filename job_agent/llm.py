"""Shared LLM call path for classification tasks in stages 3+.

Mirrors the sibling Spotify project's insights.py pattern: two providers
switched via LLM_PROVIDER ("anthropic" default, or "supportvectors" — an
OpenAI-compatible gateway, e.g. a bootcamp-provided endpoint), never falls
back silently between them, and every call returns None (with a printed
warning) on failure instead of raising — a misconfigured or unreachable LLM
should degrade a single classification, not crash a run processing many
companies.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

ANTHROPIC_MODEL = "claude-sonnet-4-5"
SUPPORTVECTORS_DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_TOKENS = 512
# Reasoning models need much more headroom — reasoning + answer share one budget.
SUPPORTVECTORS_MAX_TOKENS = 2048


def _call_anthropic(prompt: str) -> str | None:
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "WARNING: ANTHROPIC_API_KEY not set — skipping LLM call. "
            "Get one at https://console.anthropic.com/settings/keys and add it to .env."
        )
        return None

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        print("WARNING: Anthropic API authentication failed — check ANTHROPIC_API_KEY.")
        return None
    except anthropic.RateLimitError:
        print("WARNING: Anthropic API rate limited — try again shortly.")
        return None
    except anthropic.APIStatusError as e:
        print(f"WARNING: Anthropic API error ({e.status_code}): {e.message}")
        return None
    except anthropic.APIConnectionError as e:
        print(f"WARNING: couldn't reach the Anthropic API: {e}")
        return None

    return "".join(block.text for block in response.content if block.type == "text").strip()


def _call_supportvectors(prompt: str) -> str | None:
    load_dotenv()
    api_key = os.getenv("SUPPORTVECTORS_API_KEY")
    base_url = os.getenv("SUPPORTVECTORS_BASE_URL")
    model = os.getenv("SUPPORTVECTORS_MODEL", SUPPORTVECTORS_DEFAULT_MODEL)

    missing = [
        name
        for name, val in (("SUPPORTVECTORS_API_KEY", api_key), ("SUPPORTVECTORS_BASE_URL", base_url))
        if not val
    ]
    if missing:
        print(
            f"WARNING: {', '.join(missing)} not set — skipping LLM call "
            "(LLM_PROVIDER=supportvectors). Add them to .env."
        )
        return None

    from openai import OpenAI  # local import: only needed for this provider

    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=SUPPORTVECTORS_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        # A self-hosted/gateway endpoint's failure modes are less predictable
        # than Anthropic's typed exceptions (bad base URL, VPN not connected,
        # invalid model name, etc.), so this catches broadly and reports what
        # to check rather than crashing.
        print(f"WARNING: SupportVectors request failed: {e}")
        print(
            "  Check SUPPORTVECTORS_BASE_URL/API_KEY, that you're on the required "
            "network/VPN if applicable, and that SUPPORTVECTORS_MODEL is valid."
        )
        return None

    content = response.choices[0].message.content
    if not content:
        finish_reason = response.choices[0].finish_reason
        print(
            f"WARNING: SupportVectors returned empty content (finish_reason={finish_reason}). "
            "If this is a reasoning model, it likely spent the entire token budget on "
            "internal reasoning before writing an answer — try raising max_tokens further."
        )
        return None
    return content.strip()


def call_llm(prompt: str) -> str | None:
    """Dispatches on LLM_PROVIDER (default "anthropic"). Unknown or
    misconfigured provider just skips with a printed warning, never raises."""
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        return _call_anthropic(prompt)
    if provider == "supportvectors":
        return _call_supportvectors(prompt)

    print(f"WARNING: unknown LLM_PROVIDER '{provider}' (expected 'anthropic' or 'supportvectors') — skipping.")
    return None
