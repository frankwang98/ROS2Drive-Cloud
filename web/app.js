const ROBOT_ID = "car01";
const ACTIONS = { 0: "加速", 1: "巡航", 2: "减速", 3: "停车" };
const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/v1/robots/${ROBOT_ID}`;

const telemetry = new Map();
let reconnectTimer;
let paused = false;

const byId = (id) => document.getElementById(id);
const number = (value, digits = 2) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "--";

function setText(id, value) { byId(id).textContent = value; }

function connect() {
  clearTimeout(reconnectTimer);
  const ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    byId("ws-dot").classList.add("online");
    setText("ws-status", "云端已连接");
  };
  ws.onclose = () => {
    byId("ws-dot").classList.remove("online");
    setText("ws-status", "云端断开，正在重连");
    reconnectTimer = setTimeout(connect, 3000);
  };
  ws.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.type === "snapshot") applySnapshot(message.data);
    if (message.type === "telemetry") applyTelemetry(message.data.name, message.data.value, new Date());
    if (message.type === "heartbeat") updateConnection("ONLINE", message.data.last_seen);
    if (message.type === "command_ack") showCommand(message.data);
  };
}

function applySnapshot(snapshot) {
  updateConnection(snapshot.connection?.state, snapshot.connection?.last_seen);
  Object.entries(snapshot.telemetry || {}).forEach(([name, item]) => {
    applyTelemetry(name, item.value, new Date(item.ts * 1000));
  });
  setText("trail-count", (snapshot.trail || []).length);
}

function updateConnection(state = "OFFLINE", lastSeen) {
  const online = state === "ONLINE";
  setText("robot-status", online ? "ONLINE" : "OFFLINE");
  byId("robot-status").className = online ? "online-text" : "offline";
  setText("last-seen", lastSeen ? new Date(lastSeen * 1000).toLocaleTimeString() : "--");
}

function applyTelemetry(name, value, timestamp) {
  telemetry.set(name, { value, timestamp });
  setText("message-status", `已收到 ${telemetry.size} 类数据`);
  if (name === "sdc/speed") setText("speed", number(value));
  if (name === "sdc/action_id") setText("action", ACTIONS[value] ?? value);
  if (name === "sdc/front_distance") setText("front-distance", number(value));
  if (name === "sdc/obstacle_count") setText("obstacle-count", number(value, 0));
  if (name === "sdc/odometry" && value?.pose) {
    setText("pose-x", number(value.pose.x));
    setText("pose-y", number(value.pose.y));
    setText("pose-yaw", `${number(value.pose.yaw)} rad`);
    setText("linear-velocity", `${number(value.velocity?.linear)} m/s`);
    setText("angular-velocity", `${number(value.velocity?.angular)} rad/s`);
  }
  renderTelemetry();
}

function renderTelemetry() {
  const body = byId("telemetry-body");
  body.replaceChildren(...Array.from(telemetry.entries()).map(([name, item]) => {
    const row = document.createElement("tr");
    [name, JSON.stringify(item.value), item.timestamp.toLocaleTimeString()].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
    return row;
  }));
}

async function sendCommand(action, value) {
  const response = await fetch(`/api/v1/robots/${ROBOT_ID}/commands`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, value }),
  });
  const result = await response.json();
  showCommand(result);
  return result;
}

function showCommand(result) {
  const id = result.command_id || result.message_id || "--";
  setText("command-result", `${result.status || "UNKNOWN"} · ${id}`);
}

byId("algo-btn").onclick = () => sendCommand("set_control_algo", Number(byId("algo-select").value));
byId("pause-btn").onclick = async () => {
  const result = await sendCommand("set_paused", !paused);
  if (result.status === "PUBLISHED") {
    paused = !paused;
    setText("pause-btn", paused ? "恢复车辆" : "暂停车辆");
  }
};
byId("clear-btn").onclick = () => sendCommand("clear_trail", true);

connect();

