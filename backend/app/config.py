"""Runtime settings, read from environment variables."""
import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    # "anthropic" uses the real LLM; "mock" runs fully offline for dev, tests and CI.
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{APP_DIR.parent / 'catbooks.db'}")
    kb_dir: Path = Path(os.getenv("KB_DIR", str(APP_DIR / "kb")))
    agent_name: str = os.getenv("AGENT_NAME", "배상담")
    brand_name: str = os.getenv("BRAND_NAME", "캣북스 고객센터")
    top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "3"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Seoul")
    # Demo-only helpers (simulated logistics, one-click seed). Turn off for anything real.
    demo_tools: bool = os.getenv("DEMO_TOOLS", "1") == "1"


settings = Settings()
