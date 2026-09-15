"""Running-stack E2E: telemetry + heartbeat + command + ACK."""
from __future__ import annotations

import json
import time
import urllib.request


BASE_URL = "http://localhost:8000"
ROBOT_ID = "car01"


def request(path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def wait_until(label: str, check, timeout: float = 15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = check()
        if value:
            print(f"PASS {label}")
            return value
        time.sleep(0.5)
    raise RuntimeError(f"TIMEOUT {label}")


def main() -> None:
    wait_until("backend health", lambda: request("/healthz").get("status") == "ok")

    robot = wait_until(
        "telemetry and heartbeat",
        lambda: (lambda value: value if value["connection"]["state"] == "ONLINE"
                  and "sdc/odometry" in value["telemetry"] else None)(
                      request(f"/api/v1/robots/{ROBOT_ID}")),
    )
    assert "pose" in robot["observed"]

    command = request(
        f"/api/v1/robots/{ROBOT_ID}/commands", "POST",
        {"action": "set_paused", "value": True},
    )
    assert command["status"] == "PUBLISHED", command
    command_id = command["command_id"]

    wait_until(
        "command ACK",
        lambda: (lambda value: value if value.get("status") == "SUCCEEDED" else None)(
            request(f"/api/v1/robots/{ROBOT_ID}/commands/{command_id}")),
    )
    print("E2E PASS: Web/API → Backend → MQTT → Vehicle → ACK → Backend")


if __name__ == "__main__":
    main()
