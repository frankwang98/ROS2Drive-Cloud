// Robot Cloud Platform Web Dashboard 前端逻辑
// 通过 WebSocket 连接后端，实时展示机器人状态 + 远程控制

const WS_URL = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/robot";

const ACTIONS = { 0: "加速", 1: "巡航", 2: "减速", 3: "停车" };

const connEl = document.getElementById("conn-status");
const logEl = document.getElementById("log");

let ws = null;

// ---------- WebSocket 连接 ----------
function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    connEl.textContent = "已连接";
    connEl.className = "conn online";
  };

  ws.onclose = () => {
    connEl.textContent = "已断开，重连中…";
    connEl.className = "conn offline";
    setTimeout(connect, 3000);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch (e) {
      console.error("解析消息失败", e);
    }
  };
}

function handleMessage(msg) {
  if (msg.type === "snapshot") {
    applySnapshot(msg.data);
    return;
  }
  if (msg.type === "update") {
    applyTopic(msg.topic, msg.data);
    logMessage(msg.topic, msg.data);
  }
}

function applySnapshot(snap) {
  const topics = snap.topics || {};
  for (const [topic, item] of Object.entries(topics)) {
    applyTopic(topic, item.value);
  }
}

function applyTopic(topic, data) {
  const el = document.getElementById(selectorFor(topic));
  if (!el) return;

  if (topic === "sdc/speed") {
    el.textContent = Number(data).toFixed(2);
    const pct = Math.min(100, (Number(data) / 3) * 100);
    document.getElementById("speed-fill").style.width = pct + "%";
  } else if (topic === "sdc/action_id") {
    el.textContent = ACTIONS[data] || data;
  } else {
    el.textContent = data;
  }
}

function selectorFor(topic) {
  switch (topic) {
    case "sdc/speed": return "speed";
    case "sdc/action_id": return "action";
    case "sdc/front_distance": return "front-distance";
    case "sdc/obstacle_count": return "obstacle-count";
    default: return null;
  }
}

function logMessage(topic, data) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="topic">${topic}</span>: ${JSON.stringify(data)}`;
  logEl.prepend(li);
  while (logEl.children.length > 20) logEl.removeChild(logEl.lastChild);
}

// ---------- 远程控制 ----------
function sendControl(action, payload) {
  // 通过 REST 下发控制指令（可扩展为发布到机器人侧）
  fetch("/api/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...payload }),
  });
}

function sendAlgo() {
  const algo = document.getElementById("algo-select").value;
  sendControl("set_control_algo", { value: Number(algo) });
}

function togglePause() {
  const btn = document.getElementById("pause-btn");
  const paused = btn.dataset.paused === "true";
  sendControl("toggle_pause", {});
  btn.dataset.paused = String(!paused);
  btn.textContent = paused ? "暂停仿真" : "继续仿真";
}

function clearTrail() {
  sendControl("clear_trail", {});
}

// 启动
connect();
