"""应用核心配置。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，支持环境变量覆盖（如 .env / K8s ConfigMap）。"""

    # 应用
    app_name: str = "Robot Cloud Platform"
    app_version: str = "0.2.0"
    debug: bool = False

    # 运行模式：simulation（仿真，默认）/ real（实车，接入本地 ROS2）
    # 可通过环境变量 ROBOT_MODE 或 /api/mode 动态切换
    robot_mode: str = "simulation"

    # 地图区域（米），用于 Web Dashboard 地图绘制
    map_width: float = 20.0
    map_height: float = 20.0
    map_cell: float = 1.0  # 网格大小（米）

    # 服务端口
    host: str = "0.0.0.0"
    port: int = 8000

    # MQTT 是唯一默认车云数据面；ZMQ 仅供显式启用的实验用途。
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1884
    mqtt_topic_prefix: str = "robots"
    # ZMQ 发布端口
    zmq_pub_port: int = 5555
    enable_zmq: bool = False

    # 默认机器人 ID（指令未指定 robot_id 时使用）
    default_robot_id: str = "car01"
    command_timeout_seconds: float = 10.0

    # 机器人订阅的 ROS2 话题（由 gateway 转发）
    robot_topics: list[str] = [
        "sdc/speed",
        "sdc/action_id",
        "sdc/front_distance",
        "sdc/obstacle_count",
        "simulation/markers",
        "sensor/lidar",
        "sdc/odometry",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
