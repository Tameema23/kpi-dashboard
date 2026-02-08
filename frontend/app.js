if (!localStorage.getItem("token") && !window.location.href.includes("login")) {
  window.location.href = "login.html";
}

const API = "https://data-log.onrender.com";
const API_BASE = API;
const TOKEN = localStorage.getItem("token");

if (!TOKEN && !location.pathname.includes("login")) {
  location.href = "login.html";
}



/* ================= TIME ================= */

function getCalgaryToday() {
  return new Date(
    new Date().toLocaleString("en-US", { timeZone: "America/Edmonton" })
  ).toISOString().split("T")[0];
}

/* ================= WEEKLY ================= */

async function loadWeekly() {

  const res = await fetch(`${API_BASE}/history`, {
    headers: { Authorization: "Bearer " + TOKEN }
  });

  const data = await res.json();
  if (!data.length) return;

  /* ================= WEEKLY GROUPING (ORIGINAL) ================= */

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

  /* ================= WEEK SELECTOR (ORIGINAL) ================= */

  const select = weekSelect;
  const prev = select.value;
  select.innerHTML = "";

  const sortedWeeks = Object.keys(weeks).sort(
    (a,b)=>new Date(b+"T12:00:00") - new Date(a+"T12:00:00")
  );

  sortedWeeks.forEach(start => {

    const ws = new Date(
      new Date(start+"T00:00:00")
        .toLocaleString("en-US",{ timeZone:"America/Edmonton" })
    );

    const we = new Date(ws);
    we.setDate(ws.getDate()+6);

    const opt = document.createElement("option");
    opt.value = start;
    opt.text = `${formatDate(ws)} – ${formatDate(we)}`;
    if(start === prev) opt.selected = true;
    select.appendChild(opt);
  });

  const chosen = select.value || sortedWeeks[0];
  const weekData = weeks[chosen].sort(
    (a,b)=>new Date(a.date)-new Date(b.date)
  );

  /* ================= WEEKLY METRICS (FIXED SHOW RATIO) ================= */

  let labels = [];
  let salesTrend = [];
  let presentations = [];
  let showRates = [];

  let pres = 0;
  let sales = 0;
  let alp = 0;
  let refs = 0;
  let apptStart = 0;

  weekData.forEach(d => {

    labels.push(d.date);
    salesTrend.push(d.total_sales);
    presentations.push(d.total_presentations);

    showRates.push(
      d.appointments_start
        ? (d.total_presentations / d.appointments_start) * 100
        : 0
    );

    pres += d.total_presentations;
    sales += d.total_sales;
    alp += d.total_alp;
    refs += d.referrals_collected;
    apptStart += d.appointments_start;
  });

  /* ================= WEEKLY KPI CARDS ================= */

  wk_pres.innerText = pres;
  wk_sales.innerText = sales;
  wk_show.innerText = apptStart
    ? Math.round(pres / apptStart * 100) + "%"
    : "0%";
  wk_close.innerText = pres
    ? Math.round(sales / pres * 100) + "%"
    : "0%";
  wk_alp.innerText = sales
    ? "$" + Math.round(alp / sales)
    : "$0";
  wk_refs.innerText = pres
    ? (refs / pres).toFixed(2)
    : "0";

  /* ================= WEEKLY CHARTS ================= */

  drawChart({
    canvasId: "salesChart",
    type: "line",
    labels,
    data: salesTrend,
    title: "Daily Sales Trend"
  });

  drawChart({
    canvasId: "presentationsChart",
    type: "bar",
    labels,
    data: presentations,
    title: "Presentations per Day"
  });

  drawChart({
    canvasId: "showRatioChart",
    type: "line",
    labels,
    data: showRates,
    title: "Show Ratio (%)"
  });

  drawChart({
    canvasId: "closingPieChart",
    type: "pie",
    labels: ["Closed Sales", "Not Closed"],
    data: [sales, Math.max(pres - sales, 0)],
    title: "Weekly Closing Ratio"
  });

  drawChart({
    canvasId: "showRatioPieChart",
    type: "pie",
    labels: ["Shows", "No Shows"],
    data: [
      pres,
      Math.max(apptStart - pres, 0)
    ],
    title: "Weekly Show Ratio"
  });

  drawChart({
    canvasId: "alpYTDChart",
    type: "line",
    labels: ytdLabels,
    data: ytdAlpPerSale,
    title: "Year-to-Date ALP per Sale"
  });

  drawChart({
    canvasId: "weeklySalesClosingChart",
    type: "line",
    labels,
    datasets: [
      {
        label: "Sales",
        data: salesTrend,
        yAxisID: "ySales"
      },
      {
        label: "Closing Ratio %",
        data: labels.map(() =>
          pres ? (sales / pres) * 100 : 0
        ),
        yAxisID: "yPercent"
      }
    ],
    title: "Weekly Sales & Closing Ratio",
    scales: {
      ySales: { beginAtZero:true, position:"left" },
      yPercent: { beginAtZero:true, max:100, position:"right" }
    }
  });




  /* ================= YEAR-TO-DATE AGGREGATION (NEW) ================= */

  const currentYear = new Date().getFullYear();
  const ytdLogs = data.filter(d =>
    new Date(d.date).getFullYear() === currentYear
  );

  const ytdWeeks = {};

  ytdLogs.forEach(d => {

    const date = new Date(d.date + "T00:00:00");
    const weekStart = new Date(date);
    const day = weekStart.getDay() === 0 ? 7 : weekStart.getDay();
    weekStart.setDate(weekStart.getDate() - day + 1);
    weekStart.setHours(0,0,0,0);

    const key = weekStart.toISOString().split("T")[0];
    if (!ytdWeeks[key]) ytdWeeks[key] = [];
    ytdWeeks[key].push(d);
  });

  const ytdLabels = [];
  const ytdSales = [];
  const ytdClosingRatio = [];
  const ytdAlpPerSale = [];

  Object.keys(ytdWeeks).sort().forEach(week => {

    let wSales = 0;
    let wPres = 0;
    let wAlp = 0;

    ytdWeeks[week].forEach(d => {
      wSales += d.total_sales;
      wPres += d.total_presentations;
      wAlp += d.total_alp;
    });

    ytdLabels.push(week);
    ytdSales.push(wSales);
    ytdClosingRatio.push(wPres ? (wSales / wPres) * 100 : 0);
    ytdAlpPerSale.push(wSales ? wAlp / wSales : 0);
  });

  /* ================= YTD CHART (MATCHES PHOTOS) ================= */

  drawChart({
    canvasId: "salesClosingYTD",
    type: "line",
    labels: ytdLabels,
    datasets: [
      {
        label: "Sales",
        data: ytdSales,
        yAxisID: "ySales"
      },
      {
        label: "Closing Ratio %",
        data: ytdClosingRatio,
        yAxisID: "yPercent"
      }
    ],
    title: "Year-to-Date Sales & Closing Ratio",
    scales: {
      ySales: { beginAtZero: true, position: "left" },
      yPercent: { beginAtZero: true, max: 100, position: "right" }
    }
  });
}


/* ================= CHART ================= */

function drawChart({
  canvasId,
  type = "line",
  labels,
  data,
  label = "",
  title = "",
  colors = {}
}) {

  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  // destroy only THIS canvas's chart
  if (canvas._chart) {
    canvas._chart.destroy();
  }

  canvas._chart = new Chart(canvas, {
    type,
    data: {
      labels,
      datasets: [{
        label,
        data,
        backgroundColor: colors.bg || "#3b82f6",
        borderColor: colors.border || "#3b82f6",
        borderWidth: 3,
        tension: 0.35,
        pointRadius: type === "line" ? 5 : 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: !!label },
        title: {
          display: !!title,
          text: title,
          font: { 
            size: 16,
            weight: "600"
          },
          padding: {
            top: 10,
            bottom: 20
          }
        }
      },
      scales: type !== "pie"
        ? { y: { beginAtZero: true } }
        : {}
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

 if(typeof weekSelect!=="undefined") loadWeekly();
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
