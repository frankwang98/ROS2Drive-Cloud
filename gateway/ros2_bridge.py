# ROS2 ⇄ 消息总线桥接
"""
从 ros2_car 的 ROS2 话题订阅机器人状态，转换为统一 JSON 后，
通过 MQTT 与 ZMQ 发布到云端 Backend；同时订阅云端 command 指令，
转发为 ROS2 话题发布到机器人侧（下行控制）。

数据流（上行）：
    ROS2 topics (sdc/speed, sdc/action_id, ...)
        ↓ 订阅
    gateway 转换为统一 JSON
        ↓ 发布
    MQTT topic: robot/{robot_id}/{topic}
    ZMQ PUB :   tcp://*:{zmq_port}

数据流（下行）：
    MQTT topic: robot/{robot_id}/command/{cmd}
    ZMQ REP :   tcp://*:{zmq_port + 1}
        ↓ 订阅/接收
    gateway 解析指令并转换为 ROS2 消息
        ↓ 发布
    ROS2 topics (sdc/control_algo, sdc/pause, sdc/clear_trail)

运行前提：已 source ROS2 环境（source /opt/ros/humble/setup.bash）
用法：
    python3 ros2_bridge.py --robot-id car01
"""
import argparse
import json
import logging

logger = logging.getLogger("ros2_bridge")

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


# ros2_car 中需要桥接的 ROS2 话题（显示控制相关，上行）
TOPIC_SCHEMA = {
    # topic: (消息类型)
    "sdc/speed": "Float64",
    "sdc/action_id": "Float64",
    "sdc/front_distance": "Float64",
    "sdc/obstacle_count": "Float64",
    "simulation/markers": "MarkerArray",
    "sensor/lidar": "PointCloud2",
}

# 云端 command 主题 → 机器人侧 ROS2 话题（下行）
# key 为 command 主题后缀，value 为 (ROS2 话题, ROS2 消息类型, 是否要求带 value)
COMMAND_SCHEMA = {
    "control_algo": ("sdc/control_algo", "Int32", True),
    "pause": ("sdc/pause", "Bool", True),
    "clear_trail": ("sdc/clear_trail", "Bool", False),
}

# Backend /api/control 的 action 名 → command 主题后缀（扁平指令兼容）
ACTION_ALIAS = {
    "set_control_algo": "control_algo",
    "toggle_pause": "pause",
}


# ROS2 消息 → 简单 JSON 值的提取函数（上行）
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


# 简单 JSON 值 → ROS2 消息（下行）
def build_ros_msg(msg_type: str, value):
    """根据消息类型构造一个 ROS2 消息对象。

    返回的 msg 需在 main() 中通过 rclpy 构造并填充，这里返回 (msg_type, value)。
    """
    return msg_type, value


def parse_command_payload(payload: dict):
    """从总线上收到的指令 JSON 解析出 (command_key, value)。

    payload 支持两种形态：
      1) 统一消息模型：{"topic": ".../command/control_algo", "data": 2}
      2) 扁平指令：     {"action": "control_algo", "value": 2}
    """
    topic = payload.get("topic", "")
    if "/command/" in topic:
        cmd = topic.rsplit("/command/", 1)[-1]
    else:
        cmd = payload.get("action") or payload.get("command")
    value = payload.get("data", payload.get("value"))
    return cmd, value


class CommandForwarder:
    """下行指令转发器：将总线上的 command 指令转发到 ROS2 话题。"""

    def __init__(self, robot_id: str, ros_publishers: dict) -> None:
        """
        ros_publishers: { ros_topic: publisher } 由 main() 在 rclpy 环境下构造，
        用于发布下行 ROS2 消息。
        """
        self.robot_id = robot_id
        self.ros_publishers = ros_publishers

    def _publish_ros(self, ros_topic: str, msg_type: str, value) -> None:
        pub = self.ros_publishers.get(ros_topic)
        if pub is None:
            logger.warning("未找到 ROS2 发布器，忽略指令: %s", ros_topic)
            return
        # 根据消息类型构造 ROS2 消息
        from std_msgs.msg import Bool, Int32

        if msg_type == "Bool":
            msg = Bool()
            msg.data = bool(value)
        elif msg_type == "Int32":
            msg = Int32()
            msg.data = int(value)
        else:  # 兜底
            logger.warning("不支持的指令消息类型: %s", msg_type)
            return
        pub.publish(msg)
        logger.info("下行指令已转发到 ROS2: %s = %s", ros_topic, msg.data)

    def handle_command(self, command_topic: str, payload: dict) -> None:
        """处理一条来自总线的 command 指令。"""
        cmd, value = parse_command_payload(payload)
        if not cmd:
            logger.warning("无法解析指令主题: %s payload=%s", command_topic, payload)
            return

        # 兼容 Backend 的 action 名（set_control_algo/toggle_pause）
        cmd = ACTION_ALIAS.get(cmd, cmd)

        spec = COMMAND_SCHEMA.get(cmd)
        if spec is None:
            logger.warning("未知指令: %s（已支持: %s）", cmd, list(COMMAND_SCHEMA))
            return

        ros_topic, msg_type, require_value = spec
        if require_value and value is None:
            logger.warning("指令 %s 缺少 value", cmd)
            return
        if not require_value and value is None:
            # 例如 clear_trail 只发触发信号，默认 True
            value = True

        self._publish_ros(ros_topic, msg_type, value)


def build_bridge(robot_id: str, mqtt_broker: str, mqtt_port: int,
                 zmq_port: int, command_forwarder: CommandForwarder):
    """创建桥接回调（上行发布 + 下行订阅）。

    返回 (on_ros_topic, mqtt_client, zmq_pub, zmq_context, zmq_rep)
    """
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

    # ---- 上行：ROS2 话题 → 总线 ----
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

    # ---- 下行：总线 command → ROS2 话题 ----
    if mqtt_client is not None:
        # 订阅本机器人所有 command 主题
        command_topic = f"robot/{robot_id}/command/#"

        def on_command_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except Exception as e:  # noqa: BLE001
                logger.error("解析下行指令失败: %s", e)
                return
            logger.info("收到下行指令: %s -> %s", msg.topic, payload)
            command_forwarder.handle_command(msg.topic, payload)

        mqtt_client.message_callback_add(
            f"robot/{robot_id}/command/+", on_command_message
        )
        mqtt_client.subscribe(command_topic)
        logger.info("已订阅下行指令主题: %s", command_topic)

    zmq_rep = None
    if HAS_ZMQ:
        # ZMQ 下行通道使用 REP，监听 zmq_port + 1
        rep_port = zmq_port + 1
        zmq_rep = zmq_context.socket(zmq.REP)
        zmq_rep.bind(f"tcp://*:{rep_port}")

        def zmq_command_loop():
            logger.info("ZMQ 下行指令通道已监听: tcp://*:%d", rep_port)
            while True:
                try:
                    raw = zmq_rep.recv_string()
                    payload = json.loads(raw)
                    command_forwarder.handle_command("zmq/command", payload)
                    zmq_rep.send_string(json.dumps({"ok": True}))
                except Exception as e:  # noqa: BLE001
                    logger.error("ZMQ 下行指令处理失败: %s", e)
                    try:
                        zmq_rep.send_string(json.dumps({"ok": False, "error": str(e)}))
                    except Exception:  # noqa: BLE001
                        pass

        import threading
        threading.Thread(target=zmq_command_loop, daemon=True).start()

    return on_ros_topic, mqtt_client, zmq_pub, zmq_context, zmq_rep


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="ROS2 ⇄ MQTT/ZMQ 桥接（含下行控制）")
    parser.add_argument("--robot-id", default="car01", help="机器人 ID")
    parser.add_argument("--mqtt-broker", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1884)
    parser.add_argument("--zmq-port", type=int, default=5555)
    args = parser.parse_args()

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

    # ---- 下行：创建 ROS2 发布器（供 CommandForwarder 使用）----
    ros_publishers = {}
    for cmd, (ros_topic, msg_type, _) in COMMAND_SCHEMA.items():
        if ros_topic not in ros_publishers:
            ros_publishers[ros_topic] = node.create_publisher(
                TYPE_MAP[msg_type], ros_topic, 10
            )
            print(f"下行发布器: {ros_topic} ({msg_type})")

    command_forwarder = CommandForwarder(args.robot_id, ros_publishers)

    on_ros_topic, mqtt_client, zmq_pub, zmq_context, zmq_rep = build_bridge(
        args.robot_id, args.mqtt_broker, args.mqtt_port, args.zmq_port,
        command_forwarder,
    )

    # ---- 上行：订阅 ROS2 话题并转发到总线 ----
    subs = []
    for topic, msg_type in TOPIC_SCHEMA.items():
        cb = on_ros_topic(topic, msg_type)
        subs.append(
            node.create_subscription(TYPE_MAP[msg_type], topic, cb, 10)
        )
        print(f"桥接话题: {topic} ({msg_type})")

    print("Bridge 已启动，等待 ROS2 消息…")
    try:
        rclpy.spin(node)
    finally:
        if mqtt_client is not None:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        if zmq_rep is not None:
            zmq_rep.close()
        if zmq_pub is not None:
            zmq_pub.close()
        if zmq_context is not None:
            zmq_context.term()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
