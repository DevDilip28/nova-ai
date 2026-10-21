from pathlib import Path
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    ai_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = ""
    aws_region: str = "us-east-1"
    bedrock_model_id: str = ""
    tavily_api_key: str = ""
    database_path: Path = ROOT / "data" / "nova.db"
    projects_root: Path = ROOT / "generated_projects"
    allowed_origins: str = "http://localhost:5173"
    command_timeout_seconds: int = 45
    dependency_install_timeout_seconds: int = 240

settings = Settings()
logging.getLogger("uvicorn.error").info("NOVA AI provider selected: %s", settings.ai_provider.strip().lower())
if not settings.database_path.is_absolute(): settings.database_path = ROOT / settings.database_path
if not settings.projects_root.is_absolute(): settings.projects_root = ROOT / settings.projects_root
settings.database_path.parent.mkdir(parents=True, exist_ok=True)
settings.projects_root.mkdir(parents=True, exist_ok=True)

