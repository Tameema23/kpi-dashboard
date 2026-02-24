/* ================= CONFIRM / ALERT DIALOGS ================= */

function showConfirm(message, onConfirm, options) {
  options = options || {};
  var confirmText = options.confirmText || "Confirm";
  var cancelText  = options.cancelText  || "Cancel";
  var danger      = options.danger !== false;

  var existing = document.getElementById("_cfModal");
  if (existing) existing.remove();

  var iconHtml = danger
    ? '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>'
    : '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
  var iconBg  = danger ? "#fff1f2" : "#eff6ff";
  var btnBg   = danger ? "#dc2626" : "#2563eb";
  var title   = danger ? "Confirm Delete" : "Are you sure?";
  var btnIcon = danger ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>' : "";

  var backdrop = document.createElement("div");
  backdrop.id = "_cfModal";
  backdrop.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,0.45);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;padding:16px;";
  backdrop.innerHTML =
    "<div style='background:#fff;border-radius:18px;width:100%;max-width:400px;box-shadow:0 20px 60px rgba(15,23,42,0.22);animation:_cfIn 0.18s ease;overflow:hidden;'>" +
      "<div style='padding:26px 26px 10px 26px;display:flex;gap:16px;align-items:flex-start;'>" +
        "<div style='width:44px;height:44px;border-radius:12px;flex-shrink:0;background:" + iconBg + ";display:flex;align-items:center;justify-content:center;'>" + iconHtml + "</div>" +
        "<div style='flex:1;'>" +
          "<div style='font-size:17px;font-weight:800;color:#0f172a;margin-bottom:6px;'>" + title + "</div>" +
          "<div id='_cfMsg' style='font-size:14px;color:#475569;line-height:1.55;'></div>" +
        "</div>" +
      "</div>" +
      "<div style='padding:18px 26px 24px 26px;display:flex;gap:10px;justify-content:flex-end;'>" +
        "<button id='_cfCancel' style='background:#f1f5f9;color:#475569;border:none;padding:10px 20px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;'>" + cancelText + "</button>" +
        "<button id='_cfOk' style='background:" + btnBg + ";color:#fff;border:none;padding:10px 20px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;'>" + btnIcon + " " + confirmText + "</button>" +
      "</div>" +
    "</div>" +
    "<style>@keyframes _cfIn{from{transform:scale(0.92);opacity:0}to{transform:scale(1);opacity:1}}#_cfCancel:hover{background:#e2e8f0!important}#_cfOk:hover{filter:brightness(0.88)}</style>";

  backdrop.querySelector("#_cfMsg").innerHTML = message;
  document.body.appendChild(backdrop);

  function close() { backdrop.remove(); }
  backdrop.querySelector("#_cfOk").onclick    = function() { close(); onConfirm(); };
  backdrop.querySelector("#_cfCancel").onclick = close;
  backdrop.addEventListener("click", function(e) { if (e.target === backdrop) close(); });
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
  });
}

function showAlert(message, type) {
  type = type || "info";
  var existing = document.getElementById("_cfModal");
  if (existing) existing.remove();
  var cfg = {
    info:    { bg: "#eff6ff", stroke: "#2563eb", btn: "#2563eb", icon: "<circle cx='12' cy='12' r='10'/><line x1='12' y1='8' x2='12' y2='12'/><line x1='12' y1='16' x2='12.01' y2='16'/>" },
    error:   { bg: "#fff1f2", stroke: "#dc2626", btn: "#dc2626", icon: "<circle cx='12' cy='12' r='10'/><line x1='12' y1='8' x2='12' y2='12'/><line x1='12' y1='16' x2='12.01' y2='16'/>" },
    success: { bg: "#f0fdf4", stroke: "#16a34a", btn: "#16a34a", icon: "<polyline points='20 6 9 17 4 12'/>" }
  };
  var c = cfg[type] || cfg.info;
  var backdrop = document.createElement("div");
  backdrop.id = "_cfModal";
  backdrop.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,0.45);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;padding:16px;";
  backdrop.innerHTML =
    "<div style='background:#fff;border-radius:18px;width:100%;max-width:380px;box-shadow:0 20px 60px rgba(15,23,42,0.22);animation:_cfIn 0.18s ease;overflow:hidden;'>" +
      "<div style='padding:26px 26px 10px 26px;display:flex;gap:16px;align-items:flex-start;'>" +
        "<div style='width:44px;height:44px;border-radius:12px;flex-shrink:0;background:" + c.bg + ";display:flex;align-items:center;justify-content:center;'><svg width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='" + c.stroke + "' stroke-width='2.5'>" + c.icon + "</svg></div>" +
        "<div style='flex:1;padding-top:8px;font-size:14px;color:#334155;line-height:1.55;'>" + message + "</div>" +
      "</div>" +
      "<div style='padding:12px 26px 22px 26px;display:flex;justify-content:flex-end;'>" +
        "<button id='_cfOk' style='background:" + c.btn + ";color:#fff;border:none;padding:10px 24px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;'>OK</button>" +
      "</div>" +
    "</div>" +
    "<style>@keyframes _cfIn{from{transform:scale(0.92);opacity:0}to{transform:scale(1);opacity:1}}#_cfOk:hover{filter:brightness(0.88)}</style>";
  document.body.appendChild(backdrop);
  function close() { backdrop.remove(); }
  backdrop.querySelector("#_cfOk").onclick = close;
  backdrop.addEventListener("click", function(e) { if (e.target === backdrop) close(); });
  document.addEventListener("keydown", function esc(e) { if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); } });
}

/* ================= UPCOMING APPOINTMENTS (homepage) ================= */

async function loadUpcomingAppointments() {
  var container = document.getElementById("upcomingList");
  if (!container) return;
  try {
    var res = await fetch(API_BASE + "/appointments", { headers: { Authorization: "Bearer " + TOKEN } });
    if (!res.ok) return;
    var appts = await res.json();
    var now = new Date();
    var upcoming = appts
      .filter(function(a) { return new Date(a.scheduled_for) >= now; })
      .sort(function(a, b) { return new Date(a.scheduled_for) - new Date(b.scheduled_for); })
      .slice(0, 5);
    var skeletonEl = document.getElementById("upcomingSkeleton");
    if (skeletonEl) skeletonEl.remove();
    if (upcoming.length === 0) {
      container.innerHTML = "<div style='text-align:center;padding:28px 0;color:#94a3b8;'><svg width='36' height='36' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.5' style='opacity:0.4;display:block;margin:0 auto 10px;'><rect x='3' y='4' width='18' height='18' rx='2'/><line x1='16' y1='2' x2='16' y2='6'/><line x1='8' y1='2' x2='8' y2='6'/><line x1='3' y1='10' x2='21' y2='10'/></svg><p style='font-size:13px;font-weight:500;margin:0;'>No upcoming appointments</p></div>";
      return;
    }
    container.innerHTML = upcoming.map(function(a) {
      var dt   = new Date(a.scheduled_for);
      var mon  = dt.toLocaleDateString("en-CA", { month: "short" });
      var time = dt.toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit", hour12: true });
      var comm = a.comments ? " · " + a.comments.substring(0, 28) + (a.comments.length > 28 ? "…" : "") : "";
      return "<div style='display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #f1f5f9;'>" +
        "<div style='width:42px;height:42px;border-radius:10px;background:#eff6ff;display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0;'>" +
          "<span style='font-size:10px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:0.04em;'>" + mon + "</span>" +
          "<span style='font-size:17px;font-weight:800;color:#1e40af;line-height:1;'>" + dt.getDate() + "</span>" +
        "</div>" +
        "<div style='flex:1;min-width:0;'>" +
          "<div style='font-size:14px;font-weight:700;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>" + a.lead_name + "</div>" +
          "<div style='font-size:12px;color:#64748b;margin-top:2px;'>" + time + "<span style='color:#94a3b8;'>" + comm + "</span></div>" +
        "</div>" +
      "</div>";
    }).join("");
  } catch(e) { console.error(e); }
}

if (!localStorage.getItem("token") && !window.location.href.includes("login")) {
  window.location.href = "login.html";
}

const API = "https://data-log.onrender.com";
const API_BASE = API;
const TOKEN = localStorage.getItem("token");

if (!TOKEN && !location.pathname.includes("login")) {
  location.href = "login.html";
}

const CHART_COLORS = {
  blue: "#2563eb",
  green: "#16a34a",
  orange: "#f59e0b",
  red: "#dc2626",
  purple: "#7c3aed",
  gray: "#64748b"
};



/* ================= TIME ================= */

async function loadWeekly() {

  const res = await fetch(`${API_BASE}/history`, {
    headers: { Authorization: "Bearer " + TOKEN }
  });

  const data = await res.json();
  if (!data.length) return;

  /* ================= GROUP DATA BY WEEK ================= */

  const weeks = {};

  data.forEach(d => {

    const date = new Date(
      new Date(d.date + "T00:00:00")
        .toLocaleString("en-US", { timeZone: "America/Edmonton" })
    );

    const weekStart = new Date(date);
    const day = weekStart.getDay() === 0 ? 7 : weekStart.getDay();
    weekStart.setDate(weekStart.getDate() - day + 1);
    weekStart.setHours(0,0,0,0);

    const key = weekStart.toLocaleDateString("en-CA");
    if (!weeks[key]) weeks[key] = [];
    weeks[key].push(d);
  });

  /* ================= BUILD WEEKLY TREND ARRAYS ================= */

  const weekLabels = [];
  const weeklySales = [];
  const weeklyPresentations = [];
  const weeklyShowRatio = [];
  const weeklyClosingRatio = [];
  const weeklyAlpPerSale = [];
  const weeklyApptStart = [];
  const weeklyRefs = [];
  const weeklyConversionRatio = [];
  const weeklyBadLeadRatio = [];
  const weeklyAssignedLeads = [];
  let ytdTotalAlp = 0;
  let ytdPres = 0;
  let ytdSales = 0;
  let ytdAlp = 0;
  let ytdApptStart = 0;
  let ytdRefs = 0;
  let ytdAssignedLeads = 0;
  let ytdBadLeads = 0;




  Object.keys(weeks).sort().forEach(week => {

    let pres = 0;
    let sales = 0;
    let alp = 0;
    let apptStart = 0;
    let refs = 0;
    let assignedLeads = 0;
    let badLeads = 0;


    weeks[week].forEach(d => {
      pres += d.total_presentations;
      sales += d.total_sales;
      alp += d.total_alp;
      apptStart += d.appointments_start;
      refs += d.referrals_collected;
      assignedLeads += (d.assigned_leads || 0);
      badLeads += (d.bad_leads || 0);
    });
    ytdTotalAlp += alp;
    ytdPres += pres;
    ytdSales += sales;
    ytdAlp += alp;
    ytdApptStart += apptStart;
    ytdRefs += refs;
    ytdAssignedLeads += assignedLeads;
    ytdBadLeads += badLeads;



    weekLabels.push(week);
    weeklySales.push(sales);
    weeklyPresentations.push(pres);
    weeklyShowRatio.push(
      apptStart ? (pres / apptStart) * 100 : 0
    );
    weeklyClosingRatio.push(
      pres ? (sales / pres) * 100 : 0
    );
    weeklyAlpPerSale.push(
      sales ? alp / sales : 0
    );
    weeklyRefs.push(refs);
    weeklyApptStart.push(apptStart);

    weeklyConversionRatio.push(
      assignedLeads ? (pres / assignedLeads) * 100 : 0
    );
    weeklyBadLeadRatio.push(
      assignedLeads ? (badLeads / assignedLeads) * 100 : 0
    );
    weeklyAssignedLeads.push(assignedLeads);
  });

  const ytdShowRatio = ytdApptStart
    ? (ytdPres / ytdApptStart) * 100
    : 0;

  const ytdClosingRatio = ytdPres
    ? (ytdSales / ytdPres) * 100
    : 0;

  const ytdAlpPerSale = ytdSales
    ? ytdAlp / ytdSales
    : 0;

  const ytdRefsPerPres = ytdPres
    ? ytdRefs / ytdPres
    : 0;


  /* ================= KPI CARDS (LATEST WEEK) ================= */

  const lastIndex = weekLabels.length - 1;

  const ytdConvRatio = ytdAssignedLeads ? (ytdPres / ytdAssignedLeads) * 100 : 0;
  const ytdBadLeadRatio = ytdAssignedLeads ? (ytdBadLeads / ytdAssignedLeads) * 100 : 0;

  // Reveal real KPI grid, hide skeletons
  const skelGrid = document.getElementById("kpi-skeleton-grid");
  const realGrid = document.getElementById("kpi-real-grid");
  const chartsSkel = document.getElementById("charts-skeleton");
  const chartsReal = document.getElementById("charts-real");
  if (skelGrid) skelGrid.classList.add("hidden");
  if (realGrid) realGrid.classList.remove("hidden");
  if (chartsSkel) chartsSkel.classList.add("hidden");
  if (chartsReal) chartsReal.classList.remove("hidden");

  // Count-up animation helper
  function countUp(id, target, prefix = "", suffix = "", decimals = 0) {
    const el = document.getElementById(id);
    if (!el) return;
    const duration = 900;
    const start = performance.now();
    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      const val = ease * target;
      el.innerText = prefix + (decimals > 0 ? val.toFixed(decimals) : Math.round(val).toLocaleString()) + suffix;
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  countUp("wk_pres", ytdPres);
  countUp("wk_sales", ytdSales);
  countUp("wk_ytd_alp", ytdTotalAlp, "$", "", 0);
  countUp("wk_show", ytdShowRatio, "", "%");
  countUp("wk_close", ytdClosingRatio, "", "%");
  countUp("wk_alp", ytdAlpPerSale, "$", "", 0);
  countUp("wk_conv", ytdConvRatio, "", "%");
  countUp("wk_bad_lead", ytdBadLeadRatio, "", "%");
  countUp("wk_refs", ytdRefsPerPres, "", "", 2);

  // Color-code ratios
  setTimeout(() => {
    const closeEl = document.getElementById("wk_close");
    if (closeEl) closeEl.className = ytdClosingRatio >= 75 ? "good" : ytdClosingRatio >= 50 ? "warn" : "bad";

    const showEl = document.getElementById("wk_show");
    if (showEl) showEl.className = ytdShowRatio >= 75 ? "good" : ytdShowRatio >= 50 ? "warn" : "bad";

    const convEl = document.getElementById("wk_conv");
    if (convEl) convEl.className = ytdConvRatio >= 60 ? "good" : ytdConvRatio >= 35 ? "warn" : "bad";

    const badEl = document.getElementById("wk_bad_lead");
    if (badEl) badEl.className = ytdBadLeadRatio <= 30 ? "good" : ytdBadLeadRatio <= 55 ? "warn" : "bad";
  }, 950);

  // Homepage snapshot KPIs (no-ops on other pages)
  countUp("home_alp",   ytdTotalAlp,     "$", "", 0);
  countUp("home_sales", ytdSales);
  countUp("home_close", ytdClosingRatio, "",  "%");
  countUp("home_pres",  ytdPres);
  loadUpcomingAppointments();



  /* ================= WEEKLY TREND CHARTS ================= */

  drawChart({
    canvasId: "salesChart",
    type: "line",
    labels: weekLabels,
    data: weeklySales,
    title: "Weekly Sales Trend",
    colors: { border: CHART_COLORS.blue }
  });

  drawChart({
    canvasId: "presentationsChart",
    type: "bar",
    labels: weekLabels,
    data: weeklyPresentations,
    title: "Weekly Presentations",
    colors: { bg: CHART_COLORS.green }
  });

  drawChart({
    canvasId: "showRatioChart",
    type: "line",
    labels: weekLabels,
    data: weeklyShowRatio,
    title: "Weekly Show Ratio (%)",
    colors: { border: CHART_COLORS.orange }
  });

  drawChart({
    canvasId: "salesClosingYTD",
    type: "line",
    labels: weekLabels,
    datasets: [
      {
        label: "Sales",
        data: weeklySales,
        yAxisID: "ySales",
        borderColor: CHART_COLORS.blue
      },
      {
        label: "Closing Ratio %",
        data: weeklyClosingRatio,
        yAxisID: "yPercent",
        borderColor: CHART_COLORS.green
      }
    ],
    title: "Weekly Sales & Closing Ratio",
    scales: {
      ySales: { beginAtZero: true, position: "left" },
      yPercent: { beginAtZero: true, max: 100, position: "right" }
    }
  });

  drawChart({
    canvasId: "alpYTDChart",
    type: "line",
    labels: weekLabels,
    data: weeklyAlpPerSale,
    title: "Weekly ALP per Sale",
    colors: { border: CHART_COLORS.purple }
  });

  /* ================= LEAD RATIO CHART WITH TOGGLE ================= */

  // Store data globally for toggle access
  window._leadRatioData = {
    weekLabels,
    weeklyConversionRatio,
    weeklyBadLeadRatio
  };

  drawLeadRatioChart("ytd");

  // Set up toggle buttons
  const toggleBtns = document.querySelectorAll(".lead-ratio-toggle");
  toggleBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      toggleBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      drawLeadRatioChart(btn.dataset.period);
    });
  });

  /* ================= WEEKLY PIE CHARTS ================= */

  const lastPres = weeklyPresentations[lastIndex] || 0;
  const lastSales = weeklySales[lastIndex] || 0;
  const lastApptStart = weeklyApptStart[lastIndex] || 0;


  drawChart({
    canvasId: "closingPieChart",
    type: "pie",
    labels: ["Closed Sales", "Not Closed"],
    data: [
      ytdSales,
      Math.max(ytdPres - ytdSales, 0)
    ],
    title: "Year-to-Date Closing Ratio",
    colors: { bg: [CHART_COLORS.green, CHART_COLORS.red] }
  });


  drawChart({
    canvasId: "showRatioPieChart",
    type: "pie",
    labels: ["Shows", "No Shows"],
    data: [
      ytdPres,
      Math.max(ytdApptStart - ytdPres, 0)
    ],
    title: "Year-to-Date Show Ratio",
    colors: { bg: [CHART_COLORS.green, CHART_COLORS.gray] }
  });
}


/* ================= LEAD RATIO CHART ================= */

function drawLeadRatioChart(period) {
  const { weekLabels, weeklyConversionRatio, weeklyBadLeadRatio } =
    window._leadRatioData || { weekLabels: [], weeklyConversionRatio: [], weeklyBadLeadRatio: [] };

  let labels = weekLabels;
  let conversion = weeklyConversionRatio;
  let badLead = weeklyBadLeadRatio;

  if (period === "q1" || period === "q2" || period === "q3" || period === "q4") {
    const qMonths = { q1: [0,1,2], q2: [3,4,5], q3: [6,7,8], q4: [9,10,11] };
    const months = qMonths[period];
    const filtered = weekLabels.reduce((acc, lbl, i) => {
      const m = new Date(lbl + "T00:00:00").getMonth();
      if (months.includes(m)) acc.push(i);
      return acc;
    }, []);
    labels = filtered.map(i => weekLabels[i]);
    conversion = filtered.map(i => weeklyConversionRatio[i]);
    badLead = filtered.map(i => weeklyBadLeadRatio[i]);
  }

  drawChart({
    canvasId: "leadRatioChart",
    type: "line",
    labels,
    datasets: [
      {
        label: "Conversion Ratio %",
        data: conversion,
        borderColor: CHART_COLORS.blue,
        backgroundColor: "transparent",
        borderWidth: 3,
        tension: 0.35,
        pointRadius: 5,
        yAxisID: "yRatio"
      },
      {
        label: "Bad Lead Ratio %",
        data: badLead,
        borderColor: CHART_COLORS.red,
        backgroundColor: "transparent",
        borderWidth: 3,
        tension: 0.35,
        pointRadius: 5,
        yAxisID: "yRatio"
      }
    ],
    title: "Conversion Ratio & Bad Lead Ratio (%)",
    scales: {
      yRatio: { beginAtZero: true, max: 100, position: "left",
        title: { display: true, text: "%" } }
    }
  });
}


/* ================= CHART ================= */

function drawChart({
  canvasId,
  type = "line",
  labels = [],
  data = [],
  datasets = null,
  label = "",
  title = "",
  colors = {},
  scales = null
}) {

  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  // Destroy existing chart on this canvas only
  if (canvas._chart) {
    canvas._chart.destroy();
  }

  // Empty state — show message if no data
  const hasData = datasets
    ? datasets.some(ds => ds.data && ds.data.length > 0)
    : data && data.length > 0;

  const wrapper = canvas.parentElement;
  const existingEmpty = wrapper.querySelector('.empty-state');
  if (existingEmpty) existingEmpty.remove();

  if (!hasData) {
    canvas.style.display = 'none';
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <p>No data available yet</p>`;
    wrapper.appendChild(empty);
    return;
  } else {
    canvas.style.display = '';
  }

  // Build datasets safely
  const finalDatasets = datasets || [{
    label,
    data,
    backgroundColor: colors.bg || "#2563eb",
    borderColor: colors.border || colors.bg || "#2563eb",
    borderWidth: type === "bar" ? 1 : 3,
    tension: type === "line" ? 0.35 : 0,
    pointRadius: type === "line" ? 5 : 0,

    // Bar-chart polish
    barPercentage: type === "bar" ? 0.5 : undefined,
    categoryPercentage: type === "bar" ? 0.6 : undefined,
    borderRadius: type === "bar" ? 6 : 0
  }];

  canvas._chart = new Chart(canvas, {
    type,
    data: {
      labels,
      datasets: finalDatasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,

      plugins: {
        legend: { display: true },

        title: {
          display: !!title,
          text: title,
          font: { size: 16, weight: "600" },
          padding: { top: 10, bottom: 20 }
        },

        tooltip: {
          callbacks: {
            label: function(context) {

              // Pie chart percentage tooltip
              if (type === "pie") {
                const values = context.dataset.data;
                const total = values.reduce((a, b) => a + b, 0);
                const value = context.raw;
                const percent = total
                  ? ((value / total) * 100).toFixed(1)
                  : 0;
                return `${context.label}: ${value} (${percent}%)`;
              }

              // Line / bar tooltip
              return `${context.dataset.label}: ${context.formattedValue}`;
            }
          }
        }
      },

      scales: scales || (
        type !== "pie"
          ? { y: { beginAtZero: true } }
          : {}
      )
    }
  });
}


/* ================= SAVE DAY ================= */

async function save() {

  const payload = {
    date: document.getElementById("date").value,
    appointments_start: Number(appointments_start.value || 0),
    appointments_finish: Number(appointments_finish.value || 0),
    total_presentations: Number(total_presentations.value || 0),
    total_sales: Number(total_sales.value || 0),
    total_alp: Number(total_alp.value || 0),
    total_ah: Number(total_ah.value || 0),
    referrals_collected: Number(referrals_collected.value || 0),
    referral_presentations: Number(referral_presentations.value || 0),
    referral_sales: Number(referral_sales.value || 0),
    assigned_leads: Number(assigned_leads.value || 0),
    bad_leads: Number(bad_leads.value || 0)
  };

  const res = await fetch(`${API_BASE}/log-day`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + TOKEN
    },
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    const result = await res.json();
    const el = document.getElementById("saveSuccess");
    if (el) { el.style.display = "flex"; setTimeout(() => el.style.display = "none", 3000); }
    showToast(result.status === "updated" ? "Day updated successfully!" : "Day saved successfully!");
  } else {
    showToast("Save failed. Please try again.", "error");
  }
}

/* ================= HISTORY ================= */

let deleteMode = false;

async function loadHistory(){

 const res = await fetch(`${API_BASE}/history`,{
   headers:{ "Authorization":"Bearer "+TOKEN }
 });

 const data = await res.json();

 historyBody.innerHTML="";

 data.forEach(d=>{
  historyBody.innerHTML+=`
   <tr class="data-row">
    <td class="select-col">
      <input type="checkbox"
             class="rowCheck hidden"
             value="${d.id}"
             onchange="toggleRowHighlight(this)">
    </td>
    <td>${d.date}</td>
    <td>${d.appointments_start}</td>
    <td>${d.appointments_finish}</td>
    <td>${d.total_presentations}</td>
    <td>${d.total_sales}</td>
    <td>${d.total_alp}</td>
    <td>${d.total_ah}</td>
    <td>${d.referrals_collected}</td>
    <td>${d.referral_presentations}</td>
    <td>${d.referral_sales}</td>
    <td>${d.assigned_leads ?? 0}</td>
    <td>${d.bad_leads ?? 0}</td>
    <td>
      <button class="btn small" onclick='editDay(${JSON.stringify(d)})'>Edit</button>
    </td>
   </tr>`;
 });
}

/* ================= DELETE MODE ================= */

function toggleDeleteMode(){

  deleteMode = !deleteMode;

  document.querySelectorAll(".rowCheck").forEach(c=>{
    c.classList.toggle("hidden", !deleteMode);
    c.checked = false;
  });

  document.querySelectorAll(".data-row").forEach(r=>{
    r.classList.remove("delete-selected");
  });

  document.querySelectorAll(".select-col").forEach(c=>{
    c.style.display = deleteMode ? "table-cell" : "none";
  });

  document.getElementById("deleteSelectedBtn")
          .classList.toggle("hidden", !deleteMode);

  document.getElementById("deleteToggle").innerText =
    deleteMode ? "Cancel" : "Delete";

  const selectAll = document.getElementById("selectAll");
  if(selectAll) selectAll.checked = false;
}

function toggleRowHighlight(box){
  const row = box.closest("tr");
  row.classList.toggle("delete-selected", box.checked);
}

function toggleSelectAll(source){
  document.querySelectorAll(".rowCheck").forEach(box=>{
    box.checked = source.checked;
    toggleRowHighlight(box);
  });
}

function deleteSelected(){

  const ids = [...document.querySelectorAll(".rowCheck:checked")]
              .map(c => Number(c.value));

  if(ids.length === 0){
    showAlert("Please select at least one day to delete.", "info");
    return;
  }

  showConfirm(
    "Delete <strong>" + ids.length + "</strong> selected day" + (ids.length > 1 ? "s" : "") + "? This cannot be undone.",
    async function() {
      const res = await fetch(`${API_BASE}/delete-days`,{
        method:"DELETE",
        headers:{
          "Content-Type":"application/json",
          "Authorization":"Bearer " + TOKEN
        },
        body: JSON.stringify(ids)
      });
      if(res.ok){
        showToast("Selected days deleted.");
        toggleDeleteMode();
        loadHistory();
      } else {
        showToast("Delete failed. Please try again.", "error");
      }
    },
    { confirmText: "Delete" }
  );
}

/* ================= EDIT AUTOFILL ================= */

function editDay(data){
  localStorage.setItem("editEntry", JSON.stringify(data));
  location.href = "log.html";
}

/* ================= HELPERS ================= */

function formatDate(d){
 return d.toLocaleDateString(undefined,{
  month:"short",
  day:"numeric",
  year:"numeric"
 });
}

window.onload=()=>{

 const dateInput=document.getElementById("date");
 if(dateInput){
  const calgaryStr = new Date().toLocaleDateString("en-CA", {
    timeZone: "America/Edmonton"
  });
  dateInput.value = calgaryStr;

 }

 const editEntry = localStorage.getItem("editEntry");

 if(editEntry){
  const d = JSON.parse(editEntry);

  document.getElementById("date").value = d.date;
  appointments_start.value = d.appointments_start;
  appointments_finish.value = d.appointments_finish;
  total_presentations.value = d.total_presentations;
  total_sales.value = d.total_sales;
  total_alp.value = d.total_alp;
  total_ah.value = d.total_ah;
  referrals_collected.value = d.referrals_collected;
  referral_presentations.value = d.referral_presentations;
  referral_sales.value = d.referral_sales;

  if (document.getElementById("assigned_leads"))
    document.getElementById("assigned_leads").value = d.assigned_leads ?? 0;
  if (document.getElementById("bad_leads"))
    document.getElementById("bad_leads").value = d.bad_leads ?? 0;

  localStorage.removeItem("editEntry");
 }

 if(typeof historyBody!=="undefined") loadHistory();
};

/* ================= LOGOUT ================= */

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  localStorage.removeItem("role");
  window.location.href = "/";
}

window.logout = logout;

/* ================= EXPORT ================= */

async function exportExcel() {

  const res = await fetch("/history", {
    headers: { Authorization: "Bearer " + TOKEN }
  });

  if (!res.ok) {
    showAlert("Failed to fetch data.", "error");
    return;
  }

  const data = await res.json();

  if (data.length === 0) {
    showAlert("No data to export yet.", "info");
    return;
  }

  const headers = Object.keys(data[0]).filter(k => k !== "id" && k !== "user_id");

  let csv = headers.join(",") + "\n";

  data.forEach(row => {
    csv += headers.map(h => row[h]).join(",") + "\n";
  });

  const blob = new Blob([csv], { type: "text/csv" });
  const url = window.URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "kpi_data.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/* ================= TOAST NOTIFICATIONS ================= */

function showToast(message, type = "success") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  const icons = {
    success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>',
    error:   '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    info:    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
  };
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = (icons[type] || icons.info) + " " + message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}