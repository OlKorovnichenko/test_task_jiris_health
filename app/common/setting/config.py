from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_visit_completed_topic: str = "VISIT_COMPLETED_TOPIC"
    kafka_billing_group: str = "BILLING"
    outbox_poll_interval: float = Field(default=1.0, gt=0)
    event_retry_interval: float = Field(default=5.0, gt=0)

    @property
    def postgres_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Config()
