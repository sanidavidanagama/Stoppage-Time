"""
config.py

Central settings using pydantic-settings.
Loads from .env automatically.
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
    ARENA: str = "https://stair-ai.com"
    AGENT_ID: str = "18161beb-b5f5-464d-ad1b-8ae2d9323fbc"
    
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

    # --- Superbase (LTM and Ledger) ---
    ST_SUPABASE_URL:              str = ""
    ST_SUPABASE_PUBLISHABLE_KEY:  str = ""
    ST_SUPABASE_SECRET_KEY:       str = ""


    # --- Tournament ---
    SEASON_ID: int = 26618

    # --- Ledger ---
    LEDGER_SCHEMA_VERSION: str = "0.3"

    # --- Agent behaviour ---
    DEBUG:           bool  = True
    MAX_TOOL_ROUNDS: int   = 4
    MAX_BET_SIZE:    float = 15.0
    MIN_EDGE_PP:     float = 5.0

    # --- Backend auth ---
    ADMIN_USERNAME:  str = "admin"
    ADMIN_PASSWORD:  str = "changeme"
    JWT_SECRET_KEY:  str = "changeme-set-a-real-secret-in-env"
    JWT_ALGORITHM:   str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    # Comma-separated string — split with allowed_origins_list property
    ALLOWED_ORIGINS: str = "*"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

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