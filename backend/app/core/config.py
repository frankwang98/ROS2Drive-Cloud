"""应用核心配置。"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置，支持环境变量覆盖（如 .env / K8s ConfigMap）。"""

    # 应用
    app_name: str = "Robot Cloud Platform"
    app_version: str = "0.1.0"
    debug: bool = False

    # 服务端口
    host: str = "0.0.0.0"
    port: int = 8000

    # 消息总线（MQTT / ZMQ）
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1884
    mqtt_topic_prefix: str = "robot"
    # ZMQ 发布端口
    zmq_pub_port: int = 5555

    # 默认机器人 ID（指令未指定 robot_id 时使用）
    default_robot_id: str = "car01"

    # 机器人订阅的 ROS2 话题（由 gateway 转发）
    robot_topics: list[str] = [
        "sdc/speed",
        "sdc/action_id",
        "sdc/front_distance",
        "sdc/obstacle_count",
        "simulation/markers",
        "sensor/lidar",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
