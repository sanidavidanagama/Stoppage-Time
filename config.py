"""
config.py

Central settings using pydantic-settings.
Loads from .env automatically.
Only two secrets needed: ARENA_KEY and GEMINI_API_KEY.
"""

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Secrets (from .env) ---
    ARENA_KEY:      str
    GEMINI_API_KEY: str

    # --- Arena ---
    ARENA: str = "https://staging.stair-ai.com"

    @property
    def SPORTMONKS_PROXY(self) -> str:
        return f"{self.ARENA}/api/v1/data/proxy/sportmonks/v3/football"

    @property
    def POLYMARKET_GAMMA(self) -> str:
        return f"{self.ARENA}/api/v1/data/proxy/polymarket-gamma"

    @property
    def POLYMARKET_CLOB(self) -> str:
        return f"{self.ARENA}/api/v1/data/proxy/polymarket-clob"

    # --- Supabase (public shared key) ---
    SUPABASE_URL: str = "https://ezvbmtvrvzageqixvdak.supabase.co"
    SUPABASE_KEY: str = "sb_publishable__m8bOkD05ToFwATpaWST5w_2-3fGS7V"

    # --- Gemini ---
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # --- Tournament ---
    SEASON_ID: int = 26618

    # --- Ledger ---
    LEDGER_SCHEMA_VERSION: str = "0.3"

    # --- Agent behaviour ---
    MAX_TOOL_ROUNDS: int   = 5
    MAX_BET_SIZE:    float = 5.0
    MIN_EDGE_PP:     float = 5.0

    # --- Headers ---
    @property
    def H_ARENA(self) -> dict:
        return {"x-api-key": self.ARENA_KEY}

    @property
    def H_WCA(self) -> dict:
        return {
            "apikey":         self.SUPABASE_KEY,
            "Accept-Profile": "world_cup_arena",
        }

    @property
    def H_PUBLIC(self) -> dict:
        return {"apikey": self.SUPABASE_KEY}


settings = Settings()