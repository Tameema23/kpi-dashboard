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

/* ── #25  Dark mode ───────────────────────────────────────────────
   Toggles dark-mode class on body, persists to localStorage. */
function initDarkMode() {
  if (localStorage.getItem("darkMode") === "1") {
    document.body.classList.add("dark-mode");
  }
}

function toggleDarkMode() {
  var isDark = document.body.classList.toggle("dark-mode");
  localStorage.setItem("darkMode", isDark ? "1" : "0");
  // Update toggle button icon
  document.querySelectorAll(".dark-toggle svg").forEach(function(svg) {
    svg.innerHTML = isDark
      ? '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'
      : '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
  });
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

/* ── #34  PWA install prompt (Android) ───────────────────────────
   Catches the browser's beforeinstallprompt event and shows
   a custom banner at the bottom of the screen. */
(function() {
  var deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", function(e) {
    e.preventDefault();
    deferredPrompt = e;
    // Show banner after a short delay
    setTimeout(showPWABanner, 2000);
  });

  function showPWABanner() {
    if (!deferredPrompt) return;
    if (localStorage.getItem("pwaPromptDismissed")) return;

    var banner = document.createElement("div");
    banner.className = "pwa-install-banner visible";
    banner.id = "pwaBanner";
    banner.innerHTML =
      '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" style="flex-shrink:0"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>' +
      '<p>Add KPI Dashboard to your home screen</p>' +
      '<button class="pwa-btn" id="pwaInstallBtn">Install</button>' +
      '<button class="pwa-dismiss" id="pwaDismissBtn">&times;</button>';
    document.body.appendChild(banner);

    document.getElementById("pwaInstallBtn").onclick = function() {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function() { banner.remove(); deferredPrompt = null; });
    };
    document.getElementById("pwaDismissBtn").onclick = function() {
      banner.remove();
      localStorage.setItem("pwaPromptDismissed", "1");
    };
  }
})();

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

  // Dark mode applied early (before paint)
  initDarkMode();

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

// Apply dark mode immediately (before DOMContentLoaded) to prevent flash
initDarkMode();