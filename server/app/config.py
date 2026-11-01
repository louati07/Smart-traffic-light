"""Configuration loader combining config.yaml and environment variables (.env)."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_YAML_PATH = PROJECT_ROOT / "config.yaml"


class Settings(BaseSettings):
    """Application settings with defaults from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Mode Flags
    firebase_mode: str = Field(default="memory", alias="FIREBASE_MODE")
    esp32_mode: str = Field(default="mock", alias="ESP32_MODE")
    vision_mode: str = Field(default="replay", alias="VISION_MODE")
    mongo_mode: str = Field(default="memory", alias="MONGO_MODE")

    # API
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    # Firebase Realtime DB
    firebase_db_url: str = Field(
        default="https://emergency-traffic-controller-default-rtdb.europe-west1.firebasedatabase.app",
        alias="FIREBASE_DB_URL",
    )
    firebase_db_secret: str | None = Field(default=None, alias="FIREBASE_DB_SECRET")

    # MongoDB
    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db: str = Field(default="smart_intersection", alias="MONGO_DB")

    # Security & Auth
    jwt_secret: str = Field(
        default="dev-jwt-secret-do-not-use-in-production-abcdef123456",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=480, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Command Signing
    hmac_secret: str = Field(
        default="dev-hmac-shared-key-wokwi-server-2026",
        alias="HMAC_SECRET",
    )
    hmac_enforce: bool = Field(default=False, alias="HMAC_ENFORCE")

    # Rate Limiting
    rate_limit_detections_per_sec: float = Field(
        default=10.0,
        alias="RATE_LIMIT_DETECTIONS_PER_SEC",
    )
    rate_limit_burst: int = Field(default=20, alias="RATE_LIMIT_BURST")

    # YAML Config cache
    _yaml_config: dict[str, Any] | None = None

    @property
    def yaml_data(self) -> dict[str, Any]:
        if self._yaml_config is None:
            if CONFIG_YAML_PATH.exists():
                with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
                    self._yaml_config = yaml.safe_load(f) or {}
            else:
                self._yaml_config = {}
        return self._yaml_config

    @property
    def intersection_id(self) -> str:
        return self.yaml_data.get("intersection", {}).get("id", "i1")

    @property
    def timings(self) -> dict[str, Any]:
        return self.yaml_data.get("timings", {
            "green_ms": 10000,
            "yellow_ms": 3000,
            "all_red_ms": 2000,
            "priority_yellow_ms": 2000,
            "priority_all_red_ms": 1000,
            "min_green_ms": 5000,
            "priority_max_ms": 30000,
            "heartbeat_timeout_ms": 10000,
            "poll_ms": 1000,
            "command_ttl_s": 15,
        })

    @property
    def engine_config(self) -> dict[str, Any]:
        return self.yaml_data.get("engine", {
            "priority_cooldown_s": 2.0,
            "priority_conflict_max_wait_s": 15.0,
        })

    @property
    def vision_config(self) -> dict[str, Any]:
        return self.yaml_data.get("vision", {
            "model_weights": "vision/weights/best.pt",
            "imgsz": 640,
            "stride": 3,
            "target_fps": 8,
            "conf_threshold": 0.55,
            "bbox_area_ratio_min": 0.005,
            "debounce_window_w": 8,
            "debounce_confirm_k": 5,
            "release_after_s": 3.0,
        })


settings = Settings()
