(function () {
  "use strict";

  const tilesEl = document.getElementById("tiles");
  const siteBanner = document.getElementById("site-banner");
  const canaryState = document.getElementById("canary-state");
  const connBanner = document.getElementById("conn-banner");
  const clockEl = document.getElementById("clock");
  const eventsBody = document.querySelector("#events-table tbody");

  let ws = null;
  let pollTimer = null;
  let chart = null;
  const chartColors = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24"];

  function fmtIST(epochSeconds) {
    if (!epochSeconds) return "-";
    return new Date(epochSeconds * 1000).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  }

  function stateClass(state, muted) {
    if (muted) return "muted";
    return (state || "unknown").toLowerCase();
  }

  function renderStatus(data) {
    siteBanner.textContent = data.site_state === "SITE_ISOLATED" ? "SITE ISOLATED" : "All monitored";
    siteBanner.className = "site-banner " + (data.site_state === "SITE_ISOLATED" ? "isolated" : "ok");

    canaryState.textContent = data.canaries_ok ? "OK" : "DOWN (monitor may be offline)";
    canaryState.className = data.canaries_ok ? "good" : "bad";

    tilesEl.innerHTML = "";
    for (const t of data.targets) {
      const cls = stateClass(t.state, t.muted);
      const tile = document.createElement("div");
      tile.className = "tile " + cls;
      tile.innerHTML =
        '<div class="tile-title">' + t.hostname + "</div>" +
        '<div class="tile-ip">' + t.ip + "</div>" +
        '<div class="tile-state ' + cls + '">' + (t.muted ? "MUTED" : t.state) + "</div>" +
        '<div class="tile-metrics">' +
        "rtt: " + (t.rtt_avg != null ? t.rtt_avg.toFixed(0) + "ms" : "n/a") + "<br>" +
        "loss: " + (t.loss_pct != null ? t.loss_pct.toFixed(0) + "%" : "n/a") + "<br>" +
        "last change: " + fmtIST(t.last_change_ts) +
        (t.muted ? "<br>muted until: " + fmtIST(t.muted_until) : "") +
        "</div>" +
        '<button class="mute-btn" data-target="' + t.id + '" data-muted="' + t.muted + '">' +
        (t.muted ? "Unmute" : "Mute 1h") + "</button>";
      tilesEl.appendChild(tile);
    }
  }

  async function toggleMute(targetId, currentlyMuted) {
    const url = "/api/targets/" + encodeURIComponent(targetId) + "/mute";
    if (currentlyMuted) {
      await fetch(url, { method: "DELETE" });
    } else {
      await fetch(url + "?minutes=60", { method: "POST" });
    }
  }

  tilesEl.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".mute-btn");
    if (!btn) return;
    toggleMute(btn.dataset.target, btn.dataset.muted === "true");
  });

  function renderEvents(events) {
    eventsBody.innerHTML = "";
    for (const e of events) {
      const row = document.createElement("tr");
      row.innerHTML =
        "<td>" + fmtIST(e.ts) + "</td><td>" + e.target_id + "</td>" +
        "<td>" + e.from_state + " -&gt; " + e.to_state + "</td><td>" + (e.reason || "") + "</td>";
      eventsBody.appendChild(row);
    }
  }

  async function refreshEvents() {
    try {
      const resp = await fetch("/api/events?limit=50");
      renderEvents(await resp.json());
    } catch (e) { /* ignore, next tick retries */ }
  }

  async function refreshChart(targetIds) {
    if (!chart) return;
    for (let i = 0; i < targetIds.length; i++) {
      try {
        const resp = await fetch("/api/history?target=" + encodeURIComponent(targetIds[i]) + "&range=1h");
        const rows = await resp.json();
        chart.data.datasets[i].data = rows.map((r) => ({ x: r.ts * 1000, y: r.rtt_avg }));
      } catch (e) { /* ignore */ }
    }
    chart.update("none");
  }

  function initChart(targetIds) {
    const ctx = document.getElementById("rtt-chart").getContext("2d");
    chart = new Chart(ctx, {
      type: "line",
      data: {
        datasets: targetIds.map((id, i) => ({
          label: id, data: [], borderColor: chartColors[i % chartColors.length],
          borderWidth: 2, pointRadius: 0, tension: 0.2,
        })),
      },
      options: {
        animation: false,
        scales: {
          x: {
            type: "linear",
            ticks: {
              color: "#8b98a5",
              callback: (v) => new Date(v).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }),
            },
            grid: { color: "#232d38" },
          },
          y: { title: { display: true, text: "ms", color: "#8b98a5" }, ticks: { color: "#8b98a5" }, grid: { color: "#232d38" } },
        },
        plugins: { legend: { labels: { color: "#e6edf3" } } },
      },
    });
  }

  function showConnBanner(show) {
    connBanner.classList.toggle("hidden", !show);
  }

  function updateChart(data) {
    const targetIds = data.targets.map((t) => t.id);
    if (!chart) initChart(targetIds);
    refreshChart(targetIds);
  }

  function startPolling() {
    if (pollTimer) return;
    showConnBanner(true);
    pollTimer = setInterval(async () => {
      try {
        const resp = await fetch("/api/status");
        const data = await resp.json();
        renderStatus(data);
        updateChart(data);
      } catch (e) { /* keep polling */ }
    }, 5000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    showConnBanner(false);
  }

  function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(proto + "//" + location.host + "/ws");

    ws.onopen = () => stopPolling();
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      renderStatus(data);
      updateChart(data);
    };
    ws.onclose = () => { startPolling(); setTimeout(connectWS, 5000); };
    ws.onerror = () => ws.close();
  }

  document.getElementById("test-alert-btn").addEventListener("click", async () => {
    const resultEl = document.getElementById("test-alert-result");
    resultEl.textContent = "Sending...";
    try {
      const resp = await fetch("/api/alerts/test", { method: "POST" });
      const data = await resp.json();
      resultEl.textContent = Object.entries(data).map(([k, v]) => k + ":" + (v ? "OK" : "fail")).join(" ");
    } catch (e) {
      resultEl.textContent = "request failed";
    }
  });

  setInterval(() => {
    clockEl.textContent = new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " IST";
  }, 1000);

  setInterval(refreshEvents, 15000);
  refreshEvents();
  connectWS();
})();
