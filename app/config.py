"""
Application configuration using Pydantic Settings.
Values are loaded from environment variables (or a .env file).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Which eligibility adapter to use: "mock" | "availity"
    eligibility_provider: str = "mock"

    # Availity OAuth2 credentials (only required when provider is "availity")
    availity_client_id: str = ""
    availity_client_secret: str = ""
    availity_base_url: str = "https://api.availity.com"
    # Space-delimited OAuth scopes; can be overridden in .env for each client app.
    availity_scope: str = "healthcare-hipaa-transactions-demo"
    # Optional JSON file that defines available provider connections for the UI.
    connections_config_path: str = "connections.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Singleton settings instance used throughout the application
settings = Settings()
