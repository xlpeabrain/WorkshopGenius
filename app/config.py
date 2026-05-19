from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    slides_dir: Path = Path("slides")
    catalog_path: Path = Path("catalog.json")
    output_dir: Path = Path("output")
    model: str = "claude-sonnet-4-6"
    max_output_slides: int = 40
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB

    class Config:
        env_file = ".env"


settings = Settings()
