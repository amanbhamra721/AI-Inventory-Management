if (!Auth.isLoggedIn()) {
  window.location.replace("login.html");
}

const id = (x) => document.getElementById(x);

function setText(idValue, value) {
  const el = id(idValue);
  if (el) {
    el.textContent = value;
    el.classList.remove("skeleton");
  }
}

function statusBadge(status) {
  if (status === "OUT_OF_STOCK") return '<span class="badge badge-error badge-sm">Out of Stock</span>';
  if (status === "LOW_STOCK") return '<span class="badge badge-warning badge-sm">Low Stock</span>';
  return '<span class="badge badge-success badge-sm">Healthy</span>';
}

async function exportCsv() {
  const resp = await Auth.apiFetch("/api/data/export/csv");
  if (!resp) return;
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "live_inventory_report.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function wireButtons() {
  ["logoutBtnDesktop", "logoutBtnMobile"].forEach((btnId) => {
    const btn = id(btnId);
    if (btn) btn.addEventListener("click", () => Auth.logout());
  });

  ["exportCsvBtnTop", "exportCsvBtnSide"].forEach((btnId) => {
    const btn = id(btnId);
    if (btn) btn.addEventListener("click", exportCsv);
  });
}

async function loadDashboard() {
  const [statsResp, stockResp, ledgerResp] = await Promise.all([
    Auth.apiFetch("/api/data/stats"),
    Auth.apiFetch("/api/data/stock"),
    Auth.apiFetch("/api/data/ledger"),
  ]);

  if (!statsResp || !stockResp || !ledgerResp) return;

  const stats = await statsResp.json();
  const stock = await stockResp.json();
  const ledger = await ledgerResp.json();

  setText("netStock", stats.net_stock ?? 0);
  setText("totalThaans", stats.total_thaans ?? 0);
  setText("inwardTotal", stats.total_inward ?? 0);
  setText("outwardTotal", stats.total_outward ?? 0);

  const low = stock.filter((x) => x.status && x.status !== "HEALTHY");
  setText("lowStock", low.length);
  setText("profilesCount", stock.length);

  const estCapital = ledger.reduce((acc, row) => acc + Math.max(0, Number(row.meters || 0) * Number(row.unit_price || 0)), 0);
  setText("totalCapital", estCapital.toFixed(2));

  const alerts = id("alertsContainer");
  if (alerts) {
    if (!low.length) {
      alerts.innerHTML = "";
    } else {
      alerts.innerHTML = low.map((a) => `
        <div class="alert alert-warning shadow-sm rounded-xl">
          <span><strong>${a.fabric}</strong> (Shade: ${a.shade_code || "N/A"}) is low at ${a.current_meters} meters.</span>
        </div>
      `).join("");
    }
  }

  const recentBody = id("recentBody");
  if (recentBody) {
    const recent = [...ledger].slice(0, 5);
    recentBody.innerHTML = recent.length
      ? recent.map((tx) => `
          <tr>
            <td class="font-medium">${tx.fabric || "N/A"}</td>
            <td>${tx.shade_code || "N/A"}</td>
            <td>${tx.transaction_type === "INWARD" ? '<span class="badge badge-success badge-sm">Inward</span>' : '<span class="badge badge-error badge-sm">Outward</span>'}</td>
            <td class="text-right">${Number(tx.meters || 0).toFixed(2)}</td>
            <td>${tx.created_at || "-"}</td>
          </tr>
        `).join("")
      : '<tr><td colspan="5" class="text-center text-base-content/60 py-6">No recent transactions available.</td></tr>';
  }

  const grouped = {};
  ledger.forEach((row) => {
    if (row.transaction_type !== "OUTWARD") return;
    const key = `${row.fabric || "N/A"}|||${row.shade_code || "N/A"}`;
    grouped[key] = (grouped[key] || 0) + Number(row.meters || 0);
  });
  const topFastSlow = Object.entries(grouped)
    .map(([key, outward]) => {
      const [fabric, shade] = key.split("|||");
      return { fabric, shade, outward };
    })
    .sort((a, b) => b.outward - a.outward)
    .slice(0, 10);

  const fastSlowBody = id("fastSlowBody");
  if (fastSlowBody) {
    fastSlowBody.innerHTML = topFastSlow.length
      ? topFastSlow.map((row) => `<tr><td>${row.fabric}</td><td>${row.shade || "N/A"}</td><td class="text-right">${row.outward.toFixed(2)}</td></tr>`).join("")
      : '<tr><td colspan="3" class="text-center text-base-content/60">No movement data.</td></tr>';
  }

  const byKey = {};
  ledger.forEach((row) => {
    const key = `${row.fabric || "N/A"}|||${row.shade_code || "N/A"}`;
    if (!byKey[key] || (row.created_at && row.created_at > byKey[key])) {
      byKey[key] = row.created_at;
    }
  });
  const now = new Date();
  const aging = Object.entries(byKey)
    .map(([key, dateStr]) => {
      const [fabric, shade] = key.split("|||");
      const last = dateStr ? new Date(dateStr) : now;
      const days = Math.max(0, Math.floor((now - last) / (1000 * 60 * 60 * 24)));
      const stockItem = stock.find((s) => (s.fabric || "N/A") === fabric && (s.shade_code || "N/A") === shade);
      return {
        fabric,
        shade,
        currentMeters: Number(stockItem?.current_meters || 0),
        days,
      };
    })
    .sort((a, b) => b.days - a.days)
    .slice(0, 10);

  const agingBody = id("agingBody");
  if (agingBody) {
    agingBody.innerHTML = aging.length
      ? aging.map((row) => `<tr><td>${row.fabric}</td><td>${row.shade || "N/A"}</td><td class="text-right">${row.currentMeters.toFixed(2)}</td><td class="text-right">${row.days}</td></tr>`).join("")
      : '<tr><td colspan="4" class="text-center text-base-content/60">No aging data available.</td></tr>';
  }

  const activityList = id("activityList");
  if (activityList) {
    const recent = [...ledger].slice(0, 8);
    activityList.innerHTML = recent.length
      ? recent.map((x) => `
          <div class="p-3 border border-base-300 rounded-lg bg-base-200">
            <p class="text-sm font-medium">${x.transaction_type} ${x.fabric || "Item"} (${Number(x.meters || 0).toFixed(2)}m)</p>
            <p class="text-xs text-base-content/70">${x.created_at || "-"}</p>
          </div>
        `).join("")
      : '<p class="text-sm text-base-content/60">No activity logs yet.</p>';
  }
}

wireButtons();
loadDashboard();
