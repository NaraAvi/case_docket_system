import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEFAULT_DB_PATH = (BASE_DIR / "instance" / "case_docket_dev.db").resolve()


def _resolve_database_url():
    configured_url = os.getenv("DATABASE_URL")
    if not configured_url:
        return f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

    if configured_url.startswith("sqlite:///") and not configured_url.startswith("sqlite:////"):
        relative_target = configured_url.replace("sqlite:///", "", 1)
        if not os.path.isabs(relative_target):
            resolved_path = (BASE_DIR / relative_target).resolve()
            return f"sqlite:///{resolved_path.as_posix()}"

    return configured_url


class Config:
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "case-docket-dev-secret-key-32-chars-123456",
    )
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY",
        "case-docket-jwt-dev-secret-key-32-chars-123",
    )
    SQLALCHEMY_DATABASE_URI = _resolve_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(Config):
    DEBUG = False


def get_config():
    env = os.getenv("FLASK_ENV", "development").lower()
    config_map = {
        "development": DevelopmentConfig,
        "testing": TestingConfig,
        "production": ProductionConfig,
    }
    return config_map.get(env, DevelopmentConfig)
