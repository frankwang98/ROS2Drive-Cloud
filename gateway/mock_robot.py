"""Mock 机器人（下行验证工具）。

在没有真实 ROS2 / ros2_car 环境下，模拟机器人侧订阅消息总线上的 command 指令，
用于验证「云端 Backend → MQTT/ZMQ → 机器人侧」的下行链路是否打通。

真实部署中，下行链路为：
    Backend --publish--> MQTT command --subscribe--> gateway --publish ROS2--> ros2_car
本工具直接订阅 MQTT command 主题，等效于验证指令能到达机器人侧。

用法：
    python3 mock_robot.py --mqtt-broker localhost --mqtt-port 1884 [--robot-id car01]
"""
import argparse
import json
import logging

import paho.mqtt.client as mqtt
from robot_contracts import CommandStatus, MessageType, envelope, parse_envelope

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock_robot")


def main():
    parser = argparse.ArgumentParser(description="Mock 机器人（下行指令监听）")
    parser.add_argument("--mqtt-broker", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--robot-id", default="car01")
    args = parser.parse_args()

    topic = f"robots/{args.robot_id}/commands"
    sequence = 0
    logger.info("Mock 机器人订阅下行指令: %s (%s:%s)",
                topic, args.mqtt_broker, args.mqtt_port)

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(client, userdata, flags, reason_code, properties=None):
        rc = getattr(reason_code, "value", reason_code)
        logger.info("已连接 MQTT, rc=%s，订阅 %s", rc, topic)
        client.subscribe(topic)

    def on_message(client, userdata, msg):
        nonlocal sequence
        try:
            message = parse_envelope(json.loads(msg.payload.decode("utf-8")))
        except Exception:  # noqa: BLE001
            logger.info("[收到原始指令] %s -> %s", msg.topic, msg.payload.decode())
            return
        logger.info("[收到下行指令] %s -> action=%s value=%s",
                    msg.topic, message["payload"].get("action"), message["payload"].get("value"))
        sequence += 1
        ack = envelope(args.robot_id, MessageType.COMMAND_ACK, {
            "command_id": message["message_id"],
            "status": CommandStatus.SUCCEEDED.value,
            "detail": "mock robot accepted command",
        }, sequence=sequence)
        client.publish(f"robots/{args.robot_id}/command_ack", json.dumps(ack), qos=1)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.mqtt_broker, args.mqtt_port, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
