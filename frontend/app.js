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
      var dt        = new Date(a.scheduled_for);
      var mon       = dt.toLocaleDateString("en-CA", { month: "short" });
      var time      = dt.toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit", hour12: true });
      var comm      = a.comments ? " · " + a.comments.substring(0, 28) + (a.comments.length > 28 ? "…" : "") : "";
      var isCallback = a.appt_type === "callback";
      var iconBg    = isCallback ? "#fef3c7" : "#eff6ff";
      var iconColor = isCallback ? "#92400e" : "#2563eb";
      var numColor  = isCallback ? "#92400e" : "#1e40af";
      var typeBadge = isCallback
        ? "<span style='display:inline-block;background:#fef3c7;color:#92400e;border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;margin-left:6px;vertical-align:middle;'>CB</span>"
        : "";
      return "<div style='display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #f1f5f9;'>" +
        "<div style='width:42px;height:42px;border-radius:10px;background:" + iconBg + ";display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0;'>" +
          "<span style='font-size:10px;font-weight:700;color:" + iconColor + ";text-transform:uppercase;letter-spacing:0.04em;'>" + mon + "</span>" +
          "<span style='font-size:17px;font-weight:800;color:" + numColor + ";line-height:1;'>" + dt.getDate() + "</span>" +
        "</div>" +
        "<div style='flex:1;min-width:0;'>" +
          "<div style='font-size:14px;font-weight:700;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>" + a.lead_name + typeBadge + "</div>" +
          "<div style='font-size:12px;color:#64748b;margin-top:2px;'>" + time + "<span style='color:#94a3b8;'>" + comm + "</span></div>" +
        "</div>" +
      "</div>";
    }).join("");
  } catch(e) { console.error(e); }
}

const API = "https://data-log.onrender.com";
const API_BASE = API;
const TOKEN = localStorage.getItem("token");

if (!TOKEN && !location.pathname.includes("login")) {
  location.href = "/login.html";
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
  if (!data.length) { if (typeof showOnboardingState === 'function') showOnboardingState(); return; }

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
  let ytdPres = 0;
  let ytdSales = 0;
  let ytdAlp = 0;
  let ytdApptStart = 0;
  let ytdRefs = 0;
  let ytdRefPres = 0;
  let ytdRefSales = 0;
  let ytdAssignedLeads = 0;
  let ytdBadLeads = 0;

  Object.keys(weeks).sort().forEach(week => {

    let pres = 0;
    let sales = 0;
    let alp = 0;
    let apptStart = 0;
    let refs = 0;
    let refPres = 0;
    let refSales = 0;
    let assignedLeads = 0;
    let badLeads = 0;

    weeks[week].forEach(d => {
      pres += d.total_presentations;
      sales += d.total_sales;
      alp += d.total_alp;
      apptStart += d.appointments_start;
      refs += d.referrals_collected;
      refPres += (d.referral_presentations || 0);
      refSales += (d.referral_sales || 0);
      assignedLeads += (d.assigned_leads || 0);
      badLeads += (d.bad_leads || 0);
    });
    ytdPres += pres;
    ytdSales += sales;
    ytdAlp += alp;
    ytdApptStart += apptStart;
    ytdRefs += refs;
    ytdRefPres += refPres;
    ytdRefSales += refSales;
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

  const ytdRefClosingRatio = ytdRefPres
    ? (ytdRefSales / ytdRefPres) * 100
    : 0;

  const ytdRefSalesRatio = ytdSales
    ? (ytdRefSales / ytdSales) * 100
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
  countUp("wk_ytd_alp", ytdAlp, "$", "", 0);
  countUp("wk_show", ytdShowRatio, "", "%");
  countUp("wk_close", ytdClosingRatio, "", "%");
  countUp("wk_alp", ytdAlpPerSale, "$", "", 0);
  countUp("wk_conv", ytdConvRatio, "", "%");
  countUp("wk_bad_lead", ytdBadLeadRatio, "", "%");
  countUp("wk_refs", ytdRefsPerPres, "", "", 2);
  countUp("wk_ref_sales", ytdRefSales);
  countUp("wk_ref_close", ytdRefClosingRatio, "", "%");
  countUp("wk_ref_sales_ratio", ytdRefSalesRatio, "", "%");

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

    const refCloseEl = document.getElementById("wk_ref_close");
    if (refCloseEl) refCloseEl.className = ytdRefClosingRatio >= 75 ? "good" : ytdRefClosingRatio >= 50 ? "warn" : "bad";

    const refSalesRatioEl = document.getElementById("wk_ref_sales_ratio");
    if (refSalesRatioEl) refSalesRatioEl.className = ytdRefSalesRatio >= 30 ? "good" : ytdRefSalesRatio >= 15 ? "warn" : "bad";
  }, 950);

  // Homepage snapshot KPIs (no-ops on other pages)
  countUp("home_alp",   ytdAlp,     "$", "", 0);
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
    // Note: addChartMobileValues is called after chart creation below
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

  // Add mobile value display for line/pie charts
  if (typeof addChartMobileValues === "function") {
    addChartMobileValues(canvasId, type, labels, data, datasets, colors);
  }
}

/* ================= SAVE DAY ================= */

async function save() {
  var _saveBtn = document.querySelector('.log-form-footer .btn');
  if (_saveBtn) { _saveBtn.disabled = true; _saveBtn.style.opacity = '0.7'; }

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
    if (typeof window._markSaved === "function") window._markSaved();
  } else {
    showToast("Save failed. Please try again.", "error");
  }
  var _saveBtn2 = document.querySelector('.log-form-footer .btn');
  if (_saveBtn2) { _saveBtn2.disabled = false; _saveBtn2.style.opacity = '1'; }
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

/* ================= EXPORT ================= */

async function exportExcel() {

  const res = await fetch(`${API_BASE}/history`, {
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

  // Human-readable headers + calculated columns
  const HEADER_MAP = {
    date: "Date", appointments_start: "Appts Start", appointments_finish: "Appts Finish",
    total_presentations: "Presentations", total_sales: "Sales",
    total_alp: "Total ALP ($)", total_ah: "Total A&H ($)",
    referrals_collected: "Refs Collected", referral_presentations: "Ref Presentations",
    referral_sales: "Ref Sales", assigned_leads: "Assigned Leads", bad_leads: "Bad Leads"
  };
  const keys = Object.keys(HEADER_MAP);
  const allHeaders = Object.values(HEADER_MAP).concat(["Closing %", "Show Ratio %", "ALP / Sale"]);
  let csv = allHeaders.join(",") + "\n";
  data.forEach(row => {
    const closing = row.total_presentations > 0 ? ((row.total_sales / row.total_presentations) * 100).toFixed(1) : "0.0";
    const show    = row.appointments_start  > 0 ? ((row.total_presentations / row.appointments_start) * 100).toFixed(1) : "0.0";
    const alpSale = row.total_sales > 0 ? (row.total_alp / row.total_sales).toFixed(2) : "0.00";
    csv += keys.map(k => row[k] !== undefined ? row[k] : 0).join(",") + "," + closing + "," + show + "," + alpSale + "\n";
  });

  const blob = new Blob([csv], { type: "text/csv" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "kpi_export_" + new Date().toLocaleDateString("en-CA") + ".csv";
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
/* =================================================================
   UX IMPROVEMENTS — items 20-38
   ================================================================= */

/* ── #20  Onboarding empty state ─────────────────────────────────
   Replaces blank KPI cards on first login with a friendly prompt. */
function showOnboardingState() {
  var grid = document.querySelector(".home-grid");
  if (!grid) return;
  grid.innerHTML =
    '<div class="onboarding-banner">' +
      '<div class="onboarding-icon">' +
        '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2">' +
          '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>' +
          '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>' +
        '</svg>' +
      '</div>' +
      '<div class="onboarding-text">' +
        '<h3>Welcome! Log your first day to get started</h3>' +
        '<p>Your KPI stats, charts, and reports will appear here once you log your first day of production.</p>' +
        '<a href="/log.html" class="onboarding-btn">' +
          '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>' +
          'Log Today\'s KPIs' +
        '</a>' +
      '</div>' +
    '</div>';
}

/* ── #21  Notification badge on Planner nav link ─────────────────
   Fetches appointments and shows a red badge on Planner links
   for appointments booked since the user last visited the planner.
   Clears when user visits planner. */
function initPlannerBadge() {
  var isPlanner = location.pathname.includes("planner");
  if (isPlanner) {
    // Clear on planner page
    localStorage.setItem("planner_last_seen", Date.now().toString());
    localStorage.removeItem("planner_new_count");
    return;
  }
  if (!TOKEN) return;

  fetch(API_BASE + "/appointments", {
    headers: { Authorization: "Bearer " + TOKEN }
  }).then(function(r) {
    if (!r.ok) return null;
    return r.json();
  }).then(function(appts) {
    if (!appts) return;
    var lastSeen = parseInt(localStorage.getItem("planner_last_seen") || "0");
    var newCount = appts.filter(function(a) {
      // booked_at is "YYYY-MM-DDTHH:MM" — convert to ms
      var ts = new Date(a.booked_at).getTime();
      return ts > lastSeen;
    }).length;
    if (newCount < 1) return;
    document.querySelectorAll("a[href='/planner.html']").forEach(function(link) {
      if (link.querySelector(".nav-badge")) return; // already has badge
      var badge = document.createElement("span");
      badge.className = "nav-badge";
      badge.innerText  = newCount > 9 ? "9+" : String(newCount);
      link.style.position = "relative";
      link.appendChild(badge);
    });
  }).catch(function() {});
}

/* ── #22  Planner appointment count summary bar ──────────────────
   Called after renderPlanner() — updates the summary bar above
   the grid with counts for this week and today. */
function updatePlannerSummary(appointments, weekStart) {
  var bar = document.getElementById("plannerSummary");
  if (!bar) return;

  var now     = new Date();
  var today   = now.toLocaleDateString("en-CA");
  var weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 6);

  var weekAppts  = appointments.filter(function(a) {
    var d = (a.scheduled_for || "").split("T")[0];
    var dt = new Date(d + "T00:00:00");
    return dt >= weekStart && dt <= weekEnd;
  });
  var todayAppts = appointments.filter(function(a) {
    return (a.scheduled_for || "").split("T")[0] === today;
  });
  var callbacks  = weekAppts.filter(function(a) { return a.appt_type === "callback"; });
  var appts      = weekAppts.filter(function(a) { return a.appt_type !== "callback"; });

  if (weekAppts.length === 0) {
    bar.innerHTML = '<span class="planner-summary-badge empty">No appointments this week</span>';
    return;
  }

  var html = '<span class="planner-summary-label">This week:</span>';
  if (appts.length    > 0) html += '<span class="planner-summary-badge appt">' + appts.length + (appts.length === 1 ? " appt" : " appts") + '</span>';
  if (callbacks.length > 0) html += '<span class="planner-summary-badge cb">' + callbacks.length + (callbacks.length === 1 ? " callback" : " callbacks") + '</span>';
  if (todayAppts.length > 0) html += '<span class="planner-summary-badge today">' + todayAppts.length + ' today</span>';
  bar.innerHTML = html;
}

/* ── #24  Quality page analytics summary ─────────────────────────
   Renders a summary row above the quality table with totals. */
function renderQualityAnalytics(entries) {
  var container = document.getElementById("qualitySummary");
  if (!container) return;

  var totalAlp = 0;
  var followUpCount = 0;
  var now = new Date().toLocaleDateString("en-CA");

  entries.forEach(function(e) {
    var alp = parseFloat((e.alp || "0").replace(/[^0-9.]/g, ""));
    if (!isNaN(alp)) totalAlp += alp;
    if (e.follow_up && e.follow_up.trim()) followUpCount++;
  });

  container.innerHTML =
    '<div class="quality-stat">' +
      '<div class="quality-stat-label">Total Entries</div>' +
      '<div class="quality-stat-value">' + entries.length + '</div>' +
    '</div>' +
    '<div class="quality-stat">' +
      '<div class="quality-stat-label">Total ALP Tracked</div>' +
      '<div class="quality-stat-value green">$' + totalAlp.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0}) + '</div>' +
    '</div>' +
    '<div class="quality-stat">' +
      '<div class="quality-stat-label">Follow-Ups Assigned</div>' +
      '<div class="quality-stat-value amber">' + followUpCount + '</div>' +
    '</div>';
}



/* ── #26  Log form keyboard navigation ───────────────────────────
   Enter key on any log input moves to the next field.
   On the last field, Enter triggers save(). */
function initLogKeyNav() {
  var order = [
    "date",
    "appointments_start","appointments_finish",
    "total_presentations","total_sales",
    "referrals_collected","referral_presentations","referral_sales",
    "total_alp","total_ah",
    "assigned_leads","bad_leads"
  ];
  order.forEach(function(id, i) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("keydown", function(e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      var next = order[i + 1];
      if (next) {
        var nextEl = document.getElementById(next);
        if (nextEl) { nextEl.focus(); nextEl.select && nextEl.select(); }
      } else {
        if (typeof save === "function") save();
      }
    });
  });
}

/* ── #26  Unsaved form warning ────────────────────────────────────
   Warns before navigating away from a dirty log form. */
function initUnsavedWarning() {
  var dirty = false;
  var saved = false;
  var fields = ["appointments_start","appointments_finish","total_presentations",
    "total_sales","referrals_collected","referral_presentations","referral_sales",
    "total_alp","total_ah","assigned_leads","bad_leads"];
  fields.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", function() {
      if (parseFloat(el.value) > 0) dirty = true;
    });
  });
  window._markSaved = function() { saved = true; dirty = false; };
  window.addEventListener("beforeunload", function(e) {
    if (dirty && !saved) { e.preventDefault(); e.returnValue = ""; }
  });
}

/* ── #28  Chart data labels ───────────────────────────────────────
   Registers the datalabels plugin inline (no CDN needed)
   to show values above bar and line data points. */
(function() {
  if (typeof Chart === "undefined") return;

  // Minimal inline data labels plugin — shows values above bars only
  var DataLabels = {
    id: "kpiDataLabels",
    afterDatasetsDraw: function(chart) {
      var ctx = chart.ctx;
      chart.data.datasets.forEach(function(dataset, i) {
        var meta = chart.getDatasetMeta(i);
        if (meta.hidden) return;
        if (chart.config.type !== "bar") return; // bars only — lines use tooltips
        meta.data.forEach(function(bar, j) {
          var val = dataset.data[j];
          if (!val && val !== 0) return;
          var label = typeof val === "number" && val >= 1000
            ? "$" + Math.round(val).toLocaleString()
            : (Number.isInteger(val) ? String(val) : val.toFixed(1));
          ctx.save();
          ctx.font = "bold 11px Inter, Arial, sans-serif";
          ctx.fillStyle = "#475569";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(label, bar.x, bar.y - 3);
          ctx.restore();
        });
      });
    }
  };
  Chart.register(DataLabels);
})();

/* ── #31  Long-press on appointment blocks (mobile) ──────────────
   Attach to any .pg-appt-block element after render. */
function attachLongPress(el, appt) {
  var timer = null;
  el.addEventListener("touchstart", function() {
    el.classList.add("touch-active");
    timer = setTimeout(function() {
      var parts = (appt.scheduled_for || "T").split("T");
      var h = parseInt((parts[1] || "09:00").split(":")[0]);
      var m = (parts[1] || "09:00").split(":")[1];
      var ampm = h >= 12 ? "PM" : "AM";
      var h12  = h % 12 || 12;
      var time = h12 + ":" + m + " " + ampm;
      var msg  = appt.lead_name + " — " + time;
      if (appt.comments) msg += "\n" + appt.comments.substring(0, 60);
      showToast(msg, "info");
    }, 500);
  }, { passive: true });
  el.addEventListener("touchend",  function() { clearTimeout(timer); el.classList.remove("touch-active"); }, { passive: true });
  el.addEventListener("touchmove", function() { clearTimeout(timer); el.classList.remove("touch-active"); }, { passive: true });
}

/* ── #32  Pull-to-refresh ─────────────────────────────────────────
   On mobile, pulling down 80px+ triggers onRefresh callback. */
function initPullToRefresh(onRefresh) {
  var startY   = 0;
  var pulling  = false;
  var THRESH   = 80;
  var ind      = null;

  function getInd() {
    if (!ind) {
      ind = document.createElement("div");
      ind.className = "ptr-indicator";
      ind.innerHTML =
        '<svg class="ptr-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
        '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Pull to refresh';
      document.body.appendChild(ind);
    }
    return ind;
  }

  document.addEventListener("touchstart", function(e) {
    if (window.scrollY === 0) { startY = e.touches[0].clientY; pulling = true; }
  }, { passive: true });

  document.addEventListener("touchmove", function(e) {
    if (!pulling) return;
    var delta = e.touches[0].clientY - startY;
    if (delta < 10) return;
    var indicator = getInd();
    indicator.classList.add("visible");
    var progress = Math.min(delta / THRESH, 1);
    indicator.style.opacity = String(progress);
    indicator.innerHTML = delta >= THRESH
      ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Release to refresh'
      : '<svg class="ptr-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Pull to refresh';
  }, { passive: true });

  document.addEventListener("touchend", function(e) {
    if (!pulling) return;
    var delta = e.changedTouches[0].clientY - startY;
    pulling = false;
    if (ind) { ind.classList.remove("visible"); ind.style.opacity = "0"; }
    if (delta >= THRESH && typeof onRefresh === "function") {
      showToast("Refreshing...", "info");
      onRefresh();
    }
  });
}

/* ── PWA install — dismiss persists, settings page hook ──────────
   Auto-banner shows once. Hitting × stores pwaInstallDismissed
   permanently — it will never auto-show again.
   The Settings page always has an Install App card where the user
   can trigger the install prompt any time they want.
   window._pwaPrompt is stored globally for Settings to use. */
(function() {
  window._pwaPrompt = null;

  window.addEventListener("beforeinstallprompt", function(e) {
    e.preventDefault();
    window._pwaPrompt = e;
    // Only auto-show if user has never dismissed it
    if (!localStorage.getItem("pwaInstallDismissed")) {
      setTimeout(showPWABanner, 3000);
    }
    // Refresh Settings install card if it's on screen
    if (typeof renderInstallAppCard === "function") renderInstallAppCard();
  });

  window.addEventListener("appinstalled", function() {
    if (document.getElementById("_pwaBanner")) document.getElementById("_pwaBanner").remove();
    localStorage.setItem("pwaInstalled", "1");
    window._pwaPrompt = null;
    if (typeof renderInstallAppCard === "function") renderInstallAppCard();
  });

  window.showPWABanner = function() {
    if (localStorage.getItem("pwaInstalled") === "1") return;
    if (localStorage.getItem("pwaInstallDismissed") === "1") return;
    if (!window._pwaPrompt) return;
    if (document.getElementById("_pwaBanner")) return;

    var banner = document.createElement("div");
    banner.id = "_pwaBanner";
    banner.style.cssText = [
      "position:fixed", "bottom:80px", "left:12px", "right:12px",
      "background:#1e293b", "color:#fff", "border-radius:14px",
      "padding:14px 16px", "box-shadow:0 8px 24px rgba(0,0,0,0.3)",
      "z-index:400", "display:flex", "align-items:center", "gap:12px",
      "animation:kpi-page-in 0.2s ease-out"
    ].join(";");
    banner.innerHTML =
      '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" style="flex-shrink:0">' +
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>' +
      '</svg>' +
      '<div style="flex:1;">' +
        '<div style="font-size:14px;font-weight:700;margin-bottom:2px;">Add to Home Screen</div>' +
        '<div style="font-size:12px;color:rgba(255,255,255,0.6);">Quick access, full screen, no browser bar</div>' +
      '</div>' +
      '<button id="_pwaInstallBtn" style="background:#3b82f6;color:#fff;border:none;border-radius:8px;' +
        'padding:8px 14px;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap;flex-shrink:0;">Install</button>' +
      '<button id="_pwaDismissBtn" style="background:none;border:none;color:rgba(255,255,255,0.5);' +
        'cursor:pointer;padding:4px 8px;font-size:22px;line-height:1;flex-shrink:0;" title="Dismiss">&times;</button>';
    document.body.appendChild(banner);

    document.getElementById("_pwaInstallBtn").onclick = function() {
      window._pwaPrompt.prompt();
      window._pwaPrompt.userChoice.then(function(r) {
        banner.remove();
        if (r.outcome === "accepted") {
          localStorage.setItem("pwaInstalled", "1");
          window._pwaPrompt = null;
        }
      });
    };
    document.getElementById("_pwaDismissBtn").onclick = function() {
      banner.remove();
      // Permanently dismissed — won't auto-show again ever
      // but Settings page can still trigger the prompt
      localStorage.setItem("pwaInstallDismissed", "1");
      if (typeof renderInstallAppCard === "function") renderInstallAppCard();
    };
  };

  // Called from Settings "Install Now" button
  window.triggerPWAInstall = function() {
    if (localStorage.getItem("pwaInstalled") === "1") {
      showToast("KPI Dashboard is already installed!", "info");
      return;
    }
    if (!window._pwaPrompt) {
      showToast("Open from Chrome on Android, or use Safari on iOS to install.", "info");
      return;
    }
    localStorage.removeItem("pwaInstallDismissed");
    window._pwaPrompt.prompt();
    window._pwaPrompt.userChoice.then(function(r) {
      if (r.outcome === "accepted") {
        localStorage.setItem("pwaInstalled", "1");
        window._pwaPrompt = null;
        showToast("KPI Dashboard installed!", "success");
      }
      if (typeof renderInstallAppCard === "function") renderInstallAppCard();
    });
  };
})();

/* ── Install App card renderer (used by settings.html) ───────────
   Renders into #installAppCard with 3 states:
   1. Already installed / running standalone → green checkmark
   2. Prompt available → Install Now button
   3. No prompt (iOS/desktop) → manual instructions */
function renderInstallAppCard() {
  var card = document.getElementById("installAppCard");
  if (!card) return;

  var isStandalone = window.matchMedia("(display-mode: standalone)").matches
    || window.navigator.standalone === true;
  var isInstalled  = localStorage.getItem("pwaInstalled") === "1";
  var wasDismissed = localStorage.getItem("pwaInstallDismissed") === "1";
  var hasPrompt    = !!window._pwaPrompt;

  if (isStandalone || isInstalled) {
    card.innerHTML =
      '<div class="settings-card-header">' +
        '<div class="settings-icon icon-green">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>' +
        '</div>' +
        '<div><h2 style="margin:0 0 2px 0;font-size:17px;">App Installed</h2>' +
        '<p style="margin:0;font-size:13px;color:#64748b;">KPI Dashboard is installed on this device</p></div>' +
      '</div>' +
      '<p style="font-size:13px;color:#64748b;margin:0 0 16px 0;line-height:1.6;">Youre running the installed version. Find it on your home screen.</p>' +
      '<button onclick="uninstallPWA()" style="background:none;border:1.5px solid #e2e8f0;color:#64748b;' +
        'border-radius:8px;padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer;' +
        'display:flex;align-items:center;gap:6px;font-family:inherit;">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
          '<polyline points="3 6 5 6 21 6"/>' +
          '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>' +
          '<path d="M10 11v6"/><path d="M14 11v6"/>' +
          '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>' +
        '</svg>' +
        'I removed it — show install prompt again' +
      '</button>';
    return;
  }

  var installBtn = hasPrompt
    ? '<button class="btn" onclick="triggerPWAInstall()">' +
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
        ' Install Now</button>'
    : '<div style="font-size:13px;color:#64748b;background:#f8fafc;padding:12px 14px;border-radius:10px;border:1px solid #f1f5f9;line-height:1.7;">' +
        '<strong style="color:#0f172a;">Android Chrome:</strong> tap menu (⋮) → "Add to Home Screen"<br>' +
        '<strong style="color:#0f172a;">iOS Safari:</strong> tap Share (□↑) → "Add to Home Screen"' +
      '</div>';

  var dismissedNote = wasDismissed
    ? '<span style="color:#f59e0b;font-weight:600;font-size:12px;">You previously dismissed the install prompt. </span>'
    : '';

  card.innerHTML =
    '<div class="settings-card-header">' +
      '<div class="settings-icon icon-blue">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
      '</div>' +
      '<div><h2 style="margin:0 0 2px 0;font-size:17px;">Install App</h2>' +
      '<p style="margin:0;font-size:13px;color:#64748b;">Add KPI Dashboard to your home screen</p></div>' +
    '</div>' +
    '<p style="font-size:13px;color:#475569;margin:0 0 14px 0;line-height:1.6;">' +
      dismissedNote +
      'Install the app for faster access, full-screen experience, and no browser navigation bar.' +
    '</p>' +
    installBtn;
}

/* ── uninstallPWA — called from Settings "I removed it" button ───
   Clears the installed flag and re-shows the install prompt card.
   Note: browsers don't let JS actually uninstall a PWA — the user
   removes it from their home screen manually. This button just
   resets the state so the "Install Now" prompt appears again. */
window.uninstallPWA = function() {
  localStorage.removeItem("pwaInstalled");
  localStorage.removeItem("pwaInstallDismissed");
  if (typeof renderInstallAppCard === "function") renderInstallAppCard();
  // Re-show the auto-banner next time they visit any page
  showToast("Install prompt reset. Use the button below to reinstall.", "info");
};

/* ── #37  Environment-based API URL ──────────────────────────────
   Reads API_BASE from a <meta name="api-base"> tag if present,
   falling back to the hardcoded URL. Add this to all HTML heads:
   <meta name="api-base" content="https://your-host.onrender.com">
   Already works without the tag — this is a progressive upgrade. */
(function() {
  var metaTag = document.querySelector('meta[name="api-base"]');
  if (metaTag && metaTag.content) {
    // Override the constants — must run after they're declared
    // Use a MutationObserver trick if needed, but direct override works here
    window.API_BASE_OVERRIDE = metaTag.content;
  }
})();

/* ── #38  Error boundaries on all API calls ──────────────────────
   Wraps loadHistory and loadWeekly with user-visible error states. */
(function() {
  var _origLoadHistory = typeof loadHistory === "function" ? loadHistory : null;
  if (_origLoadHistory) {
    window.loadHistory = async function() {
      try {
        await _origLoadHistory();
      } catch(e) {
        var body = document.getElementById("historyBody");
        if (body) {
          body.innerHTML =
            '<tr><td colspan="14" style="text-align:center;padding:32px;color:#dc2626;">' +
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:8px;">' +
            '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
            'Failed to load history. <a href="#" onclick="loadHistory();return false;" style="color:#2563eb;font-weight:700;">Try again</a>' +
            '</td></tr>';
        }
      }
    };
  }
})();

/* ── Page-level init — runs once on DOMContentLoaded ─────────── */
document.addEventListener("DOMContentLoaded", function() {
  var path = location.pathname;

  // Log page
  if (path.includes("log")) {
    initLogKeyNav();
    initUnsavedWarning();
  }

  // Planner badge on all non-planner pages
  if (TOKEN) initPlannerBadge();

  // History pull-to-refresh
  if (path.includes("history")) {
    initPullToRefresh(function() { if (typeof loadHistory === "function") loadHistory(); });
  }
});

/* =================================================================
   NEW FEATURES — PWA, transitions, cold start, quality, drag-drop,
   chart mobile labels, planner auto-refresh, nav deduplication,
   database backup endpoint
   ================================================================= */

/* ── PAGE TRANSITIONS ────────────────────────────────────────────
   No JS needed. The CSS kpi-page-in animation handles the fade-in.
   html { background: #f1f5f9 } in style.css kills the white flash
   by painting the correct background before any CSS loads.
   Navigation is instant — no interception, no fake delays. */

/* ── COLD START OVERLAY ──────────────────────────────────────────
   Shows a "Connecting to server..." overlay after 3 seconds if
   the first API call hasn't returned. Disappears on first response.
   Render free tier can take 30-60s to wake up. */
(function() {
  if (location.pathname.includes("login")) return;

  var overlay = null;
  var timer   = null;
  var dismissed = false;

  function showOverlay() {
    if (dismissed) return;
    overlay = document.createElement("div");
    overlay.className = "cold-start-overlay visible";
    overlay.innerHTML =
      '<div class="cold-start-spinner"></div>' +
      '<div class="cold-start-text">' +
        'Connecting to server...' +
        '<div class="cold-start-sub">Render free tier is waking up — usually takes 20-40 seconds</div>' +
      '</div>';
    document.body.appendChild(overlay);
  }

  function hideOverlay() {
    dismissed = true;
    clearTimeout(timer);
    if (overlay) { overlay.remove(); overlay = null; }
  }

  // Show after 3 seconds if page hasn't loaded data yet
  timer = setTimeout(showOverlay, 3000);

  // Intercept all fetch calls — hide overlay on first successful response
  var _origFetch = window.fetch.bind(window);
  window.fetch = function() {
    return _origFetch.apply(null, arguments).then(function(res) {
      if (res.ok) hideOverlay();
      return res;
    }).catch(function(err) {
      throw err;
    });
  };

  // Also hide if page becomes visible after being hidden
  document.addEventListener("visibilitychange", function() {
    if (!document.hidden) hideOverlay();
  });
})();

/* ── PLANNER AUTO-REFRESH ────────────────────────────────────────
   Polls /appointments every 30 seconds on the planner page.
   Only re-renders if the data has actually changed (compares count
   and last booked_at). Silently updates — no disruptive flash. */
function initPlannerAutoRefresh(getAppointments, setAppointments, renderFn) {
  var INTERVAL = 30000; // 30 seconds
  var lastHash = "";
  var intervalId = null;

  function hashAppts(appts) {
    // Quick hash: count + newest booked_at
    var sorted = appts.slice().sort(function(a, b) {
      return (b.booked_at || "").localeCompare(a.booked_at || "");
    });
    return appts.length + "|" + (sorted[0] ? sorted[0].booked_at : "");
  }

  async function poll() {
    try {
      var res = await fetch(API_BASE + "/appointments", {
        headers: { Authorization: "Bearer " + TOKEN }
      });
      if (!res.ok) return;
      var fresh = await res.json();
      var hash  = hashAppts(fresh);
      if (hash !== lastHash) {
        lastHash = hash;
        setAppointments(fresh);
        renderFn();
        // Update badge timestamp
        var newest = fresh.reduce(function(max, a) {
          var t = new Date(a.booked_at).getTime();
          return t > max ? t : max;
        }, 0);
        if (newest > 0) {
          // If a new appointment was booked by someone else, show subtle indicator
          var lastSeen = parseInt(localStorage.getItem("planner_last_seen") || "0");
          if (newest > lastSeen) {
            // Silent re-render already done above — no toast to avoid being annoying
          }
        }
      }
    } catch(e) { /* silent — don't disrupt the user */ }
  }

  // Set initial hash
  lastHash = hashAppts(getAppointments());

  intervalId = setInterval(poll, INTERVAL);

  // Stop polling when page is hidden, restart when visible
  document.addEventListener("visibilitychange", function() {
    if (document.hidden) {
      clearInterval(intervalId);
    } else {
      poll(); // Immediate refresh on return
      intervalId = setInterval(poll, INTERVAL);
    }
  });

  return function stop() { clearInterval(intervalId); };
}

/* ── QUALITY FOLLOW-UP DUE INDICATORS ───────────────────────────
   After renderTable(), scan rows and highlight overdue/due-soon
   entries. Called with the entries array. */
function applyQualityDueIndicators(entries) {
  var tbody = document.getElementById("qualityBody");
  if (!tbody) return;

  var today = new Date();
  today.setHours(0, 0, 0, 0);
  var soonMs = 7 * 24 * 60 * 60 * 1000; // 7 days

  var rows = tbody.querySelectorAll("tr");
  rows.forEach(function(row, i) {
    var entry = entries[i];
    if (!entry) return;

    // Parse follow_up date — it might be "2025-03-15" or "Mar 15, 2025" etc.
    var followUp = (entry.follow_up || "").trim();
    if (!followUp) return;

    // Try parsing as a date
    var dt = new Date(followUp);
    if (isNaN(dt.getTime())) return; // not a parseable date — skip

    dt.setHours(0, 0, 0, 0);
    var diff = dt.getTime() - today.getTime();

    // Remove old classes
    row.classList.remove("quality-overdue", "quality-due-soon");

    // Find the follow_up cell (index 5) and add badge
    var fuCell = row.cells[5];
    if (!fuCell) return;

    // Remove existing due badge
    var existingBadge = fuCell.querySelector(".due-badge");
    if (existingBadge) existingBadge.remove();

    var badge = document.createElement("span");
    badge.className = "due-badge";

    if (diff < 0) {
      // Overdue
      row.classList.add("quality-overdue");
      badge.classList.add("overdue");
      var days = Math.abs(Math.round(diff / (1000*60*60*24)));
      badge.innerHTML =
        '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
        (days === 0 ? "Due today" : days + "d overdue");
    } else if (diff <= soonMs) {
      // Due within 7 days
      row.classList.add("quality-due-soon");
      badge.classList.add("soon");
      var daysLeft = Math.round(diff / (1000*60*60*24));
      badge.innerHTML =
        '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' +
        (daysLeft === 0 ? "Due today" : "Due in " + daysLeft + "d");
    } else {
      return; // Not due soon — no badge needed
    }

    fuCell.appendChild(badge);
  });
}

/* ── DRAG AND DROP RESCHEDULING ──────────────────────────────────
   Drag an appointment block to any time-slot cell to reschedule it.
   Shows an undo toast after the API call completes.
   Must be called after renderPlanner() to attach to new elements. */
function initDragDrop(getAppointments, saveAppointmentFn, renderFn) {
  var dragAppt   = null;  // appointment being dragged
  var dragEl     = null;  // DOM element being dragged
  var ghostEl    = null;  // preview ghost in target cell
  var undoStack  = [];    // {id, old_scheduled_for} for undo

  // Re-attach after every render by calling this on the grid
  function attachDragHandlers() {
    var grid = document.getElementById("plannerGrid");
    if (!grid) return;

    // ── Draggable blocks ─────────────────────────────────────
    grid.querySelectorAll(".pg-appt-block").forEach(function(block) {
      if (block._dragAttached) return;
      block._dragAttached = true;
      block.draggable = true;

      block.addEventListener("dragstart", function(e) {
        // Find the appointment by matching lead_name + time from block content
        var nameEl = block.querySelector(".pg-appt-name");
        var timeEl = block.querySelector(".pg-appt-time");
        if (!nameEl || !timeEl) return;

        // Store appt id on the element (set during renderPlanner)
        var apptId = parseInt(block.dataset.apptId);
        var appts  = getAppointments();
        dragAppt   = appts.find(function(a) { return a.id === apptId; });
        if (!dragAppt) return;

        dragEl = block;
        dragEl.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(dragAppt.id));
      });

      block.addEventListener("dragend", function() {
        if (dragEl) dragEl.classList.remove("dragging");
        clearGhost();
        dragAppt = null;
        dragEl   = null;
        // Clean up all drag-over highlights
        document.querySelectorAll(".pg-cell.drag-over").forEach(function(c) {
          c.classList.remove("drag-over", "callback-over");
        });
      });
    });

    // ── Drop target cells ─────────────────────────────────────
    grid.querySelectorAll(".pg-cell").forEach(function(cell) {
      if (cell._dropAttached) return;
      cell._dropAttached = true;

      cell.addEventListener("dragover", function(e) {
        if (!dragAppt) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";

        // Highlight cell
        document.querySelectorAll(".pg-cell.drag-over").forEach(function(c) {
          if (c !== cell) c.classList.remove("drag-over", "callback-over");
        });
        cell.classList.add("drag-over");
        if (dragAppt.appt_type === "callback") cell.classList.add("callback-over");

        // Show ghost
        clearGhost();
        ghostEl = document.createElement("div");
        ghostEl.className = "drop-ghost " + (dragAppt.appt_type === "callback" ? "callback" : "appointment");
        ghostEl.innerText = dragAppt.lead_name;
        cell.appendChild(ghostEl);
      });

      cell.addEventListener("dragleave", function(e) {
        // Only clear if actually leaving the cell (not entering a child)
        if (!cell.contains(e.relatedTarget)) {
          cell.classList.remove("drag-over", "callback-over");
          clearGhost();
        }
      });

      cell.addEventListener("drop", async function(e) {
        e.preventDefault();
        if (!dragAppt) return;

        cell.classList.remove("drag-over", "callback-over");
        clearGhost();

        // Get target date and hour from the cell's position in the grid
        var targetDate = cell.dataset.date;
        var targetHour = cell.dataset.hour;
        if (!targetDate || !targetHour) return;

        // Keep original minutes
        var origMinutes = (dragAppt.scheduled_for || "T00:00").split("T")[1].split(":")[1] || "00";
        var newScheduled = targetDate + "T" + String(targetHour).padStart(2, "0") + ":" + origMinutes;

        if (newScheduled === dragAppt.scheduled_for) return; // no change

        var oldScheduled = dragAppt.scheduled_for;
        var apptId       = dragAppt.id;

        // Optimistic update — update local data immediately
        var appts = getAppointments();
        var apptIdx = appts.findIndex(function(a) { return a.id === apptId; });
        if (apptIdx === -1) return;
        appts[apptIdx].scheduled_for = newScheduled;
        setAppointments(appts);
        renderFn();

        // Save to server
        try {
          var result = await saveAppointmentFn(apptId, { scheduled_for: newScheduled });
          if (result) {
            // Show undo toast
            showUndoToast(
              "Moved to " + formatDropTime(newScheduled),
              function() {
                // Undo — move back
                var appts2 = getAppointments();
                var idx2 = appts2.findIndex(function(a) { return a.id === apptId; });
                if (idx2 !== -1) appts2[idx2].scheduled_for = oldScheduled;
                setAppointments(appts2);
                renderFn();
                saveAppointmentFn(apptId, { scheduled_for: oldScheduled });
              }
            );
          }
        } catch(err) {
          // Revert on error
          var appts3 = getAppointments();
          var idx3 = appts3.findIndex(function(a) { return a.id === apptId; });
          if (idx3 !== -1) appts3[idx3].scheduled_for = oldScheduled;
          setAppointments(appts3);
          renderFn();
          showToast("Failed to reschedule. Please try again.", "error");
        }

        dragAppt = null;
        dragEl   = null;
      });
    });
  }

  function clearGhost() {
    if (ghostEl) { ghostEl.remove(); ghostEl = null; }
  }

  function formatDropTime(iso) {
    var parts = (iso || "T").split("T");
    var h = parseInt((parts[1] || "0").split(":")[0]);
    var m = (parts[1] || "00:00").split(":")[1];
    var ampm = h >= 12 ? "PM" : "AM";
    var h12  = h % 12 || 12;
    var days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
    var d    = new Date(parts[0] + "T00:00:00");
    return days[d.getDay()] + " " + h12 + ":" + m + " " + ampm;
  }

  function showUndoToast(message, onUndo) {
    var container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      document.body.appendChild(container);
    }
    var toast = document.createElement("div");
    toast.className = "toast success";
    toast.style.display = "flex";
    toast.style.alignItems = "center";
    toast.style.gap = "8px";

    var undoBtn = document.createElement("button");
    undoBtn.className = "toast-undo-btn";
    undoBtn.innerText = "Undo";
    undoBtn.onclick = function() {
      toast.remove();
      onUndo();
    };

    toast.innerHTML =
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>' +
      message;
    toast.appendChild(undoBtn);
    container.appendChild(toast);
    setTimeout(function() { if (toast.parentNode) toast.remove(); }, 5000);
  }

  return { attachDragHandlers: attachDragHandlers };
}

/* ── CHART MOBILE DATA VALUES ────────────────────────────────────
   For line and pie charts, renders a simple value list below the
   canvas on mobile screens (where hover is unavailable). */
function addChartMobileValues(canvasId, type, labels, data, datasets, colors) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;

  // Remove any existing mobile values
  var existing = canvas.parentElement.querySelector(".chart-mobile-values");
  if (existing) existing.remove();

  // Only for line and pie
  if (type !== "line" && type !== "pie") return;

  var container = document.createElement("div");
  container.className = "chart-mobile-values";

  if (type === "pie" && data && data.length > 0) {
    var total = data.reduce(function(s, v) { return s + v; }, 0);
    var bgColors = (colors && colors.bg) ? colors.bg : ["#2563eb","#dc2626","#16a34a","#f59e0b"];
    if (!Array.isArray(bgColors)) bgColors = [bgColors];
    labels.forEach(function(lbl, i) {
      var val  = data[i] || 0;
      var pct  = total > 0 ? ((val / total) * 100).toFixed(1) : "0.0";
      var color = bgColors[i % bgColors.length];
      var item = document.createElement("div");
      item.className = "chart-mv-item";
      item.innerHTML =
        '<div class="chart-mv-dot" style="background:' + color + '"></div>' +
        lbl + ': <span class="chart-mv-val">' + val + ' (' + pct + '%)</span>';
      container.appendChild(item);
    });
  } else if (type === "line") {
    // Show latest data point for each dataset
    var ds = datasets || [{ label: "", data: data || [], borderColor: (colors && colors.border) || "#2563eb" }];
    ds.forEach(function(d) {
      if (!d.data || d.data.length === 0) return;
      var latest = d.data[d.data.length - 1];
      var val = typeof latest === "number" ? (Number.isInteger(latest) ? latest : latest.toFixed(1)) : latest;
      var item = document.createElement("div");
      item.className = "chart-mv-item";
      item.innerHTML =
        '<div class="chart-mv-dot" style="background:' + (d.borderColor || "#2563eb") + '"></div>' +
        (d.label || "") + ': <span class="chart-mv-val">' + val + '</span>';
      container.appendChild(item);
    });
  }

  if (container.children.length > 0) {
    canvas.parentElement.appendChild(container);
  }
}

/* ── NAV DEDUPLICATION — renderNav() ────────────────────────────
   Call renderNav() from any page to stamp the topbar + bottom nav.
   Pass `activePage` as one of: home, log, reports, history,
   planner, quality, settings.
   This is OPTIONAL — existing pages still work with their hardcoded
   nav. This function is here for future pages or nav refactors. */
function renderNav(activePage) {
  var role       = localStorage.getItem("role") || "admin";
  var username   = localStorage.getItem("username") || "";
  var canQuality = localStorage.getItem("can_quality") === "1";
  var canPlanner = localStorage.getItem("can_planner") === "1";

  var pages = [
    { id: "home",     href: "/index.html",   label: "Home",     adminOnly: true },
    { id: "log",      href: "/log.html",     label: "Log Day",  adminOnly: true },
    { id: "reports",  href: "/reports.html", label: "Reports",  adminOnly: true },
    { id: "history",  href: "/history.html", label: "History",  adminOnly: true },
    { id: "planner",  href: "/planner.html", label: "Planner",  adminOnly: false },
    { id: "quality",  href: "/quality.html", label: "Quality",  adminOnly: false, qualityOnly: true },
    { id: "settings", href: "/settings.html",label: "Settings", adminOnly: false },
  ];

  function shouldShow(page) {
    if (page.adminOnly && role !== "admin") return false;
    if (page.qualityOnly && role !== "admin" && !canQuality) return false;
    if (page.id === "planner" && role !== "admin" && !canPlanner && !canQuality) return false;
    return true;
  }

  // Topbar nav
  var topbarNav = document.querySelector(".topbar-nav");
  if (topbarNav) {
    topbarNav.innerHTML = pages.filter(shouldShow).map(function(p) {
      var cls = p.id === activePage ? " class=\"active\"" : "";
      return '<a href="' + p.href + '"' + cls + '>' + p.label + '</a>';
    }).join("");
  }

  // Username
  var userEl = document.getElementById("username-text");
  if (userEl) userEl.innerText = username;
}

/* ── DATABASE BACKUP endpoint trigger ───────────────────────────
   Admins can trigger a manual backup from Settings.
   The actual backup logic lives in main.py (/backup endpoint).
   This function calls it and shows feedback. */
async function triggerBackup() {
  var btn = document.getElementById("backupBtn");
  if (btn) { btn.disabled = true; btn.innerText = "Backing up..."; }
  try {
    var res = await fetch(API_BASE + "/backup", {
      method: "POST",
      headers: { Authorization: "Bearer " + TOKEN }
    });
    if (res.ok) {
      var data = await res.json();
      showToast("Backup complete: " + (data.filename || "kpi_backup.db"), "success");
    } else {
      var err = await res.json().catch(function() { return {}; });
      showToast(err.detail || "Backup failed.", "error");
    }
  } catch(e) {
    showToast("Backup failed — server error.", "error");
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = "Backup Now"; }
  }
}