from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://groundwork:groundwork@localhost:5432/groundwork"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800

    # OIDC
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:8000/api/auth/callback"

    # AWS
    aws_region: str = "us-east-1"
    aws_portfolio_id: str = ""

    # App
    app_name: str = "Groundwork"
    app_url: str = "http://localhost:8000"
    session_secret: str = Field(default="change-me-to-a-random-string")
    debug: bool = False


settings = Settings()
