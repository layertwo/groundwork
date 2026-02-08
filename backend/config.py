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
    aws_management_account_id: str = ""
    aws_groundwork_account_id: str = Field(default="", pattern=r"^$|^[0-9]{12}$")
    aws_groundwork_role_name: str = Field(
        default="GroundworkStackSetRole", pattern=r"^[\w+=,.@-]{1,64}$"
    )
    aws_org_root_id: str = Field(default="", pattern=r"^$|^r-[a-z0-9]{4,32}$")
    admin_role_name: str = "GroundworkAdmin-DO-NOT-DELETE"

    # App
    app_name: str = "Groundwork"
    app_url: str = "http://localhost:8000"
    session_secret: str = Field(default="change-me-to-a-random-string")
    debug: bool = False


settings = Settings()
