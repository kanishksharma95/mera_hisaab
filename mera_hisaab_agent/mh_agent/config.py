"""
Configuration loader for the Mera Hisaab ADK Agent.

Zero hardcoding: all paths, keys, IDs, and settings must come from the environment.
Validates required variables at import/startup time and fails fast with clear errors.
"""
from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

# Search order for .env:
# 1. mera_hisaab_agent/.env
# 2. Project root .env (parent directory)
AGENT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = AGENT_ROOT.parent

agent_env = AGENT_ROOT / ".env"
project_env = PROJECT_ROOT / ".env"

if agent_env.exists():
    load_dotenv(agent_env, override=False)
if project_env.exists():
    load_dotenv(project_env, override=False)


@dataclass(frozen=True)
class AgentConfig:
    google_api_key: str
    gemini_model: str
    mera_hisaab_path: Path
    django_settings_module: str
    business_id: int
    agent_actor_user_id: int


def _get_required_env(key: str) -> str:
    val = os.getenv(key)
    if not val or not val.strip():
        raise ValueError(
            f"Required environment variable '{key}' is missing or empty. "
            f"Please define it in mera_hisaab_agent/.env or the system environment."
        )
    return val.strip()


def _parse_optional_positive_int(key: str) -> int:
    """Parse an optional positive-int env var; return 0 when unset/empty.

    Used for the standalone fallback tenant (BUSINESS_ID / AGENT_ACTOR_USER_ID).
    In the web app these are supplied per-request instead, so 0 is valid here.
    """
    raw = os.getenv(key, "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError()
    except ValueError:
        raise ValueError(
            f"{key} must be a positive integer when set, got '{raw}'."
        )
    return value


def load_config() -> AgentConfig:
    """Validate and return the loaded agent configuration."""
    google_api_key = _get_required_env("GOOGLE_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    django_settings_module = os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.dev").strip()

    # MERA_HISAAB_PATH is required for standalone runs (to bootstrap Django), but
    # optional when embedded in the running web app — default to the project root
    # (the parent of mera_hisaab_agent/).
    raw_path = os.getenv("MERA_HISAAB_PATH", "").strip() or str(PROJECT_ROOT)
    mera_hisaab_path = Path(raw_path).resolve()
    if not mera_hisaab_path.exists():
        raise ValueError(
            f"MERA_HISAAB_PATH '{raw_path}' does not exist on disk."
        )

    # BUSINESS_ID / AGENT_ACTOR_USER_ID are the standalone fallback tenant. In the
    # web app each request sets its own tenant via context.set_tenant_context(),
    # so these are OPTIONAL there and default to 0 (meaning "no fixed fallback").
    business_id = _parse_optional_positive_int("BUSINESS_ID")
    agent_actor_user_id = _parse_optional_positive_int("AGENT_ACTOR_USER_ID")

    return AgentConfig(
        google_api_key=google_api_key,
        gemini_model=gemini_model,
        mera_hisaab_path=mera_hisaab_path,
        django_settings_module=django_settings_module,
        business_id=business_id,
        agent_actor_user_id=agent_actor_user_id,
    )


# Export validated singleton config
config = load_config()

