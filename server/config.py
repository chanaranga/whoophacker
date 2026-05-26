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

    # UTC hour (0-23) to run the automatic sleep analysis if the user
    # didn't log sleep manually. Amsterdam CEST (UTC+2) 10am = UTC 8.
    auto_sleep_check_utc_hour: int = 8

    # UTC hour (0-23) to send proactive workout suggestion.
    # Amsterdam CEST (UTC+2) 5pm = UTC 15.
    auto_suggestion_utc_hour: int = 15


settings = Settings()
