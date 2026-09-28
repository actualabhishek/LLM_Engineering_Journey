from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    admin_password: str = ""
    secret_key: str = ""
    database_url: str = "sqlite:////data/app.db"
    gpu_worker_url: str = ""
    gpu_worker_token: str = ""


settings = Settings()
