"""Configuration, loaded from the environment (and a local .env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


PORT = int(_env("PORT", "4000"))
SESSION_SECRET = _env("SESSION_SECRET", "")
DATABASE_PATH = _env("DATABASE_PATH", str(Path.cwd() / "data" / "bff.db"))

ENGINE_PROJECT = _env("GEAP_ENGINE_PROJECT", "adk-tut-508714")
ENGINE_LOCATION = _env("GEAP_ENGINE_LOCATION", "us-central1")
ENGINE_ID = _env("GEAP_ENGINE_ID", "335803495506509824")
ENGINE_RESOURCE = (
    f"projects/{ENGINE_PROJECT}/locations/{ENGINE_LOCATION}"
    f"/reasoningEngines/{ENGINE_ID}"
)

if not SESSION_SECRET:
    print("[bff] SESSION_SECRET is not set; portal sessions cannot be verified.")
