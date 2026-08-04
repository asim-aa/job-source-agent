"""Environment-driven config. Reads .env if python-dotenv is installed."""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

LINKEDIN_PROVIDER = os.environ.get("LINKEDIN_PROVIDER", "mock")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
