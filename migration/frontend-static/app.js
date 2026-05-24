// Auth guard — redirect immediately if not logged in
if (!Auth.isLoggedIn()) {
  window.location.replace("login.html");
}

// ── DOM refs ──────────────────────────────────────────────────────────────
const netStockEl    = document.getElementById("netStock");
const totalInwardEl = document.getElementById("totalInward");
const totalOutwardEl= document.getElementById("totalOutward");
const alertsEl      = document.getElementById("alerts");
const stockListEl   = document.getElementById("stockList");
const itemCountEl   = document.getElementById("itemCount");
const searchInput   = document.getElementById("searchInput");
const searchBtn     = document.getElementById("searchBtn");
const clearBtn      = document.getElementById("clearBtn");
const exportCsvBtn  = document.getElementById("exportCsvBtn");
const logoutBtn     = document.getElementById("logoutBtn");

// ── Helpers ───────────────────────────────────────────────────────────────
function statusBadge(status) {
  if (status === "OUT_OF_STOCK") return `<span class="badge badge-sm bg-red-600 text-white border-none text-[9px] uppercase tracking-wider font-bold">Out of Stock</span>`;
  if (status === "LOW_STOCK")    return `<span class="badge badge-sm bg-orange-400 text-white border-none text-[9px] uppercase tracking-wider font-bold">Low Stock</span>`;
  return "";
}

function meterColor(meters) {
  return meters < 50 ? "text-red-500" : "text-slate-700";
}

// ── Render ────────────────────────────────────────────────────────────────
function renderAlerts(items) {
  const low = items.filter(i => i.status !== "HEALTHY");
  if (!low.length) { alertsEl.innerHTML = ""; return; }
  alertsEl.innerHTML = `
    <div class="mb-8">
      <h3 class="font-bold text-red-600 mb-3 text-sm">⚠️ Critical Stock Alerts</h3>
      <div class="space-y-3">
        ${low.map(a => `
          <div class="bg-red-50 p-4 rounded-xl shadow-sm border border-red-200 flex justify-between items-center">
            <div>
              <p class="font-bold text-red-800 text-sm">${a.fabric}</p>
              <span class="text-[10px] bg-red-100 px-2 py-0.5 rounded font-medium text-red-600 border border-red-200">
                Shade: ${a.shade_code || "N/A"}
              </span>
            </div>
            <div class="text-right">
              <p class="text-xl font-bold text-red-600">${a.current_meters}</p>
              <p class="text-[9px] text-red-400 font-bold uppercase">Meters Left</p>
              ${statusBadge(a.status)}
            </div>
          </div>`).join("")}
      </div>
    </div>`;
}

function renderStock(items) {
  itemCountEl.textContent = `${items.length} Items`;
  if (!items.length) {
    stockListEl.innerHTML = `<div class="text-center py-8 text-slate-400 text-sm">No stock profiles found.</div>`;
    return;
  }
  stockListEl.innerHTML = items.map(item => `
    <div class="bg-white p-4 rounded-xl shadow-sm border border-slate-100 flex justify-between items-center">
      <div>
        <p class="font-bold text-slate-800 text-sm">${item.fabric || "Unknown Fabric"}</p>
        <div class="flex gap-2 mt-1.5">
          <span class="text-[9px] bg-slate-100 px-2 py-0.5 rounded font-medium text-slate-500 border border-slate-200">
            Shade: ${item.shade_code || "N/A"}
          </span>
        </div>
      </div>
      <div class="text-right">
        <p class="text-xl font-bold ${meterColor(item.current_meters)}">${item.current_meters}</p>
        <p class="text-[9px] text-slate-400 font-bold uppercase">Meters</p>
        ${statusBadge(item.status)}
      </div>
    </div>`).join("");
}

// ── Data fetching ─────────────────────────────────────────────────────────
async function loadStats() {
  const resp = await Auth.apiFetch("/api/data/stats");
  if (!resp) return;
  const d = await resp.json();
  netStockEl.textContent    = d.net_stock;
  totalInwardEl.textContent = d.total_inward;
  totalOutwardEl.textContent= d.total_outward;
}

async function loadStock(search = "") {
  const query = search ? `?search=${encodeURIComponent(search)}` : "";
  const resp = await Auth.apiFetch(`/api/data/stock${query}`);
  if (!resp) return;
  const items = await resp.json();
  renderAlerts(items);
  renderStock(items);
  clearBtn.classList.toggle("hidden", !search);
}

// ── CSV export (downloads with token auth) ────────────────────────────────
exportCsvBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  const resp = await Auth.apiFetch("/api/data/export/csv");
  if (!resp) return;
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "live_inventory_report.csv";
  a.click();
  URL.revokeObjectURL(url);
});

// ── Search ────────────────────────────────────────────────────────────────
searchBtn.addEventListener("click", () => loadStock(searchInput.value.trim()));
searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") loadStock(searchInput.value.trim()); });
clearBtn.addEventListener("click", () => { searchInput.value = ""; loadStock(); });

// ── Logout ────────────────────────────────────────────────────────────────
logoutBtn.addEventListener("click", () => Auth.logout());

// ── Boot ──────────────────────────────────────────────────────────────────
loadStats();
loadStock();
