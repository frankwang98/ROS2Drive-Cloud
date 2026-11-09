# Native C++ ↔ Cloud MQTT integration

This adapter runs **the ROS2Drive C++ SimulationEngine**, not a second Python simulator.
It sends live pose, runtime status, trajectory, mission feedback and heartbeat through
the existing Cloud MQTT v2 envelopes. Cloud's existing FastAPI and Dashboard consume
those topics. Navigation requests travel in the opposite direction via the existing
POST /api/v2/robots/{robot_id}/missions endpoint.

## Start (trusted local machine/network)

1. Build ROS2Drive branch feat/cross-platform-studio:

       cmake -S ../ROS2Drive/native -B ../ROS2Drive/build-native
       cmake --build ../ROS2Drive/build-native -j

2. Start Cloud broker/backend with bash scripts/run_cloud.sh.
3. Install the bridge's dependency: python3 -m pip install paho-mqtt
4. From ROS2Drive-Cloud root run:

       python3 gateway/native_runtime_bridge.py \
         --runner ../ROS2Drive/build-native/ros2drive_live \
         --broker 127.0.0.1 --port 1884 --robot-id car01 \
         --scenario port_transport

5. Open http://localhost:8000/dashboard/ , choose connected mode, backend
   http://localhost:8000 and robot car01. Dispatch a FollowRoute mission.

No ROS2 is required for this native mode. The bridge owns the subprocess and
serializes its commands through stdin. C++ continues to own simulation, planning
and control. This is a local development adapter, not a safety-certified remote
control system. Keep MQTT and the HTTP control API on a trusted network; enable
authentication/TLS before any external deployment.

Known limitations: navigation and cancellation use the C++ mission manager, but
Cloud scene maps are not automatically synchronized with native scenario geometry.
Select matching scenario/routes; pause and emergency stop are supported by the
native engine. End-to-end broker/browser verification is still required.
