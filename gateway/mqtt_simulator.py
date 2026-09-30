"""MQTT 模拟器（仿真模式数据源）。

在没有真实 ROS2 机器人环境时，向 MQTT broker 发送模拟的机器人状态数据，
用于验证 Backend → Web Dashboard 的完整链路，并驱动地图上的车/轨迹运动。

仿真模式：`python3 mqtt_simulator.py --mode simulation`
实车模式下的数据由 gateway/ros2_bridge.py 提供（本脚本不参与）。
"""
import argparse
import json
import math
import random
import time

import paho.mqtt.client as mqtt
from robot_contracts import MessageType, envelope

TOPIC_PREFIX = "robot"
ROBOT_ID = "car01"

ACTIONS = {
    0: "加速",
    1: "巡航",
    2: "减速",
    3: "停车",
}


def publish_loop(broker: str, port: int, mode: str, robot_id: str = ROBOT_ID):
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(broker, port, 60)
    client.loop_start()
    print(f"MQTT 模拟器已连接 {broker}:{port}  (mode={mode}, robot={robot_id})")

    speed = 0.0
    # 仿真小车在 20x20 地图上绕圈运动
    x, y = 0.0, 0.0
    heading = 0.0
    step = 0
    sequence = 0
    while True:
        # 模拟速度变化（加速→巡航→减速→停车 循环）
        speed = (speed + 0.2) % 3.0
        action = random.choice(list(ACTIONS.keys()))
        front_distance = random.uniform(2.0, 12.0)

        # 绕圈轨迹：半径 7m，圆心 (0,0)，顺时针
        step += 1
        angle = step * 0.05
        x = 7.0 * math.cos(angle)
        y = 7.0 * math.sin(angle)
        heading = angle + math.pi / 2  # 车头沿切线方向

        samples = {
            "sdc/speed": round(speed, 2),
            "sdc/action_id": action,
            "sdc/front_distance": round(front_distance, 2),
            "sdc/obstacle_count": random.randint(0, 5),
            "sdc/odometry": {
                "pose": {"x": round(x, 2), "y": round(y, 2), "yaw": round(heading, 3)},
                "velocity": {"linear": round(speed, 2), "angular": 0.0},
            },
            "simulation/markers": {"marker_count": random.randint(100, 200)},
            "sensor/lidar": {
                "width": 360,
                "height": 1,
                "point_step": 32,
            },
        }

        for topic, data in samples.items():
            sequence += 1
            payload = envelope(robot_id, MessageType.TELEMETRY, {
                "name": topic, "source": mode, "value": data,
            }, sequence=sequence)
            client.publish(f"robots/{robot_id}/telemetry", json.dumps(payload))
            print(f"→ {topic}: {data}")

        sequence += 1
        heartbeat = envelope(robot_id, MessageType.HEARTBEAT, {}, sequence=sequence)
        client.publish(f"robots/{robot_id}/heartbeat", json.dumps(heartbeat), qos=1)

        time.sleep(1.0)


def main():
    parser = argparse.ArgumentParser(description="MQTT 仿真模拟器（仿真模式数据源）")
    parser.add_argument("--mqtt-broker", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--robot-id", default=ROBOT_ID)
    parser.add_argument("--mode", default="simulation",
                        help="数据模式标识：simulation（仿真）")
    args = parser.parse_args()
    publish_loop(args.mqtt_broker, args.mqtt_port, args.mode, args.robot_id)


if __name__ == "__main__":
    main()

