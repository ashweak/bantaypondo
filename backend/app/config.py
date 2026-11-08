from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./bantaypondo.db"  # use postgresql+psycopg://... in production
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Red-flag thresholds
    above_abc_ratio: float = 1.001             # contract cost > ABC by more than 0.1%
    near_abc_ratio: float = 0.999              # used only for the dataset-wide stat
    late_days_low: int = 90                    # finished > 90 days after target
    late_days_high: int = 180
    concentration_share: float = 0.30          # contractor holds >= 30% of province value
    concentration_min_projects: int = 5


settings = Settings()
