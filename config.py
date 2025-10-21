from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_name: str = "google-gla:gemini-2.5-pro"
    # model_name: str = "anthropic:claude-3-5-haiku-latest"
    fake_bank_url: str = "http://127.0.0.1:8001"

settings = Settings()
