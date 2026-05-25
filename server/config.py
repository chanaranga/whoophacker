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


settings = Settings()
