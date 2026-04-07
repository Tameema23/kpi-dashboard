/*
 * quality.js — Quality Tracker page logic
 *
 * Depends on app.js (must load first):
 *   - TOKEN                    : auth token
 *   - showToast()              : toast notifications
 *   - showConfirm()            : confirmation dialogs
 *   - renderQualityAnalytics() : analytics summary cards
 *   - applyQualityDueIndicators() : overdue row indicators
 *
 * Depends on XLSX library (loaded in quality.html):
 *   - XLSX                     : Excel export
 *
 * Functions exposed to window (called via onclick/oninput in HTML):
 *   - exportQualityExcel()
 *   - openAddModal()
 *   - openEditModal(id)
 *   - closeModal()
 *   - saveEntry()
 *   - deleteEntry(id, name)
 *   - filterQualityTable(query)
 *   - clearQualitySearch()
 */

(function () {

  // ── Init: username & role-based nav ──────────────────────────
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

  // ── Helpers ───────────────────────────────────────────────────
  function esc(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function fmtDate(d) {
    if (!d) return "";
    try {
      return new Date(d + (d.length === 10 ? "T00:00" : ""))
        .toLocaleDateString("en-CA");
    } catch(e) { return d; }
  }

  // ── Excel Export ──────────────────────────────────────────────
  window.exportQualityExcel = function() {
    if (!entriesCache || entriesCache.length === 0) {
      showToast("No entries to export.", "error");
      return;
    }
    var rows = [["Insured Name","Policy #","Remarks","Date","Phone Number","Follow Up","Action","ALP"]];
    entriesCache.forEach(function(e) {
      rows.push([
        e.insured_name  || "",
        e.policy_number || "",
        e.remarks       || "",
        e.date          || "",
        e.phone_number  || "",
        e.follow_up     || "",
        e.action        || "",
        e.alp           || ""
      ]);
    });
    var wb = XLSX.utils.book_new();
    var ws = XLSX.utils.aoa_to_sheet(rows);
    ws["!cols"] = [22,16,20,12,16,14,30,12].map(function(w) { return {wch:w}; });
    XLSX.utils.book_append_sheet(wb, ws, "Quality Tracker");
    var today = new Date().toLocaleDateString("en-CA").replace(/\//g, "-");
    XLSX.writeFile(wb, "quality_tracker_" + today + ".xlsx");
    showToast("Excel exported!");
  };

  // ── Load entries ──────────────────────────────────────────────
  async function loadEntries() {
    try {
      var res = await fetch("/quality", {
        headers: { Authorization: "Bearer " + TOKEN }
      });
      if (!res.ok) return;
      entriesCache = await res.json();
      renderQualityAnalytics(entriesCache);
      renderTable(entriesCache);
      if (typeof applyQualityDueIndicators === "function") applyQualityDueIndicators(entriesCache);
    } catch(e) { console.error(e); }
  }

  // ── Render table ──────────────────────────────────────────────
  function renderTable(entries) {
    var tbody = document.getElementById("qualityBody");
    if (!entries || entries.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#94a3b8;padding:40px 0;font-size:14px;">No entries yet. Click \u201cAdd Entry\u201d to get started.</td></tr>';
      return;
    }
    tbody.innerHTML = entries.map(function(e) {
      return '<tr>' +
        '<td style="font-weight:700;color:#0f172a;">'                                          + esc(e.insured_name)  + '</td>' +
        '<td style="font-family:monospace;font-size:13px;color:#475569;">'                     + esc(e.policy_number) + '</td>' +
        '<td>'                                                                                  + esc(e.remarks)       + '</td>' +
        '<td style="white-space:nowrap;">'                                                     + fmtDate(e.date)      + '</td>' +
        '<td>'                                                                                  + esc(e.phone_number)  + '</td>' +
        '<td>' + (e.follow_up ? '<span style="background:#eff6ff;color:#2563eb;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;">' + esc(e.follow_up) + '</span>' : '') + '</td>' +
        '<td style="max-width:180px;white-space:normal;line-height:1.4;">'                     + esc(e.action)        + '</td>' +
        '<td style="font-weight:700;color:#16a34a;">'                                          + (e.alp ? "$" + esc(e.alp) : "") + '</td>' +
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
    ["f_insured_name","f_policy_number","f_remarks","f_date",
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
            method: "DELETE",
            headers: { Authorization: "Bearer " + TOKEN }
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
    var countEl  = document.getElementById("qualitySearchCount");
    var q        = (query || "").trim().toLowerCase();

    if (clearBtn) clearBtn.style.display = q ? "flex" : "none";

    if (!q) {
      renderTable(entriesCache);
      if (typeof applyQualityDueIndicators === "function") applyQualityDueIndicators(entriesCache);
      if (countEl) countEl.innerText = "";
      return;
    }

    var filtered = entriesCache.filter(function(e) {
      return [
        e.insured_name  || "",
        e.policy_number || "",
        e.remarks       || "",
        e.date          || "",
        e.phone_number  || "",
        e.follow_up     || "",
        e.action        || "",
        e.alp           || ""
      ].some(function(val) { return val.toLowerCase().indexOf(q) !== -1; });
    });

    renderTable(filtered);
    if (typeof applyQualityDueIndicators === "function") applyQualityDueIndicators(filtered);

    if (countEl) {
      if (filtered.length === 0) {
        countEl.innerHTML = "<span style='color:#dc2626;'>No results for <strong>\u201c" + esc(query.trim()) + "\u201d</strong></span>";
      } else {
        countEl.innerHTML = "<span style='color:#2563eb;font-weight:600;'>" + filtered.length + "</span> result" + (filtered.length === 1 ? "" : "s") + " for <strong>\u201c" + esc(query.trim()) + "\u201d</strong>";
      }
    }

    if (filtered.length > 0) highlightQualityMatches(q);
  };

  window.clearQualitySearch = function() {
    var input = document.getElementById("qualitySearchInput");
    if (input) { input.value = ""; input.focus(); }
    window.filterQualityTable("");
  };

  function highlightQualityMatches(query) {
    if (!query) return;
    var tbody = document.getElementById("qualityBody");
    if (!tbody) return;
    tbody.querySelectorAll("td").forEach(function(cell) {
      if (cell.querySelector("button")) return;
      var text = cell.textContent;
      if (!text) return;
      var safe  = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      var regex = new RegExp("(" + safe + ")", "gi");
      if (!regex.test(text)) return;
      var parts = text.split(new RegExp("(" + safe + ")", "gi"));
      cell.innerHTML = parts.map(function(part, i) {
        return i % 2 === 1
          ? '<mark class="q-highlight">' + esc(part) + '</mark>'
          : esc(part);
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
      if (document.activeElement === input) {
        window.clearQualitySearch();
        input.blur();
      }
    }
  });

  // Close modal on backdrop click
  document.getElementById("qualityModal").addEventListener("click", function(e) {
    if (e.target === this) window.closeModal();
  });

  // ── Boot ──────────────────────────────────────────────────────
  loadEntries();

})();