"""ROS2 ⇄ MQTT/ZMQ 桥接层。

作用：连接 ros2_car 机器人（ROS2 话题）与云端消息总线（MQTT/ZMQ）。

数据流：
  ROS2 topics (sdc/speed, sdc/action_id, ...)
      ↓ 订阅
  gateway 将消息转换为统一 JSON
      ↓ 发布
  MQTT topic: robot/{robot_id}/sdc/speed
  ZMQ PUB :   tcp://*:5555

可在机器人侧（宿主机或同网段容器）运行，也可作为 sidecar 部署。
"""
