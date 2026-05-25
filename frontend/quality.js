/*
 * quality.js — Quality Tracker page logic
 *
 * Depends on app.js (must load first):
 *   - TOKEN, showToast(), showConfirm(), renderQualityAnalytics(), applyQualityDueIndicators()
 *
 * Depends on XLSX (loaded in quality.html).
 */

(function () {

  // ── Init ─────────────────────────────────────────────────────
  var u = localStorage.getItem("username");
  if (u) document.getElementById("username-text").innerText = u;

  if (localStorage.getItem("role") === "assistant") {
    document.querySelectorAll(".admin-only").forEach(function(el) { el.style.display = "none"; });
    if (localStorage.getItem("can_planner") === "1")
      document.querySelectorAll("a[href='/planner.html']").forEach(function(el) { el.style.display = ""; });
    document.querySelectorAll("a[href='/settings.html']").forEach(function(el) { el.style.display = ""; });
  }

  // ── State ─────────────────────────────────────────────────────
  var entriesCache  = [];
  var editingId     = null;
  var activeFilter  = "all"; // "all" | "due-soon"

  // ── Helpers ───────────────────────────────────────────────────
  function esc(str) {
    if (!str) return "";
    return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function fmtDate(d) {
    if (!d) return "";
    try {
      return new Date(d + (d.length === 10 ? "T00:00" : "")).toLocaleDateString("en-CA");
    } catch(e) { return d; }
  }

  // Days until due: positive = future, 0 = today, negative = overdue
  function daysUntilDue(dueDateStr) {
    if (!dueDateStr) return null;
    var today = new Date(); today.setHours(0,0,0,0);
    var due   = new Date(dueDateStr + "T00:00:00");
    return Math.round((due - today) / (1000 * 60 * 60 * 24));
  }

  // Returns "green" | "yellow" | "red" | null
  function getDueClass(dueDateStr) {
    var days = daysUntilDue(dueDateStr);
    if (days === null) return null;
    if (days >= 10)  return "green";
    if (days >= 5)   return "yellow";
    return "red"; // 0–4 days or overdue
  }

  function dueBadgeHtml(dueDateStr) {
    if (!dueDateStr) return '<span class="due-badge none">No due date</span>';
    var days   = daysUntilDue(dueDateStr);
    var cls    = getDueClass(dueDateStr);
    var label;
    if (days < 0)      label = Math.abs(days) + "d overdue";
    else if (days === 0) label = "Due today";
    else                 label = days + "d left";
    return '<span class="due-badge ' + cls + '">' +
      '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>' +
      label + '</span>';
  }

  // ── Excel Export ──────────────────────────────────────────────
  window.exportQualityExcel = function() {
    if (!entriesCache || entriesCache.length === 0) { showToast("No entries to export.", "error"); return; }
    var rows = [["Insured Name","Policy #","Remarks","Date","Due Date","Phone Number","Follow Up","Action","ALP"]];
    entriesCache.forEach(function(e) {
      rows.push([e.insured_name||"", e.policy_number||"", e.remarks||"", e.date||"",
                 e.due_date||"", e.phone_number||"", e.follow_up||"", e.action||"", e.alp||""]);
    });
    var wb = XLSX.utils.book_new();
    var ws = XLSX.utils.aoa_to_sheet(rows);
    ws["!cols"] = [22,16,20,12,12,16,14,30,12].map(function(w) { return {wch:w}; });
    XLSX.utils.book_append_sheet(wb, ws, "Quality Tracker");
    var today = new Date().toLocaleDateString("en-CA").replace(/\//g, "-");
    XLSX.writeFile(wb, "quality_tracker_" + today + ".xlsx");
    showToast("Excel exported!");
  };

  // ── Load entries ──────────────────────────────────────────────
  async function loadEntries() {
    try {
      var res = await fetch("/quality", { headers: { Authorization: "Bearer " + TOKEN } });
      if (!res.ok) return;
      entriesCache = await res.json();
      renderQualityAnalytics(entriesCache);
      applyFilter();
    } catch(e) { console.error(e); }
  }

  // ── Filter: all vs due-soon ───────────────────────────────────
  function applyFilter() {
    var q = (document.getElementById("qualitySearchInput").value || "").trim().toLowerCase();
    var source = activeFilter === "due-soon"
      ? entriesCache.filter(function(e) {
          var cls = getDueClass(e.due_date);
          return cls === "yellow" || cls === "red";
        })
      : entriesCache;

    if (q) {
      source = source.filter(function(e) {
        return [e.insured_name||"", e.policy_number||"", e.remarks||"",
                e.date||"", e.phone_number||"", e.follow_up||"", e.action||"", e.alp||""]
          .some(function(v) { return v.toLowerCase().indexOf(q) !== -1; });
      });
    }
    renderTable(source, q);
    updateFilterBtns();
    var countEl = document.getElementById("qualitySearchCount");
    if (countEl) {
      if (q && source.length === 0) {
        countEl.innerHTML = "<span style='color:#dc2626;'>No results for <strong>\u201c" + esc(q) + "\u201d</strong></span>";
      } else if (q) {
        countEl.innerHTML = "<span style='color:#2563eb;font-weight:600;'>" + source.length + "</span> result" + (source.length===1?"":"s") + " for <strong>\u201c" + esc(q) + "\u201d</strong>";
      } else {
        countEl.innerText = "";
      }
    }
    if (q && source.length > 0) highlightQualityMatches(q);
  }

  function updateFilterBtns() {
    var allBtn  = document.getElementById("filterAllBtn");
    var soonBtn = document.getElementById("filterDueSoonBtn");
    if (!allBtn || !soonBtn) return;
    var dueCount = entriesCache.filter(function(e) {
      var cls = getDueClass(e.due_date);
      return cls === "yellow" || cls === "red";
    }).length;
    allBtn.classList.toggle("filter-btn-active", activeFilter === "all");
    soonBtn.classList.toggle("filter-btn-active", activeFilter === "due-soon");
    soonBtn.querySelector(".filter-count").innerText = dueCount > 0 ? dueCount : "";
  }

  window.setFilter = function(f) {
    activeFilter = f;
    applyFilter();
  };

  // ── Render table ──────────────────────────────────────────────
  function renderTable(entries, highlightQuery) {
    var tbody = document.getElementById("qualityBody");
    if (!entries || entries.length === 0) {
      tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#94a3b8;padding:40px 0;font-size:14px;">No entries found.</td></tr>';
      return;
    }
    tbody.innerHTML = entries.map(function(e) {
      var dueClass = getDueClass(e.due_date);
      var rowClass = dueClass ? "quality-row-" + dueClass : "";
      return '<tr class="' + rowClass + '">' +
        '<td style="font-weight:700;color:#0f172a;">'                                         + esc(e.insured_name)  + '</td>' +
        '<td style="font-family:monospace;font-size:13px;color:#475569;">'                    + esc(e.policy_number) + '</td>' +
        '<td>'                                                                                 + esc(e.remarks)       + '</td>' +
        '<td style="white-space:nowrap;">'                                                    + fmtDate(e.date)      + '</td>' +
        '<td style="white-space:nowrap;">'                                                    + dueBadgeHtml(e.due_date) + '</td>' +
        '<td>'                                                                                 + esc(e.phone_number)  + '</td>' +
        '<td>' + (e.follow_up ? '<span style="background:#eff6ff;color:#2563eb;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;">' + esc(e.follow_up) + '</span>' : '') + '</td>' +
        '<td style="max-width:180px;white-space:normal;line-height:1.4;">'                    + esc(e.action)        + '</td>' +
        '<td style="font-weight:700;color:#16a34a;">'                                         + (e.alp ? "$" + esc(e.alp) : "") + '</td>' +
        '<td style="text-align:center;">' +
          '<button class="btn small" style="background:#eff6ff;color:#2563eb;" onclick="openEditModal(' + e.id + ')" title="Edit">' +
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
          '</button>' +
        '</td>' +
        '<td style="text-align:center;">' +
          '<button class="btn small" style="background:#fee2e2;color:#dc2626;" onclick="deleteEntry(' + e.id + ',\'' + esc(e.insured_name) + '\')" title="Delete">' +
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>' +
          '</button>' +
        '</td>' +
      '</tr>';
    }).join("");
  }

  // ── Modal ─────────────────────────────────────────────────────
  window.openAddModal = function() {
    editingId = null;
    document.getElementById("modalTitle").innerText = "Add Entry";
    clearForm();
    document.getElementById("qualityModal").classList.remove("hidden");
  };

  window.openEditModal = function(id) {
    var entry = entriesCache.find(function(e) { return e.id === id; });
    if (!entry) return;
    editingId = id;
    document.getElementById("modalTitle").innerText = "Edit Entry";
    document.getElementById("f_insured_name").value  = entry.insured_name  || "";
    document.getElementById("f_policy_number").value = entry.policy_number || "";
    document.getElementById("f_remarks").value       = entry.remarks       || "";
    document.getElementById("f_date").value          = entry.date          || "";
    document.getElementById("f_due_date").value      = entry.due_date      || "";
    document.getElementById("f_phone_number").value  = entry.phone_number  || "";
    document.getElementById("f_follow_up").value     = entry.follow_up     || "";
    document.getElementById("f_action").value        = entry.action        || "";
    document.getElementById("f_alp").value           = entry.alp           || "";
    document.getElementById("modalMsg").innerText = "";
    document.getElementById("qualityModal").classList.remove("hidden");
  };

  window.closeModal = function() {
    document.getElementById("qualityModal").classList.add("hidden");
    editingId = null;
  };

  function clearForm() {
    ["f_insured_name","f_policy_number","f_remarks","f_date","f_due_date",
     "f_phone_number","f_follow_up","f_action","f_alp"].forEach(function(id) {
      document.getElementById(id).value = "";
    });
    document.getElementById("modalMsg").innerText = "";
  }

  window.saveEntry = async function() {
    var name = document.getElementById("f_insured_name").value.trim();
    var msg  = document.getElementById("modalMsg");
    if (!name) { msg.innerText = "Insured name is required."; return; }

    var payload = {
      insured_name:  name,
      policy_number: document.getElementById("f_policy_number").value.trim(),
      remarks:       document.getElementById("f_remarks").value.trim(),
      date:          document.getElementById("f_date").value,
      due_date:      document.getElementById("f_due_date").value,
      phone_number:  document.getElementById("f_phone_number").value.trim(),
      follow_up:     document.getElementById("f_follow_up").value.trim(),
      action:        document.getElementById("f_action").value.trim(),
      alp:           document.getElementById("f_alp").value.trim()
    };

    try {
      var url    = editingId ? "/quality/" + editingId : "/quality";
      var method = editingId ? "PUT" : "POST";
      var res = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        window.closeModal();
        showToast(editingId ? "Entry updated!" : "Entry added!");
        loadEntries();
      } else {
        var d = await res.json();
        msg.innerText = d.detail || "Failed to save.";
      }
    } catch(e) { msg.innerText = "Server error."; }
  };

  window.deleteEntry = function(id, name) {
    showConfirm(
      "Delete the entry for <strong>" + esc(name) + "</strong>? This cannot be undone.",
      async function() {
        try {
          var res = await fetch("/quality/" + id, {
            method: "DELETE", headers: { Authorization: "Bearer " + TOKEN }
          });
          if (res.ok) { showToast(name + " deleted."); loadEntries(); }
          else showToast("Failed to delete.", "error");
        } catch(e) { showToast("Server error.", "error"); }
      },
      { confirmText: "Delete" }
    );
  };

  // ── Search ────────────────────────────────────────────────────
  window.filterQualityTable = function(query) {
    var clearBtn = document.getElementById("qualityClearBtn");
    if (clearBtn) clearBtn.style.display = query ? "flex" : "none";
    applyFilter();
  };

  window.clearQualitySearch = function() {
    var input = document.getElementById("qualitySearchInput");
    if (input) { input.value = ""; input.focus(); }
    applyFilter();
  };

  function highlightQualityMatches(query) {
    if (!query) return;
    var tbody = document.getElementById("qualityBody");
    if (!tbody) return;
    tbody.querySelectorAll("td").forEach(function(cell) {
      if (cell.querySelector("button") || cell.querySelector(".due-badge")) return;
      var text = cell.textContent;
      if (!text) return;
      var safe  = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      var regex = new RegExp("(" + safe + ")", "gi");
      if (!regex.test(text)) return;
      var parts = text.split(new RegExp("(" + safe + ")", "gi"));
      cell.innerHTML = parts.map(function(part, i) {
        return i % 2 === 1 ? '<mark class="q-highlight">' + esc(part) + '</mark>' : esc(part);
      }).join("");
    });
  }

  // ── Keyboard shortcuts ────────────────────────────────────────
  document.addEventListener("keydown", function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "f") {
      var input = document.getElementById("qualitySearchInput");
      if (input) { e.preventDefault(); input.focus(); input.select(); }
    }
    if (e.key === "Escape") {
      var input = document.getElementById("qualitySearchInput");
      if (document.activeElement === input) { window.clearQualitySearch(); input.blur(); }
    }
  });

  document.getElementById("qualityModal").addEventListener("click", function(e) {
    if (e.target === this) window.closeModal();
  });

  // ── Boot ──────────────────────────────────────────────────────
  loadEntries();

})();