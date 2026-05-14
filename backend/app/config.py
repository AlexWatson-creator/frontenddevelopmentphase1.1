"""Application settings loaded from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class Settings:
    """Application configuration.

    Reads DB_SERVER from .env (or environment).
    Connection uses Windows trusted auth via ODBC Driver 17.
    """

    DB_SERVER: str = os.getenv("DB_SERVER", "localhost")
    DB_NAME: str = "JAPBIMDB"
    DB_DRIVER: str = "ODBC+Driver+17+for+SQL+Server"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mssql+pyodbc://{self.DB_SERVER}/{self.DB_NAME}"
            f"?driver={self.DB_DRIVER}&trusted_connection=yes"
        )


settings = Settings()
