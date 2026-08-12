// Robot Cloud Platform Web Dashboard 前端逻辑
// WebSocket 实时推送 + 模式切换 + 地图/车辆/轨迹可视化

const WS_URL = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/robot";

const ACTIONS = { 0: "加速", 1: "巡航", 2: "减速", 3: "停车" };

const connEl = document.getElementById("conn-status");
const logEl = document.getElementById("log");
const modeBadge = document.getElementById("mode-badge");
const poseLine = document.getElementById("pose-line");

let ws = null;
let currentMode = "simulation";

// 地图状态
let pose = { x: 0, y: 0, heading: 0 };
let trail = [];
let obstacles = [];

// ---------- WebSocket 连接 ----------
function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    connEl.textContent = "已连接";
    connEl.className = "conn online";
    fetchMode();
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
    if (msg.topic === "_system/mode") {
      setModeUI(msg.data);
    }
  }
}

function applySnapshot(snap) {
  const topics = snap.topics || {};
  for (const [topic, item] of Object.entries(topics)) {
    applyTopic(topic, item.value);
  }
  if (snap.mode) setModeUI(snap.mode);
  if (snap.pose) {
    pose = snap.pose;
    updatePoseLine();
    drawMap();
  }
  if (Array.isArray(snap.trail)) {
    trail = snap.trail;
    drawMap();
  }
}

function applyTopic(topic, data) {
  // 位姿话题 -> 更新地图
  if (topic === "sdc/x" || topic === "pose/x" || topic === "odom/x") {
    pose.x = Number(data) || 0;
    updatePoseLine();
    drawMap();
  } else if (topic === "sdc/y" || topic === "pose/y" || topic === "odom/y") {
    pose.y = Number(data) || 0;
    updatePoseLine();
    drawMap();
  } else if (topic === "sdc/heading" || topic === "pose/heading") {
    pose.heading = Number(data) || 0;
    updatePoseLine();
    drawMap();
  } else if (topic === "sdc/obstacle_count") {
    obstacles = Array.from({ length: Number(data) || 0 }, () => ({
      x: (Math.random() - 0.5) * 14,
      y: (Math.random() - 0.5) * 14,
    }));
    drawMap();
  }

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

// ---------- 模式 ----------
function fetchMode() {
  fetch("/api/mode")
    .then((r) => r.json())
    .then((data) => {
      if (data.mode) setModeUI(data.mode);
    })
    .catch(() => {});
}

function setModeUI(mode) {
  currentMode = mode === "real" ? "real" : "simulation";
  modeBadge.textContent = currentMode === "real" ? "实车" : "仿真";
  modeBadge.className = "badge " + currentMode;
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === currentMode);
  });
}

function switchMode(mode) {
  fetch("/api/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        setModeUI(mode);
        logMessage("_system/mode", mode);
      }
    })
    .catch(() => {});
}

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchMode(btn.dataset.mode));
});

// ---------- 地图绘制 ----------
function updatePoseLine() {
  poseLine.textContent = `位置: (${pose.x.toFixed(2)}, ${pose.y.toFixed(2)}) / 朝向: ${((pose.heading * 180) / Math.PI).toFixed(0)}°`;
}

function drawMap() {
  const canvas = document.getElementById("map-canvas");
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const half = W / 2;

  // 背景
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(0, 0, W, H);

  // 网格（20x20 地图，每格 1m -> 画布 20 格）
  const cellPx = W / 20;
  ctx.strokeStyle = "#1e293b";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 20; i++) {
    ctx.beginPath();
    ctx.moveTo(i * cellPx, 0);
    ctx.lineTo(i * cellPx, H);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, i * cellPx);
    ctx.lineTo(W, i * cellPx);
    ctx.stroke();
  }

  // 坐标轴
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(half, 0);
  ctx.lineTo(half, H);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(0, half);
  ctx.lineTo(W, half);
  ctx.stroke();

  // 障碍物（红色方块）
  ctx.fillStyle = "#ef4444";
  obstacles.forEach((o) => {
    ctx.fillRect(half + o.x * cellPx - 4, half - o.y * cellPx - 4, 8, 8);
  });

  // 轨迹（青色线）
  if (trail.length > 1) {
    ctx.strokeStyle = "#22d3ee";
    ctx.lineWidth = 2;
    ctx.beginPath();
    trail.forEach((p, i) => {
      const px = half + p[0] * cellPx;
      const py = half - p[1] * cellPx;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }

  // 车辆（蓝色圆 + 朝向箭头）
  const cx = half + pose.x * cellPx;
  const cy = half - pose.y * cellPx;
  ctx.fillStyle = "#38bdf8";
  ctx.beginPath();
  ctx.arc(cx, cy, 9, 0, Math.PI * 2);
  ctx.fill();
  // 外圈
  ctx.strokeStyle = "#0ea5e9";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, 14, 0, Math.PI * 2);
  ctx.stroke();
  // 朝向箭头
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 3;
  ctx.beginPath();
  const len = 18;
  const hx = cx + Math.cos(pose.heading) * len;
  const hy = cy - Math.sin(pose.heading) * len;
  ctx.moveTo(cx, cy);
  ctx.lineTo(hx, hy);
  ctx.stroke();

  // 车中心点
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.arc(cx, cy, 3, 0, Math.PI * 2);
  ctx.fill();
}

// 窗口尺寸自适应
function resizeMap() {
  const canvas = document.getElementById("map-canvas");
  const card = document.getElementById("map-card");
  const size = Math.max(320, card.clientWidth - 42);
  canvas.width = size;
  canvas.height = size;
  drawMap();
}
window.addEventListener("resize", resizeMap);

// ---------- 远程控制 ----------
function sendControl(action, payload) {
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
window.addEventListener("load", resizeMap);
