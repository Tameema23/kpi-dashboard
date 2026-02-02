if (!localStorage.getItem("token") && !window.location.href.includes("login")) {
  window.location.href = "login.html";
}

const API = "https://data-log.onrender.com";
const API_BASE = API;
const TOKEN = localStorage.getItem("token");

if (!TOKEN && !location.pathname.includes("login")) {
  location.href = "login.html";
}

let chartInstance = null;

/* ================= TIME ================= */

function getCalgaryToday() {
  return new Date(
    new Date().toLocaleString("en-US", { timeZone: "America/Edmonton" })
  ).toISOString().split("T")[0]
}


/* ================= WEEKLY ================= */

async function loadWeekly() {

  const res = await fetch(`${API_BASE}/history`, {
    headers: {
      "Authorization": "Bearer " + TOKEN
    }
  });

  const data = await res.json();

  if (!data.length) {
    drawChart(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], [0,0,0,0,0,0,0]);
    return;
  }

  const weeks = {};

  data.forEach(d => {

    const date = new Date(
      new Date(d.date + "T00:00:00").toLocaleString(
        "en-US",{ timeZone:"America/Edmonton" }
      )
    );

    const weekStart = new Date(date);
    const day = weekStart.getDay() === 0 ? 7 : weekStart.getDay();
    weekStart.setDate(weekStart.getDate() - day + 1);
    weekStart.setHours(0,0,0,0);

    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate() + 6);

    if(date >= weekStart && date <= weekEnd){
      const key = weekStart.toLocaleDateString("en-CA");
      if(!weeks[key]) weeks[key]=[];
      weeks[key].push(d);
    }
  });

  const select = weekSelect;
  const prev = select.value;
  select.innerHTML="";

  const sortedWeeks = Object.keys(weeks).sort(
    (a,b)=>new Date(b+"T12:00:00")-new Date(a+"T12:00:00")
  );

  sortedWeeks.forEach(start=>{

    const weekStart = new Date(
      new Date(start+"T00:00:00").toLocaleString(
        "en-US",{ timeZone:"America/Edmonton" }
      )
    );

    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate()+6);

    const opt=document.createElement("option");
    opt.value=start;
    opt.text=`${formatDate(weekStart)} – ${formatDate(weekEnd)}`;

    if(start===prev) opt.selected=true;
    select.appendChild(opt);
  });

  const chosen = select.value || sortedWeeks[0];
  const weekData = weeks[chosen].sort(
    (a,b)=>new Date(a.date)-new Date(b.date)
  );

  let labels=[], salesTrend=[];
  let pres=0,sales=0,alp=0,refs=0,apptFinish=0;

  weekData.forEach(d=>{
    labels.push(d.date);
    salesTrend.push(d.total_sales);

    pres+=d.total_presentations;
    sales+=d.total_sales;
    alp+=d.total_alp;
    refs+=d.referrals_collected;
    apptFinish+=d.appointments_finish;
  });

  wk_pres.innerText=pres;
  wk_sales.innerText=sales;
  wk_show.innerText=apptFinish?Math.round(pres/apptFinish*100)+"%":"0%";
  wk_close.innerText=pres?Math.round(sales/pres*100)+"%":"0%";
  wk_alp.innerText=sales?"$"+Math.round(alp/sales):"$0";
  wk_refs.innerText=pres?(refs/pres).toFixed(2):"0";

  drawChart(labels,salesTrend);
}

/* ================= CHART ================= */

function drawChart(labels,data){

  if(chartInstance) chartInstance.destroy();

  chartInstance=new Chart(kpiChart,{
    type:"line",
    data:{
      labels,
      datasets:[{
        data,
        borderWidth:3,
        tension:.35,
        pointRadius:5
      }]
    },
    options:{
      scales:{ y:{beginAtZero:true}},
      plugins:{legend:{display:false}}
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
    const err = await res.text();
    console.error(err);
    alert("Save failed — check console");
  }
}

/* ================= HISTORY ================= */

async function loadHistory(){

 const res = await fetch(`${API_BASE}/history`,{
   headers:{
     "Authorization":"Bearer "+TOKEN
   }
 });

 const data = await res.json();

 historyBody.innerHTML="";

 data.forEach(d=>{
  historyBody.innerHTML+=`
   <tr>
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
    <td><button class="btn small" onclick="editDay('${d.date}')">Edit</button></td>
   </tr>`;
 });
}

/* ================= HELPERS ================= */

function editDay(d){
 localStorage.setItem("editDate",d);
 location.href="log.html";
}

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

 if(typeof weekSelect!=="undefined") loadWeekly();
 if(typeof historyBody!=="undefined") loadHistory();
};

/* ================= LOGOUT ================= */

function logout() {
  localStorage.removeItem("token");
  window.location.href = "/";
}

window.logout = logout;

async function exportExcel() {
  const token = localStorage.getItem("token")

  const res = await fetch("/history", {
    headers: { Authorization: "Bearer " + token }
  })

  if (!res.ok) {
    alert("Failed to fetch data")
    return
  }

  const data = await res.json()

  if (data.length === 0) {
    alert("No data to export yet")
    return
  }

  const headers = Object.keys(data[0]).filter(k => k !== "id" && k !== "user_id")

  let csv = headers.join(",") + "\n"

  data.forEach(row => {
    csv += headers.map(h => row[h]).join(",") + "\n"
  })

  const blob = new Blob([csv], { type: "text/csv" })
  const url = window.URL.createObjectURL(blob)

  const a = document.createElement("a")
  a.href = url
  a.download = "kpi_data.csv"
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

