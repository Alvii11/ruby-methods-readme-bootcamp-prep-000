"use strict";

const POLL_MS = 2000;
let logTarget = null; // bot id whose logs the modal is showing

async function api(path, method = "GET") {
  const res = await fetch(path, { method });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${body}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function fmtUptime(s) {
  if (s == null) return "—";
  s = Math.floor(s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function renderCard(bot) {
  const card = el("div", "card");

  const top = el("div", "card-top");
  const left = el("div");
  left.appendChild(el("div", "card-name", bot.name));
  if (bot.description) left.appendChild(el("div", "card-desc", bot.description));
  top.appendChild(left);
  top.appendChild(el("span", `badge ${bot.status}`, bot.status));
  card.appendChild(top);

  card.appendChild(el("div", "card-cmd", bot.command));

  const metrics = el("div", "metrics");
  const running = bot.status === "running";
  metrics.innerHTML =
    `<span>pid <b>${bot.pid ?? "—"}</b></span>` +
    `<span>up <b>${fmtUptime(bot.uptime)}</b></span>` +
    `<span>cpu <b>${running && bot.cpu != null ? bot.cpu + "%" : "—"}</b></span>` +
    `<span>mem <b>${running && bot.mem_mb != null ? bot.mem_mb + "MB" : "—"}</b></span>` +
    `<span>restarts <b>${bot.restarts}</b></span>` +
    (bot.exit_code != null && !running ? `<span>exit <b>${bot.exit_code}</b></span>` : "");
  card.appendChild(metrics);

  const actions = el("div", "card-actions");
  const startBtn = el("button", "start", running ? "Restart" : "Start");
  startBtn.onclick = () => act(running ? "restart" : "start", bot.id);
  const stopBtn = el("button", "stop", "Stop");
  stopBtn.disabled = !running;
  stopBtn.onclick = () => act("stop", bot.id);
  const logBtn = el("button", "logs", "Logs");
  logBtn.onclick = () => openLogs(bot.id, bot.name);
  actions.append(startBtn, stopBtn, logBtn);
  card.appendChild(actions);

  return card;
}

async function act(action, botId) {
  try {
    await api(`/api/bots/${encodeURIComponent(botId)}/${action}`, "POST");
    await refresh();
  } catch (e) {
    setStatus(`error: ${e.message}`, true);
  }
}

async function groupAct(action, group) {
  try {
    await api(`/api/groups/${encodeURIComponent(group)}/${action}`, "POST");
    await refresh();
  } catch (e) {
    setStatus(`error: ${e.message}`, true);
  }
}

function renderSystem(sys) {
  const load = (sys.load || []).map((x) => (x == null ? "—" : x.toFixed(2))).join(" ");
  document.getElementById("sys").innerHTML =
    `<span>CPU <b>${sys.cpu_percent}%</b> (${sys.cpu_count} cores)</span>` +
    `<span>load <b>${load}</b></span>` +
    `<span>mem <b>${sys.mem_percent}%</b> (${sys.mem_used_gb}/${sys.mem_total_gb}GB)</span>` +
    `<span>disk <b>${sys.disk_percent}%</b></span>` +
    `<span>up <b>${sys.uptime_hours}h</b></span>`;
}

function renderGroups(data) {
  const root = document.getElementById("groups");
  root.innerHTML = "";
  for (const group of data.groups) {
    const bots = data.bots.filter((b) => b.group === group);
    const section = el("div", "group");

    const head = el("div", "group-head");
    head.appendChild(el("h2", null, group));
    const ga = el("div", "group-actions");
    const startAll = el("button", null, "Start all");
    startAll.onclick = () => groupAct("start", group);
    const stopAll = el("button", null, "Stop all");
    stopAll.onclick = () => groupAct("stop", group);
    ga.append(startAll, stopAll);
    head.appendChild(ga);
    section.appendChild(head);

    const cards = el("div", "cards");
    bots.forEach((b) => cards.appendChild(renderCard(b)));
    section.appendChild(cards);
    root.appendChild(section);
  }
}

async function refresh() {
  try {
    const [bots, sys] = await Promise.all([api("/api/bots"), api("/api/system")]);
    renderSystem(sys);
    renderGroups(bots);
    const running = bots.bots.filter((b) => b.status === "running").length;
    setStatus(`${running}/${bots.bots.length} running · updated ${new Date().toLocaleTimeString()}`);
  } catch (e) {
    setStatus(`disconnected: ${e.message}`, true);
  }
}

function setStatus(msg, isErr) {
  const line = document.getElementById("status-line");
  line.textContent = msg;
  line.style.color = isErr ? "#ff8378" : "";
}

// -- log modal --------------------------------------------------------------

function openLogs(botId, name) {
  logTarget = botId;
  document.getElementById("modal-title").textContent = `Logs · ${name}`;
  document.getElementById("modal").classList.remove("hidden");
  refreshLogs();
}
function closeLogs() {
  logTarget = null;
  document.getElementById("modal").classList.add("hidden");
}
async function refreshLogs() {
  if (!logTarget) return;
  try {
    const txt = await api(`/api/bots/${encodeURIComponent(logTarget)}/logs?lines=400`);
    const pre = document.getElementById("modal-logs");
    const follow = document.getElementById("log-follow").checked;
    pre.textContent = txt || "(no output yet)";
    if (follow) pre.scrollTop = pre.scrollHeight;
  } catch (e) {
    document.getElementById("modal-logs").textContent = `error: ${e.message}`;
  }
}

document.getElementById("modal-close").onclick = closeLogs;
document.getElementById("modal").onclick = (e) => {
  if (e.target.id === "modal") closeLogs();
};

// -- auth -------------------------------------------------------------------

async function initAuth() {
  try {
    const info = await api("/api/auth");
    if (info.enabled) {
      const btn = document.getElementById("logout-btn");
      btn.classList.remove("hidden");
      btn.onclick = async () => {
        await api("/api/logout", "POST").catch(() => {});
        window.location.href = "/login.html";
      };
    }
  } catch (e) {
    // 401 here means the session expired — bounce to login.
    if (String(e.message).startsWith("401")) window.location.href = "/login.html";
  }
}

// If any poll returns 401 (session expired), send the user back to login.
const _api = api;
api = async function (path, method) {
  try {
    return await _api(path, method);
  } catch (e) {
    if (String(e.message).startsWith("401")) window.location.href = "/login.html";
    throw e;
  }
};

async function initAlerts() {
  try {
    const info = await api("/api/alerts");
    const btn = document.getElementById("test-alert-btn");
    if (info.enabled && info.channels.length) {
      btn.classList.remove("hidden");
      btn.title = `channels: ${info.channels.join(", ")}`;
      btn.onclick = async () => {
        btn.disabled = true;
        try {
          await api("/api/alerts/test", "POST");
          setStatus(`test alert sent via ${info.channels.join(", ")}`);
        } catch (e) {
          setStatus(`alert test failed: ${e.message}`, true);
        } finally {
          btn.disabled = false;
        }
      };
    }
  } catch (e) {
    /* alerts unknown — leave button hidden */
  }
}

initAuth();
initAlerts();
setInterval(refresh, POLL_MS);
setInterval(refreshLogs, POLL_MS);
refresh();
