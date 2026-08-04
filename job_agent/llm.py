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
# Reasoning models need much more headroom — reasoning + answer share one
# budget, and stage 4's classification prompt can list 100+ links, which
# burns through a lot of it before the model gets to the answer. Even so,
# this budget gets exhausted often enough in practice (varies run to run on
# the same prompt) that a single retry at double the budget is worth it
# before giving up.
SUPPORTVECTORS_MAX_TOKENS = 8192
SUPPORTVECTORS_RETRY_MAX_TOKENS = 16384


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
            temperature=0,  # classification, not creative writing — want the same answer every time
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

    # temperature=0 (greedy decoding) is deterministic, which is normally
    # what we want for classification — but observed in practice: for some
    # prompts the greedy path itself runs long and never reaches an answer
    # within budget, on every attempt, regardless of how large the budget is
    # (retried at 2x tokens with temperature=0 and still exhausted it). A
    # nonzero temperature on retry resamples a different reasoning path,
    # which is the actual fix for a stuck trajectory — a bigger budget alone
    # just delays hitting the same wall.
    attempts = [
        (SUPPORTVECTORS_MAX_TOKENS, 0),
        (SUPPORTVECTORS_RETRY_MAX_TOKENS, 0.4),
    ]
    for attempt_max_tokens, attempt_temperature in attempts:
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=attempt_max_tokens,
                temperature=attempt_temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            # A self-hosted/gateway endpoint's failure modes are less
            # predictable than Anthropic's typed exceptions (bad base URL,
            # VPN not connected, invalid model name, etc.), so this catches
            # broadly and reports what to check rather than crashing.
            print(f"WARNING: SupportVectors request failed: {e}")
            print(
                "  Check SUPPORTVECTORS_BASE_URL/API_KEY, that you're on the required "
                "network/VPN if applicable, and that SUPPORTVECTORS_MODEL is valid."
            )
            return None

        content = response.choices[0].message.content
        if content:
            return content.strip()

        finish_reason = response.choices[0].finish_reason
        if finish_reason == "length" and attempt_max_tokens < SUPPORTVECTORS_RETRY_MAX_TOKENS:
            print(
                f"WARNING: SupportVectors spent the whole {attempt_max_tokens}-token budget on "
                f"internal reasoning with no answer — retrying once at "
                f"{SUPPORTVECTORS_RETRY_MAX_TOKENS} tokens / temperature={attempts[1][1]}."
            )
            continue

        print(
            f"WARNING: SupportVectors returned empty content (finish_reason={finish_reason})."
        )
        return None

    return None


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
