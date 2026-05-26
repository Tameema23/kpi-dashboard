/*
 * quality.js — Quality Tracker page logic
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
  var entriesCache = [];
  var editingId    = null;
  var activeFilter = "all";

  // ── Helpers ───────────────────────────────────────────────────
  function esc(str) {
    if (!str) return "";
    return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function fmtDateDisplay(d) {
    if (!d) return "";
    try {
      return new Date(d + (d.length === 10 ? "T00:00" : "")).toLocaleDateString("en-CA");
    } catch(e) { return d; }
  }

  // ── Due date logic ────────────────────────────────────────────
  function daysUntilDue(dueDateStr) {
    if (!dueDateStr) return null;
    var today = new Date(); today.setHours(0,0,0,0);
    var due   = new Date(dueDateStr + "T00:00:00");
    return Math.round((due - today) / (1000 * 60 * 60 * 24));
  }

  function getDueClass(dueDateStr) {
    var days = daysUntilDue(dueDateStr);
    if (days === null) return null;
    if (days >= 10) return "green";
    if (days >= 5)  return "yellow";
    return "red";
  }

  function dueBadgeHtml(dueDateStr) {
    if (!dueDateStr) return '<span class="due-badge none">No due date</span>';
    var days = daysUntilDue(dueDateStr);
    var cls  = getDueClass(dueDateStr);
    var label;
    if (days < 0)       label = Math.abs(days) + "d overdue";
    else if (days === 0) label = "Due today";
    else                 label = days + "d left";
    return '<span class="due-badge ' + cls + '">' +
      '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>' +
      label + '</span>';
  }

  // ── Action history parsing ────────────────────────────────────
  // Format: "BY:username\nDATE:May 25, 2026 at 02:00 PM\nNOTE:text\n===ENTRY===\n..."
  function parseActionHistory(raw) {
    if (!raw || !raw.trim()) return [];
    var blocks = raw.indexOf("===ENTRY===") !== -1
      ? raw.split("===ENTRY===")
      : [raw];
    return blocks.map(function(block) {
      var b = block.trim();
      if (!b) return null;
      if (b.indexOf("BY:") !== 0) return { by: "", date: "", note: b };
      var byStart   = b.indexOf("BY:")   + 3;
      var dateStart = b.indexOf("DATE:");
      var noteStart = b.indexOf("NOTE:");
      var by   = (dateStart > -1 ? b.slice(byStart, dateStart) : b.slice(byStart)).trim();
      var date = dateStart > -1
        ? (noteStart > -1 ? b.slice(dateStart + 5, noteStart) : b.slice(dateStart + 5)).trim()
        : "";
      var note = noteStart > -1 ? b.slice(noteStart + 5).trim() : "";
      return { by: by, date: date, note: note };
    }).filter(Boolean);
  }

  function renderActionHistory(entries) {
    var wrap = document.getElementById("f_action_history_entries");
    wrap.innerHTML = "";
    entries.forEach(function(e, i) {
      var isFirst = (i === 0);
      var div = document.createElement("div");
      div.style.cssText = [
        "border-radius:10px",
        "padding:10px 13px",
        "border:1.5px solid " + (isFirst ? "#bfdbfe" : "#f1f5f9"),
        "background:"         + (isFirst ? "#eff6ff" : "#fafafa"),
      ].join(";");

      var meta = "";
      if (e.by || e.date) {
        meta = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:' + (e.note ? "5px" : "0") + ';">';
        if (isFirst) meta += '<span style="font-size:10px;font-weight:700;background:#2563eb;color:#fff;padding:1px 7px;border-radius:20px;">Latest</span>';
        if (e.by)   meta += '<span style="font-size:11px;font-weight:700;color:' + (isFirst ? "#1d4ed8" : "#64748b") + ';">' + esc(e.by) + '</span>';
        if (e.date) meta += '<span style="font-size:11px;color:#94a3b8;">' + esc(e.date) + '</span>';
        meta += '</div>';
      }
      var noteHtml = e.note
        ? '<div style="font-size:13px;color:' + (isFirst ? "#1e3a8a" : "#475569") + ';line-height:1.55;white-space:pre-wrap;">' + esc(e.note) + '</div>'
        : '<div style="font-size:12px;color:#94a3b8;font-style:italic;">No note</div>';
      div.innerHTML = meta + noteHtml;
      wrap.appendChild(div);
    });
  }

  // Latest action note for table display (first entry's note)
  function latestActionNote(raw) {
    if (!raw || !raw.trim()) return "";
    var entries = parseActionHistory(raw);
    if (!entries.length) return "";
    return entries[0].note || "";
  }

  // ── Excel Export ──────────────────────────────────────────────
  window.exportQualityExcel = function() {
    if (!entriesCache || entriesCache.length === 0) { showToast("No entries to export.", "error"); return; }
    var rows = [["Date","Insured Name","Policy #","Remarks","Phone","Follow Up","Action (Latest)","Due Date","ALP"]];
    entriesCache.forEach(function(e) {
      rows.push([
        e.date          || "",
        e.insured_name  || "",
        e.policy_number || "",
        e.remarks       || "",
        e.phone_number  || "",
        e.follow_up     || "",
        latestActionNote(e.action) || "",
        e.due_date      || "",
        e.alp           || ""
      ]);
    });
    var wb = XLSX.utils.book_new();
    var ws = XLSX.utils.aoa_to_sheet(rows);
    ws["!cols"] = [12,22,16,20,16,14,35,12,12].map(function(w) { return {wch:w}; });
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

  // ── Filter ────────────────────────────────────────────────────
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
                e.date||"", e.phone_number||"", e.follow_up||"",
                latestActionNote(e.action)||"", e.alp||""]
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

  window.setFilter = function(f) { activeFilter = f; applyFilter(); };

  // ── Render table ──────────────────────────────────────────────
  function renderTable(entries) {
    var tbody = document.getElementById("qualityBody");
    if (!entries || entries.length === 0) {
      tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#94a3b8;padding:40px 0;font-size:14px;">No entries found.</td></tr>';
      return;
    }
    tbody.innerHTML = entries.map(function(e) {
      var dueClass   = getDueClass(e.due_date);
      var rowClass   = dueClass ? "quality-row-" + dueClass : "";
      var actionNote = latestActionNote(e.action);
      var hasHistory = parseActionHistory(e.action).length > 1;
      return '<tr class="' + rowClass + '">' +
        '<td style="white-space:nowrap;font-weight:600;color:#475569;">'                         + fmtDateDisplay(e.date)   + '</td>' +
        '<td style="font-weight:700;color:#0f172a;">'                                            + esc(e.insured_name)      + '</td>' +
        '<td style="font-family:monospace;font-size:13px;color:#475569;">'                       + esc(e.policy_number)     + '</td>' +
        '<td>'                                                                                   + esc(e.remarks)           + '</td>' +
        '<td>'                                                                                   + esc(e.phone_number)      + '</td>' +
        '<td>' + (e.follow_up ? '<span style="background:#eff6ff;color:#2563eb;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;">' + esc(e.follow_up) + '</span>' : '') + '</td>' +
        '<td style="max-width:200px;white-space:normal;line-height:1.4;">' +
          esc(actionNote) +
          (hasHistory ? '<div style="margin-top:3px;"><span style="font-size:10px;font-weight:700;background:#f1f5f9;color:#64748b;padding:1px 6px;border-radius:10px;">+ history</span></div>' : '') +
        '</td>' +
        '<td style="white-space:nowrap;">'                                                       + dueBadgeHtml(e.due_date) + '</td>' +
        '<td style="font-weight:700;color:#16a34a;">'                                            + (e.alp ? "$" + esc(e.alp) : "") + '</td>' +
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
    // Clear all fields
    ["f_insured_name","f_policy_number","f_remarks",
     "f_due_date","f_phone_number","f_follow_up","f_action","f_alp"].forEach(function(id) {
      document.getElementById(id).value = "";
    });
    // Auto-fill with today's date in Mountain Time
    document.getElementById("f_date").value = new Date().toLocaleDateString("en-CA", { timeZone: "America/Edmonton" });
    // Hide action history
    document.getElementById("f_action_history_wrap").style.display = "none";
    document.getElementById("f_action_label").innerText = "Action";
    document.getElementById("f_action").placeholder = "Describe the action to take...";
    document.getElementById("modalMsg").innerText = "";
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
    document.getElementById("f_alp").value           = entry.alp           || "";

    // Store existing raw action on the modal
    document.getElementById("qualityModal").dataset.existingAction = entry.action || "";

    // Parse and render history
    var history = parseActionHistory(entry.action || "");
    if (history.length > 0) {
      renderActionHistory(history);
      document.getElementById("f_action_history_wrap").style.display = "block";
      document.getElementById("f_action_label").innerText = "Add New Action Note (optional)";
      document.getElementById("f_action").placeholder = "What changed? Add an update...";
    } else {
      document.getElementById("f_action_history_wrap").style.display = "none";
      document.getElementById("f_action_label").innerText = "Action";
      document.getElementById("f_action").placeholder = "Describe the action to take...";
    }
    document.getElementById("f_action").value = "";
    document.getElementById("modalMsg").innerText = "";
    document.getElementById("qualityModal").classList.remove("hidden");
  };

  window.closeModal = function() {
    document.getElementById("qualityModal").classList.add("hidden");
    editingId = null;
  };

  window.saveEntry = async function() {
    var name = document.getElementById("f_insured_name").value.trim();
    var msg  = document.getElementById("modalMsg");
    if (!name) { msg.innerText = "Insured name is required."; return; }

    var newActionText = document.getElementById("f_action").value.trim();
    var finalAction;

    if (editingId) {
      // Build new history entry and prepend to existing
      var existingRaw = document.getElementById("qualityModal").dataset.existingAction || "";
      var now = new Date();
      var dateStr = now.toLocaleDateString("en-CA", {
        timeZone: "America/Edmonton", month: "short", day: "numeric", year: "numeric"
      });
      var timeStr = now.toLocaleTimeString("en-CA", {
        timeZone: "America/Edmonton", hour: "2-digit", minute: "2-digit", hour12: true
      });
      var updatedBy = localStorage.getItem("username") || "unknown";
      var newEntry = "BY:" + updatedBy + "\nDATE:" + dateStr + " at " + timeStr + "\nNOTE:" + newActionText;
      if (existingRaw.trim()) {
        finalAction = newEntry + "\n===ENTRY===\n" + existingRaw.trim();
      } else {
        finalAction = newEntry;
      }
    } else {
      // New entry — wrap in history format right away
      var now = new Date();
      var dateStr = now.toLocaleDateString("en-CA", {
        timeZone: "America/Edmonton", month: "short", day: "numeric", year: "numeric"
      });
      var timeStr = now.toLocaleTimeString("en-CA", {
        timeZone: "America/Edmonton", hour: "2-digit", minute: "2-digit", hour12: true
      });
      var updatedBy = localStorage.getItem("username") || "unknown";
      finalAction = "BY:" + updatedBy + "\nDATE:" + dateStr + " at " + timeStr + "\nNOTE:" + newActionText;
    }

    var payload = {
      insured_name:  name,
      policy_number: document.getElementById("f_policy_number").value.trim(),
      remarks:       document.getElementById("f_remarks").value.trim(),
      date:          document.getElementById("f_date").value,
      due_date:      document.getElementById("f_due_date").value,
      phone_number:  document.getElementById("f_phone_number").value.trim(),
      follow_up:     document.getElementById("f_follow_up").value.trim(),
      action:        finalAction,
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