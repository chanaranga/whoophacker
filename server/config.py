from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_url: str
    redis_url: str

    ollama_cloud_api_key: str
    ollama_cloud_base: str = "https://ollama.com"
    ollama_model: str = "deepseek-v3.1:671b-cloud"
    ollama_snapshot_model: str = "deepseek-v3.1:671b-cloud"

    signal_bot_number: str
    signal_user_number: str
    signal_api_url: str = "http://signal-rest:8080"

    server_secret: str

    # Local hour (0-23) to run automatic sleep analysis (default 10am).
    auto_sleep_check_local_hour: int = 10

    # Local hour (0-23) to send proactive workout suggestion (default 5pm).
    auto_suggestion_local_hour: int = 17

    # Fallback timezone if none has been received from the app yet.
    default_timezone: str = "Europe/Amsterdam"


settings = Settings()
