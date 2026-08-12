# ROS2 ⇄ 消息总线桥接
"""
从 ros2_car 的 ROS2 话题订阅机器人状态，转换为统一 JSON 后，
通过 MQTT 与 ZMQ 发布到云端 Backend。

运行前提：已 source ROS2 环境（source /opt/ros/humble/setup.bash）
用法：
    python3 ros2_bridge.py --robot-id car01
"""
import argparse
import json
import threading

# 可选依赖：paho-mqtt、pyzmq（缺省时对应通道自动禁用）
try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:  # pragma: no cover
    HAS_MQTT = False

try:
    import zmq
    HAS_ZMQ = True
except ImportError:  # pragma: no cover
    HAS_ZMQ = False


# ros2_car 中需要桥接的 ROS2 话题（显示控制相关）
TOPIC_SCHEMA = {
    # topic: (消息类型, 取值字段)
    "sdc/speed": "Float64",
    "sdc/action_id": "Float64",
    "sdc/front_distance": "Float64",
    "sdc/obstacle_count": "Float64",
    "simulation/markers": "MarkerArray",
    "sensor/lidar": "PointCloud2",
}

# ROS2 消息 → 简单 JSON 值的提取函数
def extract_value(msg, msg_type: str):
    """将 ROS2 消息转换为可 JSON 序列化的简单值。"""
    if msg_type in ("Float64", "Int32", "Bool"):
        return getattr(msg, "data", None)
    if msg_type == "MarkerArray":
        return {"marker_count": len(msg.markers) if msg.markers else 0}
    if msg_type == "PointCloud2":
        return {
            "width": getattr(msg, "width", 0),
            "height": getattr(msg, "height", 0),
            "point_step": getattr(msg, "point_step", 0),
        }
    return str(msg)


def build_bridge(robot_id: str, mqtt_broker: str, mqtt_port: int, zmq_port: int):
    """创建桥接回调。"""
    if not HAS_MQTT and not HAS_ZMQ:
        raise RuntimeError("需要安装 paho-mqtt 或 pyzmq 之一")

    mqtt_client = None
    if HAS_MQTT:
        mqtt_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        mqtt_client.connect(mqtt_broker, mqtt_port, 60)
        mqtt_client.loop_start()

    zmq_pub = None
    zmq_context = None
    if HAS_ZMQ:
        zmq_context = zmq.Context()
        zmq_pub = zmq_context.socket(zmq.PUB)
        zmq_pub.bind(f"tcp://*:{zmq_port}")

    def on_ros_topic(topic: str, msg_type: str):
        def callback(msg):
            payload = {
                "robot_id": robot_id,
                "topic": topic,
                "type": msg_type,
                "data": extract_value(msg, msg_type),
            }
            text = json.dumps(payload)
            # 发布到 MQTT
            if mqtt_client is not None:
                mqtt_client.publish(f"robot/{robot_id}/{topic}", text)
            # 发布到 ZMQ（topic 帧 + payload 帧）
            if zmq_pub is not None:
                zmq_pub.send_string(f"robot/{robot_id}/{topic}", zmq.SNDMORE)
                zmq_pub.send_string(text)
        return callback

    return on_ros_topic, mqtt_client, zmq_pub, zmq_context


def main():
    parser = argparse.ArgumentParser(description="ROS2 ⇄ MQTT/ZMQ 桥接")
    parser.add_argument("--robot-id", default="car01", help="机器人 ID")
    parser.add_argument("--mqtt-broker", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--zmq-port", type=int, default=5555)
    args = parser.parse_args()

    on_ros_topic, mqtt_client, zmq_pub, zmq_context = build_bridge(
        args.robot_id, args.mqtt_broker, args.mqtt_port, args.zmq_port
    )

    # 动态导入 ROS2（避免无 ROS2 环境下 import 失败）
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Float64, Int32, Bool
    from visualization_msgs.msg import MarkerArray
    from sensor_msgs.msg import PointCloud2

    rclpy.init()
    node = Node(f"robot_bridge_{args.robot_id}")

    TYPE_MAP = {
        "Float64": Float64,
        "Int32": Int32,
        "Bool": Bool,
        "MarkerArray": MarkerArray,
        "PointCloud2": PointCloud2,
    }

    subs = []
    for topic, msg_type in TOPIC_SCHEMA.items():
        cb = on_ros_topic(topic, msg_type)
        subs.append(
            node.create_subscription(TYPE_MAP[msg_type], topic, cb, 10)
        )
        print(f"桥接话题: {topic} ({msg_type})")

    print("Bridge 已启动，等待 ROS2 消息…")
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
