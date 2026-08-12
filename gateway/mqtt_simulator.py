"""MQTT 模拟器。

在没有真实 ROS2 机器人环境时，向 MQTT broker 发送模拟的机器人状态数据，
用于验证 Backend → Web Dashboard 的完整链路。

数据模拟 ros2_car 的显示控制话题（sdc/speed, sdc/action_id, sdc/front_distance...）。
"""
import json
import random
import time

import paho.mqtt.client as mqtt

BROKER = "mqtt-broker"
PORT = 1884
TOPIC_PREFIX = "robot"
ROBOT_ID = "car01"

ACTIONS = {
    0: "加速",
    1: "巡航",
    2: "减速",
    3: "停车",
}


def publish_loop():
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    print(f"MQTT 模拟器已连接 {BROKER}:{PORT}")

    speed = 0.0
    while True:
        # 模拟速度变化（加速→巡航→减速→停车 循环）
        speed = (speed + 0.2) % 3.0
        action = random.choice(list(ACTIONS.keys()))
        front_distance = random.uniform(2.0, 12.0)

        samples = {
            "sdc/speed": round(speed, 2),
            "sdc/action_id": action,
            "sdc/front_distance": round(front_distance, 2),
            "sdc/obstacle_count": random.randint(0, 5),
            "simulation/markers": {"marker_count": random.randint(100, 200)},
            "sensor/lidar": {
                "width": 360,
                "height": 1,
                "point_step": 32,
            },
        }

        for topic, data in samples.items():
            payload = {
                "robot_id": ROBOT_ID,
                "topic": topic,
                "type": "simulated",
                "data": data,
            }
            client.publish(f"{TOPIC_PREFIX}/{ROBOT_ID}/{topic}", json.dumps(payload))
            print(f"→ {topic}: {data}")

        time.sleep(1.0)


if __name__ == "__main__":
    publish_loop()
