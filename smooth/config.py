# Elastic License 2.0
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: Elastic-2.0

"""
Configuration management for Smooth.

This module handles application configuration from environment variables.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    
    Assumptions:
    - Environment variables override defaults
    - API version is configurable
    - AUTH_ENABLED can be disabled for testing/development
    """
    
    # Authentication
    auth_enabled: bool = True
    
    # Database
    database_url: str = "sqlite:///./smooth.db"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_version: str = "v1"
    
    # MQTT
    mqtt_enabled: bool = False
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    
    # Logging
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )


settings = Settings()
