const $ = (id) => document.getElementById(id);

const SOURCE_LABEL = {
  "keys-page": "pasted on this page",
  "import-hermes": "copied from Hermes .env",
  "cli-from-env": "CLI --from-env",
  "cli-secret-file": "CLI --secret-file",
  api: "HTTP API",
  "inferred-hermes-env": "matched Hermes .env (origin not recorded)",
  unknown: "origin not recorded",
};

const HERMES_LABEL = {
  match: "Hermes .env matches",
  drift: "Hermes .env differs",
  missing: "not in Hermes .env",
  "not-synced": "not mirrored",
};

const state = {
  keys: [],
  providers: [],
  tenants: [],
  tenantSource: "",
  tenant: "",
  path: "",
  hermesTenant: "reeves",
  agentInstructions: "",
};

function setStatus(text, kind) {
  const node = $("key-status");
  node.textContent = text || "";
  node.className = `key-status ${kind || ""}`.trim();
}

function fillTenants() {
  const select = $("key-tenant");
  const pills = $("tenant-pills");
  const current = state.tenant || select.value;
  select.innerHTML = "";
  pills.innerHTML = "";
  for (const row of state.tenants) {
    const option = document.createElement("option");
    option.value = row.id;
    option.textContent = row.name || row.id;
    select.appendChild(option);
    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = `view-pill${row.id === current ? " active" : ""}`;
    pill.dataset.tenant = row.id;
    pill.textContent = row.id;
    pills.appendChild(pill);
  }
  if (current && [...select.options].some((item) => item.value === current)) {
    select.value = current;
    state.tenant = current;
  } else if (select.options.length) {
    select.value = state.hermesTenant && [...select.options].some((item) => item.value === state.hermesTenant)
      ? state.hermesTenant
      : select.options[0].value;
    state.tenant = select.value;
  }
  $("tenant-source").textContent = state.tenantSource || "kai";
}

function fillProviders() {
  const select = $("key-provider");
  const current = select.value;
  select.innerHTML = "";
  for (const row of state.providers) {
    const option = document.createElement("option");
    option.value = row.id;
    option.textContent = row.stored ? `${row.label} · on file` : row.label;
    select.appendChild(option);
  }
  if (current && [...select.options].some((item) => item.value === current)) {
    select.value = current;
  }
}

function renderList() {
  const root = $("key-list");
  const visible = state.keys.filter((row) => !state.tenant || row.tenant === state.tenant);
  $("key-count").textContent = String(visible.length);
  $("key-path").textContent = state.path || "";
  $("agent-instructions").textContent = state.agentInstructions || "";
  if (!visible.length) {
    root.innerHTML = `<p class="empty">No keys for ${escapeHtml(state.tenant || "this tenant")} yet.</p>`;
    return;
  }
  root.innerHTML = "";
  for (const row of visible) {
    const item = document.createElement("article");
    item.className = "key-row key-row-provenanced";
    const hermes = row.hermes || {};
    item.innerHTML = `
      <span class="provider-dot" aria-hidden="true"></span>
      <div class="key-main">
        <strong>${escapeHtml(row.label || row.provider)}</strong>
        <small>${escapeHtml(row.tenant)} · ${escapeHtml(row.provider)} · ${escapeHtml(row.env_var || "")}</small>
        <small class="key-provenance">${escapeHtml(SOURCE_LABEL[row.source] || row.source)} · ${escapeHtml(row.fp || "")}</small>
        <small class="key-provenance">${escapeHtml(HERMES_LABEL[hermes.status] || hermes.status || "")}${row.rotated_at ? ` · rotated ${escapeHtml(row.rotated_at)}` : ` · created ${escapeHtml(row.created_at || row.updated_at || "")}`}</small>
      </div>
      <code class="key-mask">${escapeHtml(row.prefix || "key")}····${escapeHtml(row.last4 || "")}</code>
      <button class="button" type="button" data-delete-tenant="${escapeHtml(row.tenant)}" data-delete="${escapeHtml(row.provider)}">Remove</button>
    `;
    root.appendChild(item);
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function refresh() {
  const query = state.tenant ? `?tenant=${encodeURIComponent(state.tenant)}` : "";
  const response = await fetch(`/api/keys${query}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`list failed (${response.status})`);
  const data = await response.json();
  state.keys = data.keys || [];
  state.providers = data.providers || [];
  state.tenants = (data.tenants && data.tenants.items) || [];
  state.tenantSource = (data.tenants && data.tenants.source) || "";
  state.path = data.path || "";
  state.hermesTenant = data.hermes_tenant || "reeves";
  state.agentInstructions = data.agent_instructions || "";
  fillTenants();
  fillProviders();
  renderList();
}

async function save(event) {
  event.preventDefault();
  const tenant = $("key-tenant").value;
  const provider = $("key-provider").value;
  const label = $("key-label").value.trim();
  const secret = $("key-secret").value;
  if (!secret.trim()) {
    setStatus("Paste a key first.", "error");
    return;
  }
  const response = await fetch("/api/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant, provider, label, secret, source: "keys-page" }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    setStatus(data.error || `save failed (${response.status})`, "error");
    return;
  }
  $("key-secret").value = "";
  $("key-label").value = "";
  state.tenant = tenant;
  setStatus(`Saved ${data.key.tenant}/${data.key.provider} ${data.key.fp}.`, "ok");
  await refresh();
}

async function importHermes() {
  const response = await fetch("/api/keys/import-hermes", { method: "POST" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    setStatus(data.error || "import failed", "error");
    return;
  }
  if (data.missing) {
    setStatus("No ~/.hermes/.env on this Mac.", "error");
    return;
  }
  state.tenant = data.tenant || state.hermesTenant;
  const imported = (data.imported || []).join(", ") || "nothing new";
  setStatus(`Imported ${imported} into ${data.tenant}.`, "ok");
  await refresh();
}

async function removeKey(tenant, provider) {
  if (!window.confirm(`Remove ${tenant}/${provider} from this Mac?`)) return;
  const response = await fetch(`/api/keys/${encodeURIComponent(tenant)}/${encodeURIComponent(provider)}`, { method: "DELETE" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    setStatus(data.error || "remove failed", "error");
    return;
  }
  setStatus(`Removed ${tenant}/${provider}.`, "ok");
  await refresh();
}

function boot() {
  $("key-form").addEventListener("submit", (event) => {
    save(event).catch((error) => setStatus(String(error.message || error), "error"));
  });
  $("import-hermes").addEventListener("click", () => {
    importHermes().catch((error) => setStatus(String(error.message || error), "error"));
  });
  $("key-tenant").addEventListener("change", () => {
    state.tenant = $("key-tenant").value;
    refresh().catch((error) => setStatus(String(error.message || error), "error"));
  });
  $("tenant-pills").addEventListener("click", (event) => {
    const button = event.target.closest("[data-tenant]");
    if (!button) return;
    state.tenant = button.dataset.tenant;
    refresh().catch((error) => setStatus(String(error.message || error), "error"));
  });
  $("key-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete]");
    if (!button) return;
    removeKey(button.dataset.deleteTenant, button.dataset.delete).catch((error) => setStatus(String(error.message || error), "error"));
  });
  refresh().catch((error) => setStatus(String(error.message || error), "error"));
}

boot();
