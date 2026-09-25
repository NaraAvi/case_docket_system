import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    IPID_S16_COMMENCEMENT_DATE = os.getenv("IPID_S16_COMMENCEMENT_DATE") or None
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "case-docket-dev-secret-key-32-chars-123456",
    )
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY",
        "case-docket-jwt-dev-secret-key-32-chars-123",
    )
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///case_docket_dev.db")
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
