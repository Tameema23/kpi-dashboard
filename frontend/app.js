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
  let ytdTotalAlp = 0;



  Object.keys(weeks).sort().forEach(week => {

    let pres = 0;
    let sales = 0;
    let alp = 0;
    let apptStart = 0;
    let refs = 0;


    weeks[week].forEach(d => {
      pres += d.total_presentations;
      sales += d.total_sales;
      alp += d.total_alp;
      apptStart += d.appointments_start;
      refs += d.referrals_collected;
    });
    ytdTotalAlp += alp;


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
  });

  /* ================= KPI CARDS (LATEST WEEK) ================= */

  const lastIndex = weekLabels.length - 1;

  wk_pres.innerText = weeklyPresentations[lastIndex] || 0;
  wk_sales.innerText = weeklySales[lastIndex] || 0;
  wk_show.innerText = weeklyShowRatio[lastIndex]
    ? Math.round(weeklyShowRatio[lastIndex]) + "%"
    : "0%";
  wk_close.innerText = weeklyClosingRatio[lastIndex]
    ? Math.round(weeklyClosingRatio[lastIndex]) + "%"
    : "0%";
  wk_alp.innerText = weeklyAlpPerSale[lastIndex]
    ? "$" + Math.round(weeklyAlpPerSale[lastIndex])
    : "$0";
  wk_refs.innerText = weeklyPresentations[lastIndex]
    ? (weeklyRefs[lastIndex] / weeklyPresentations[lastIndex]).toFixed(2)
    : "0";
  
  wk_ytd_alp.innerText = "$" + ytdTotalAlp.toLocaleString();



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

  /* ================= WEEKLY PIE CHARTS ================= */

  const lastPres = weeklyPresentations[lastIndex] || 0;
  const lastSales = weeklySales[lastIndex] || 0;
  const lastApptStart = weeklyApptStart[lastIndex] || 0;


  drawChart({
    canvasId: "closingPieChart",
    type: "pie",
    labels: ["Closed Sales", "Not Closed"],
    data: [lastSales, Math.max(lastPres - lastSales, 0)],
    title: "Latest Week Closing Ratio",
    colors: { bg: [CHART_COLORS.green, CHART_COLORS.red] }
  });

  drawChart({
    canvasId: "showRatioPieChart",
    type: "pie",
    labels: ["Shows", "No Shows"],
    data: [lastPres, Math.max(lastApptStart - lastPres, 0)],
    title: "Latest Week Show Ratio",
    colors: { bg: [CHART_COLORS.green, CHART_COLORS.gray] }
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
    referral_sales: Number(referral_sales.value || 0)
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
    document.getElementById("saveSuccess").style.display = "block";
  } else {

    const msg = await res.text();

    if(msg.includes("already logged")){
      alert("This day is already logged. You can edit it in History.");
    }else{
      alert("Save failed");
    }
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

async function deleteSelected(){

  const ids = [...document.querySelectorAll(".rowCheck:checked")]
              .map(c => Number(c.value));

  if(ids.length === 0){
    alert("Select at least one day to delete");
    return;
  }

  const res = await fetch(`${API_BASE}/delete-days`,{
    method:"DELETE",
    headers:{
      "Content-Type":"application/json",
      "Authorization":"Bearer " + TOKEN
    },
    body: JSON.stringify(ids)
  });

  if(res.ok){
    toggleDeleteMode();
    loadHistory();
  }else{
    alert("Delete failed");
  }
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
  const calgary=new Date(
    new Date().toLocaleString("en-US",{timeZone:"America/Edmonton"})
  );
  dateInput.value=calgary.toISOString().split("T")[0];
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

  localStorage.removeItem("editEntry");
 }

 if(typeof historyBody!=="undefined") loadHistory();
};

/* ================= LOGOUT ================= */

function logout() {
  localStorage.removeItem("token");
  window.location.href = "/";
}

window.logout = logout;

/* ================= EXPORT ================= */

async function exportExcel() {

  const res = await fetch("/history", {
    headers: { Authorization: "Bearer " + TOKEN }
  });

  if (!res.ok) {
    alert("Failed to fetch data");
    return;
  }

  const data = await res.json();

  if (data.length === 0) {
    alert("No data to export yet");
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
