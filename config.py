from pydantic_settings import BaseSettings
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    import os


class Settings(BaseSettings):
    model_name: str = "google-gla:gemini-2.5-pro"
    # model_name: str = "anthropic:claude-3-5-haiku-latest"
    fake_bank_url: str = "http://127.0.0.1:8001"
    teams_webhook_url: str = ""
    approval_base_url: str = "http://127.0.0.1:8000"
    
    class Config:
        extra = "ignore"
        env_file = os.getenv("ENV_FILE", ".env")

settings = Settings()
