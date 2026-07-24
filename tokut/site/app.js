const state = {
  dashboard: null,
  filters: {
    provider: "",
    account: "",
    company: "",
    project: "",
    model: "",
    user: "",
    day: "",
    hour: "",
  },
  breakdown: "project",
  sort: "cost",
  mtdSpendZoom: "mtd",
  mtdSpendFocus: 100,
  drawerOpen: false,
  chatDrawerOpen: true,
  generatedAt: null,
  source: null,
};

const FILTER_SPECS = [
  ["provider", "Provider"],
  ["account", "Account"],
  ["company", "Company"],
  ["project", "Project"],
  ["model", "Model"],
  ["user", "User"],
  ["day", "Day"],
  ["hour", "Hour"],
];

const SORT_SPECS = [
  ["cost", "Highest $"],
  ["tokens", "Most Tokens"],
  ["events", "Most Events"],
  ["recent", "Newest"],
  ["name", "Name"],
];

const MTD_SPEND_ZOOMS = [
  ["1h", "1H", 60],
  ["6h", "6H", 360],
  ["24h", "1D", 1440],
  ["7d", "7D", 10080],
  ["mtd", "MTD", Infinity],
];

const $ = (id) => document.getElementById(id);

function fmt(n) {
  return Number(n || 0).toLocaleString();
}

function compact(n) {
  const value = Number(n || 0);
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${trimDecimal(value / 1e9)}B`;
  if (abs >= 1e6) return `${trimDecimal(value / 1e6)}M`;
  if (abs >= 1e4) return `${trimDecimal(value / 1e3)}k`;
  return value.toLocaleString();
}

function trimDecimal(x) {
  const rounded = Math.round(x * 10) / 10;
  return rounded.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function pct(n) {
  return `${Math.round(Number(n || 0) * 10) / 10}%`;
}

function titleCase(value) {
  return String(value || "")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function money(n) {
  const value = Number(n || 0);
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  }
  if (Math.abs(value) >= 1) {
    return value.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (Math.abs(value) >= 0.01) {
    return value.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 })}`;
}

function resetText(epochSeconds) {
  if (!epochSeconds) return "reset unknown";
  const diff = epochSeconds * 1000 - Date.now();
  if (diff <= 0) return "reset now";
  const minutes = Math.round(diff / 60000);
  if (minutes < 90) return `resets in ${minutes}m`;
  return `resets in ${Math.round(minutes / 60)}h`;
}

function ageText(isoTimestamp) {
  if (!isoTimestamp) return "–";
  const diff = Date.now() - new Date(isoTimestamp).getTime();
  if (Number.isNaN(diff)) return "–";
  if (diff < 60000) return "now";
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function freshnessText(isoTimestamp) {
  if (!isoTimestamp) return "updated unknown";
  const diff = Date.now() - new Date(isoTimestamp).getTime();
  if (Number.isNaN(diff)) return "updated unknown";
  if (diff < 1000) return "updated <1s ago";
  const seconds = Math.max(1, Math.floor(diff / 1000));
  if (seconds < 60) return `updated ${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `updated ${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `updated ${hours}h ago`;
  return `updated ${Math.floor(hours / 24)}d ago`;
}

function setConnection(ok) {
  $("connection-dot").classList.toggle("stale", !ok);
  $("connection-text").textContent = ok ? "live" : "reconnecting";
}

function providerColor(provider) {
  if (provider === "codex") return "var(--codex)";
  if (provider === "claude") return "var(--claude)";
  if (provider === "grok") return "var(--grok, #1da1f2)";
  if (provider === "gemini") return "var(--gemini)";
  return "var(--warn)";
}

function providerLabel(provider) {
  if (provider === "codex") return "OpenAI";
  if (provider === "claude") return "Anthropic";
  if (provider === "grok") return "xAI Grok";
  if (provider === "gemini") return "Google";
  return titleCase(provider || "Unknown");
}

function providerLogo(provider) {
  if (provider === "codex") return "/logos/openai.svg";
  if (provider === "claude") return "/logos/anthropic.svg";
  if (provider === "gemini") return "/logos/google.svg";
  return "";
}

function modelKey(provider, model) {
  return `${provider || "unknown"}\u0000${model || "unknown"}`;
}

function clampPct(value) {
  return Math.min(Math.max(Number(value || 0), 0), 100);
}

function buildModelSparklines(minuteRows, points = 28) {
  const minuteSet = new Set();
  minuteRows.forEach((row) => {
    if (row.minute) minuteSet.add(row.minute);
  });
  const minutes = [...minuteSet].sort().slice(-points);
  const indexByMinute = new Map(minutes.map((minute, index) => [minute, index]));
  const buckets = new Map();
  minuteRows.forEach((row) => {
    if (!indexByMinute.has(row.minute)) return;
    const key = modelKey(row.provider, row.model);
    if (!buckets.has(key)) buckets.set(key, Array(points).fill(0));
    buckets.get(key)[indexByMinute.get(row.minute)] += Number(row.total_tokens || 0);
  });
  return buckets;
}

function modelSparkline(values) {
  const width = 112;
  const height = 26;
  const max = Math.max(1, ...values);
  const points = values.map((value, index) => {
    const x = values.length <= 1 ? width : (index / (values.length - 1)) * width;
    const y = height - (Number(value || 0) / max) * (height - 3) - 1.5;
    return `${roundForSvg(x)},${roundForSvg(y)}`;
  });
  const area = points.length ? `0,${height} ${points.join(" ")} ${width},${height}` : "";
  return `
    <svg class="model-sparkline" viewBox="0 0 ${width} ${height}" role="img" aria-label="Recent token burn trend">
      <polyline class="spark-area" points="${area}"></polyline>
      <polyline class="spark-line" points="${points.join(" ")}"></polyline>
    </svg>
  `;
}

function roundForSvg(value) {
  return Math.round(value * 10) / 10;
}

function render(dashboard) {
  state.dashboard = dashboard;
  state.generatedAt = dashboard.generated_at;
  const current = dashboard.current;
  const primary = dashboard.latest_rate_limits?.primary || {};
  const secondary = dashboard.latest_rate_limits?.secondary || {};
  const windows = dashboard.windows || {};
  const costs = dashboard.costs || {};
  const billing = dashboard.billing || {};

  $("subtitle").textContent = `${dashboard.codex_home} · updated ${new Date(dashboard.generated_at).toLocaleTimeString()}`;
  $("event-count").textContent =
    dashboard.event_count === dashboard.total_event_count
      ? fmt(dashboard.event_count)
      : `${fmt(dashboard.event_count)} / ${fmt(dashboard.total_event_count)}`;
  $("watched-files").textContent = fmt(dashboard.watched_files);
  $("plan-type").textContent = dashboard.latest_rate_limits?.plan_type || "local";
  $("account-count").textContent = `${fmt((dashboard.accounts || []).length)} accounts`;
  $("windows-note").textContent =
    dashboard.event_count === dashboard.total_event_count
      ? `${fmt(dashboard.event_count)} events`
      : `${fmt(dashboard.event_count)} of ${fmt(dashboard.total_event_count)} events match`;

  const burn1h = windows["1h"]?.total_tokens || 0;
  const burn5m = windows["5m"]?.total_tokens || 0;
  $("kpi-burn").textContent = compact(burn1h);
  $("kpi-burn").title = `${fmt(burn1h)} tokens in the last hour`;
  $("kpi-burn-sub").textContent = `≈ ${compact(Math.round(burn5m / 5))} tok/min over 5m`;
  $("cost-hour").textContent = money(costs.estimated_1h_usd);
  $("cost-hour").title = `${money(costs.estimated_1h_usd)} API list-price equivalent in the last hour`;
  $("cost-hour-sub").textContent = `${money(costs.estimated_per_minute_5m_usd)} / min over 5m · ${billing.actual_charge_confidence || "unverified"}`;
  $("cost-minute").textContent = money(costs.estimated_current_minute_usd);
  $("cost-minute").title = `${money(costs.estimated_current_minute_usd)} API list-price equivalent in the current minute`;
  $("cost-minute-sub").textContent = `${money(costs.estimated_5m_usd)} over 5m`;
  $("cost-total").textContent = money(costs.estimated_total_usd);
  $("cost-total").title = `${money(costs.estimated_total_usd)} API list-price equivalent across matching events`;
  $("cost-total-sub").textContent = `${fmt(costs.priced_event_count)} priced-estimate · ${fmt(costs.unpriced_event_count)} unpriced`;

  if (current) {
    const contextPct = current.model_context_window
      ? (current.last.input_tokens / current.model_context_window) * 100
      : 0;
    $("current-total").textContent = compact(current.total.total_tokens);
    $("current-total").title = fmt(current.total.total_tokens);
    $("current-thread").textContent = `${providerLabel(current.provider)} / ${current.account} · ${current.thread_name || current.session_id}`;
    $("current-thread").title = current.thread_name || current.session_id;
    $("last-total").textContent = compact(current.last.total_tokens);
    $("last-total").title = fmt(current.last.total_tokens);
    $("last-breakdown").textContent = `in ${compact(current.last.input_tokens)} · out ${compact(current.last.output_tokens)}`;
    $("context-window").textContent = pct(contextPct);
    $("context-raw").textContent = `${fmt(current.last.input_tokens)} / ${fmt(current.model_context_window)}`;
    setBar("context-bar", contextPct);
  } else {
    $("current-total").textContent = "0";
    $("current-thread").textContent = "No matching token events";
    $("last-total").textContent = "0";
    $("last-breakdown").textContent = "in 0 · out 0";
    $("context-window").textContent = "0%";
    $("context-raw").textContent = "0 / 0";
    setBar("context-bar", 0);
  }

  $("primary-limit").textContent = pct(primary.used_percent);
  $("primary-reset").textContent = resetText(primary.resets_at);
  setBar("primary-bar", primary.used_percent);
  $("secondary-limit").textContent = pct(secondary.used_percent);
  $("secondary-reset").textContent = resetText(secondary.resets_at);
  setBar("secondary-bar", secondary.used_percent);

  renderFilters(dashboard);
  renderSorts();
  renderActiveFilters();
  renderAssurance(dashboard);
  renderConsult(dashboard.consult || {});
  renderProviderModelTable(dashboard.providers || [], dashboard.models || [], dashboard.minute_model_costs || []);
  renderSubscriptions(dashboard.subscriptions || []);
  renderCharts(dashboard);
  renderWindows(windows);
  renderBillingNote(billing);
  renderModels(dashboard.models || []);
  renderMinuteCosts(dashboard.minute_costs || [], dashboard.minute_model_costs || []);
  renderBreakdown(dashboard.breakdowns || {});
  renderAccounts(dashboard.accounts || []);
  renderChatDrawer(dashboard.sessions || [], dashboard.current);
  renderSessions(dashboard.sessions || []);
  renderLimits(primary, secondary);
}

function renderAssurance(dashboard) {
  const costs = dashboard.costs || {};
  const billing = dashboard.billing || {};
  const confidence = billing.actual_charge_confidence || "unverified";
  const markers = billing.observed_api_env_markers || [];
  const meter = Number(
    billing.theoretical_api_equivalent_usd || billing.estimated_api_equivalent_usd || costs.estimated_total_usd || 0
  );
  const planCredits = Number(billing.plan_credits_usd || billing.subscription_theoretical_usd || 0);
  const metered = Number(billing.metered_usd || 0);
  const cash = Number(billing.actual_charge_usd || billing.paid_api_or_overage_usd || billing.confirmed_charge_usd || 0);
  const unknown = Number(billing.unknown_theoretical_usd || 0);
  const cashMax = Number(billing.cash_exposure_max_usd || cash);
  const allowance = Number(billing.included_allowance_usd || 0);

  $("api-equivalent").textContent = money(meter);
  $("api-equivalent").title = `${money(meter)} full meter (list price or server cost ticks)`;
  $("api-equivalent-sub").textContent = `${fmt(costs.priced_event_count)} priced · ${fmt(costs.unpriced_event_count)} unpriced`;

  $("plan-credits").textContent = money(planCredits);
  $("plan-credits").title = `${money(planCredits)} discounted plan credits (included usage)`;
  $("plan-credits-sub").textContent = allowance
    ? `included allowance ${money(allowance)}`
    : "all sub burn as credits if no allowance set";

  $("metered-above").textContent = money(metered);
  $("metered-above").title = `${money(metered)} burn above included allowance (cash-eligible)`;
  $("metered-above-sub").textContent = metered ? "subject to overage cap" : "none above plan credits";

  $("confirmed-charge").textContent = money(cash);
  $("confirmed-charge").title = `${money(cash)} estimated cash (API + capped overage); max ${money(cashMax)}`;
  $("confirmed-charge-sub").textContent = cashMax > cash ? `est. cash · max ${money(cashMax)}` : "API + capped overage";

  $("quota-burn").textContent = money(unknown);
  $("quota-burn").title = `${money(unknown)} unmapped meter (set billing_mode)`;
  $("quota-burn-sub").textContent = unknown ? "map accounts in subscriptions.json" : "all accounts mapped";

  $("charge-confidence").textContent = titleCase(confidence.replaceAll("_", " "));
  $("charge-confidence-sub").textContent = markers.length ? `markers: ${markers.join(", ")}` : "no API billing markers seen";
}

function renderConsult(consult) {
  const headline = consult.headline || "No consult data yet — burn some tokens or map subscriptions.";
  $("consult-headline").textContent = headline;
  const actions = consult.actions || [];
  $("consult-actions").innerHTML = actions.length
    ? actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")
    : "";
}

function renderBillingNote(billing) {
  const confidence = billing.actual_charge_confidence || "unverified";
  const env = billing.observed_api_env_markers || [];
  const markerText = env.length ? `billing env markers: ${env.join(", ")}` : "no API billing env markers seen by daemon";
  const split = `Plan credits ${money(billing.plan_credits_usd)} · metered ${money(billing.metered_usd)} · cash ${money(billing.paid_api_or_overage_usd)}.`;
  $("billing-note").textContent = `${billing.warning || "Local logs prove token burn, not invoice charges."} ${split} Confidence: ${confidence}; ${markerText}.`;
}

function renderCharts(dashboard) {
  renderMtdSpendChart(dashboard.mtd_spend || []);
  renderCostStackChart(dashboard.costs || {}, dashboard.billing || {});
  renderModelChart(dashboard.models || []);
  renderHourChart(dashboard.breakdowns?.hour || []);
  renderMinuteChart(dashboard.minute_costs || []);
  updateFreshnessLabels();
}

function renderMtdSpendChart(rows) {
  renderMtdSpendControls();
  $("mtd-spend-focus").value = String(state.mtdSpendFocus);
  if (!rows.length) {
    $("mtd-spend-note").textContent = "no MTD spend rows";
    $("mtd-spend-start").textContent = "start";
    $("mtd-spend-end").textContent = "now";
    $("mtd-spend-chart").innerHTML = `<p class="empty">No month-to-date spend data yet.</p>`;
    return;
  }

  const visible = visibleMtdSpendRows(rows);
  const latest = visible[visible.length - 1] || rows[rows.length - 1];
  const first = visible[0] || rows[0];
  const width = 920;
  const height = 260;
  const pad = { top: 14, right: 18, bottom: 28, left: 56 };
  const maxValue = Math.max(
    0.00000001,
    ...visible.map((row) => Number(row.mtd_actual_usd || 0)),
    ...visible.map((row) => Number(row.mtd_api_equivalent_usd || 0))
  );
  const actualPoints = spendPoints(visible, "mtd_actual_usd", maxValue, width, height, pad);
  const apiPoints = spendPoints(visible, "mtd_api_equivalent_usd", maxValue, width, height, pad);
  const yTicks = [0, 0.5, 1].map((ratio) => {
    const y = height - pad.bottom - ratio * (height - pad.top - pad.bottom);
    return {
      y: roundForSvg(y),
      label: money(maxValue * ratio),
    };
  });
  const latestActual = Number(latest.mtd_actual_usd || 0);
  const latestApi = Number(latest.mtd_api_equivalent_usd || 0);
  const latestTokens = Number(latest.mtd_tokens || 0);
  $("mtd-spend-note").textContent = `Actual ${money(latestActual)} · API equiv ${money(latestApi)} · ${compact(latestTokens)} tokens`;
  $("mtd-spend-start").textContent = spendAxisLabel(first.minute);
  $("mtd-spend-end").textContent = spendAxisLabel(latest.minute);
  $("mtd-spend-chart").innerHTML = `
    <svg class="stock-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Month-to-date cumulative spend by minute">
      <rect class="stock-bg" x="${pad.left}" y="${pad.top}" width="${width - pad.left - pad.right}" height="${height - pad.top - pad.bottom}"></rect>
      ${yTicks
        .map(
          (tick) => `
            <line class="stock-grid" x1="${pad.left}" x2="${width - pad.right}" y1="${tick.y}" y2="${tick.y}"></line>
            <text class="stock-y" x="${pad.left - 9}" y="${tick.y + 3}">${escapeHtml(tick.label)}</text>
          `
        )
        .join("")}
      <polyline class="stock-line api" points="${apiPoints}"></polyline>
      <polyline class="stock-line actual" points="${actualPoints}"></polyline>
      ${visible
        .slice(-12)
        .map((row) => {
          const point = spendPoint(row, visible, "mtd_actual_usd", maxValue, width, height, pad);
          const tooltip = [
            spendTooltipTime(row.minute),
            `Actual MTD: ${money(row.mtd_actual_usd)}`,
            `API equiv MTD: ${money(row.mtd_api_equivalent_usd)}`,
            `Minute actual: ${money(row.actual_charge_usd)}`,
            `Minute API equiv: ${money(row.api_equivalent_usd)}`,
            `MTD tokens: ${fmt(row.mtd_tokens)}`,
          ].join("\\n");
          return `<circle class="stock-point" cx="${point.x}" cy="${point.y}" r="4" tabindex="0"><title>${escapeHtml(tooltip)}</title></circle>`;
        })
        .join("")}
      <text class="stock-x left" x="${pad.left}" y="${height - 7}">${escapeHtml(spendAxisLabel(first.minute))}</text>
      <text class="stock-x right" x="${width - pad.right}" y="${height - 7}">${escapeHtml(spendAxisLabel(latest.minute))}</text>
    </svg>
    <div class="stock-legend" aria-label="Chart legend">
      <span><i class="actual"></i>Actual $</span>
      <span><i class="api"></i>API equiv</span>
    </div>
  `;
}

function renderMtdSpendControls() {
  $("mtd-spend-controls").innerHTML = MTD_SPEND_ZOOMS.map(([key, label]) => {
    const selected = state.mtdSpendZoom === key;
    return `<button class="stock-control ${selected ? "selected" : ""}" type="button" data-mtd-zoom="${key}" aria-pressed="${selected}">${label}</button>`;
  }).join("");
  document.querySelectorAll("[data-mtd-zoom]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mtdSpendZoom = button.dataset.mtdZoom;
      state.mtdSpendFocus = 100;
      render(state.dashboard);
    });
  });
}

function visibleMtdSpendRows(rows) {
  const focus = Number.isFinite(Number(state.mtdSpendFocus)) ? Number(state.mtdSpendFocus) : 100;
  const focusIndex = Math.max(0, Math.min(rows.length - 1, Math.round((focus / 100) * (rows.length - 1))));
  const end = rows[focusIndex] || rows[rows.length - 1];
  const zoom = MTD_SPEND_ZOOMS.find(([key]) => key === state.mtdSpendZoom) || MTD_SPEND_ZOOMS[MTD_SPEND_ZOOMS.length - 1];
  const minutes = zoom[2];
  if (!Number.isFinite(minutes)) return rows.slice(0, focusIndex + 1);
  const cutoff = new Date(end.minute).getTime() - minutes * 60000;
  const visible = rows.slice(0, focusIndex + 1).filter((row) => new Date(row.minute).getTime() >= cutoff);
  if (visible.length >= 2) return visible;
  return rows.slice(Math.max(0, focusIndex - 1), focusIndex + 1);
}

function spendPoints(rows, field, maxValue, width, height, pad) {
  return rows.map((row) => {
    const point = spendPoint(row, rows, field, maxValue, width, height, pad);
    return `${point.x},${point.y}`;
  }).join(" ");
}

function spendPoint(row, rows, field, maxValue, width, height, pad) {
  const index = Math.max(0, rows.indexOf(row));
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const x = pad.left + (rows.length <= 1 ? plotWidth : (index / (rows.length - 1)) * plotWidth);
  const y = height - pad.bottom - (Number(row[field] || 0) / maxValue) * plotHeight;
  return { x: roundForSvg(x), y: roundForSvg(y) };
}

function spendAxisLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "–";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function spendTooltipTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown minute";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function renderCostStackChart(costs, billing) {
  const paid = Number(billing.paid_api_or_overage_usd || billing.actual_charge_usd || billing.confirmed_charge_usd || 0);
  const planCredits = Number(billing.plan_credits_usd || billing.subscription_theoretical_usd || 0);
  const metered = Number(billing.metered_usd || 0);
  // Metered residual above cash (e.g. overage burn above auto-top-up cap) stays visible.
  const meteredUncashed = Math.max(0, metered - paid);
  const unknown = Number(billing.unknown_theoretical_usd || 0);
  const withoutSubscriptions = Number(billing.would_pay_without_subscriptions_usd || costs.estimated_total_usd || 0);
  const total = Math.max(paid + meteredUncashed + planCredits + unknown, 0.00000001);
  const segments = [
    ["Cash (API / capped overage)", paid, "confirmed", "Estimated cash: API-billed burn plus overage within monthly cap."],
    ["Metered above cash cap", meteredUncashed, "metered", "Burn above plan credits that exceeds the overage cash cap (or is uncapped residual)."],
    ["Plan credits (discounted)", planCredits, "estimate", "Included plan usage at list/server meter — not cash."],
    ["Unknown / unassigned", unknown, "quota", "Meter not mapped to subscription or API billing mode."],
  ];
  $("cost-stack-note").dataset.suffix = ` · full meter ${money(withoutSubscriptions)}`;
  $("cost-stack-chart").innerHTML = `
    <div class="stacked-bar money-stack" role="img" aria-label="Cash, metered residual, plan credits, and unknown burn">
      ${segments
        .map(([label, value, key, detail]) => {
          const width = value ? Math.max((value / total) * 100, 2) : 0;
          return `<span class="${key}" style="width:${width}%" title="${escapeHtml(label)}: ${money(value)}. ${detail}"></span>`;
        })
        .join("")}
    </div>
    <div class="confidence-legend">
      ${segments
        .map(
          ([label, value, key, detail]) => `
            <span class="legend-item" title="${escapeHtml(detail)}">
              <i class="${key}"></i>
              <span>${label}</span>
              <strong class="num">${money(value)}</strong>
            </span>
          `
        )
        .join("")}
    </div>
    <p class="chart-callout">Plan credits are discounted included usage. Metered is burn above included.allowance_usd. Cash is only the metered slice limited by overage caps (or full API billing). Full no-subscription meter is the counterfactual total.</p>
  `;
}

function renderModelChart(models) {
  const rows = models.slice(0, 8);
  const max = Math.max(0.00000001, ...rows.map((row) => Number(row.estimated_cost_usd || 0)));
  $("model-chart-note").dataset.prefix = `${fmt(rows.length)} shown · `;
  $("model-chart").innerHTML =
    rows
      .map((row) => {
        const color = providerColor(row.provider);
        const amount = Number(row.estimated_cost_usd || 0);
        const width = Math.max((amount / max) * 100, amount ? 2 : 0);
        const tooltip = modelTooltip(row);
        return `
          <button class="chart-row" type="button" data-chart-model="${escapeHtml(row.model)}" title="${escapeHtml(tooltip)}">
            <span class="chart-row-label">
              <i style="background:${color}"></i>
              <span>${escapeHtml(row.model)}</span>
            </span>
            <span class="chart-track"><span style="width:${width}%; background:${color}"></span></span>
            <strong class="num">${money(amount)}</strong>
          </button>
        `;
      })
      .join("") || `<p class="empty">No model data.</p>`;

  document.querySelectorAll("[data-chart-model]").forEach((row) => {
    row.addEventListener("click", () => {
      const model = row.dataset.chartModel;
      state.filters.model = state.filters.model === model ? "" : model;
      refreshWithFilters();
    });
  });
}

function renderHourChart(hours) {
  const byHour = new Map(hours.map((row) => [String(row.value || row.label), row]));
  const rows = Array.from({ length: 24 }, (_, hour) => {
    const label = `${String(hour).padStart(2, "0")}:00`;
    return byHour.get(label) || { label, value: label, estimated_cost_usd: 0, total_tokens: 0, event_count: 0 };
  });
  const max = Math.max(0.00000001, ...rows.map((row) => Number(row.estimated_cost_usd || 0)));
  const top = rows.reduce((best, row) => (Number(row.estimated_cost_usd || 0) > Number(best.estimated_cost_usd || 0) ? row : best), rows[0]);
  $("hour-chart-note").dataset.prefix = `peak ${top.label || top.value} · ${money(top.estimated_cost_usd)} · `;
  $("hour-chart").innerHTML = rows
    .map((row, index) => {
      const amount = Number(row.estimated_cost_usd || 0);
      const height = Math.max((amount / max) * 100, amount ? 3 : 1);
      const hot = amount === Number(top.estimated_cost_usd || 0) && amount > 0;
      const tooltip = [
        `${row.label || row.value}`,
        `API-equivalent cost: ${money(amount)}`,
        `Tokens: ${fmt(row.total_tokens)}`,
        `Events: ${fmt(row.event_count)}`,
        freshnessText(state.generatedAt),
      ].join("\n");
      return `
        <button class="column ${hot ? "hot" : ""}" type="button" data-chart-hour="${escapeHtml(row.value || row.label)}"
          title="${escapeHtml(tooltip)}">
          <span class="column-bar" style="height:${height}%"></span>
          <span class="column-label">${index % 3 === 0 ? String(index).padStart(2, "0") : ""}</span>
        </button>
      `;
    })
    .join("");

  document.querySelectorAll("[data-chart-hour]").forEach((column) => {
    column.addEventListener("click", () => {
      const hour = column.dataset.chartHour;
      state.filters.hour = state.filters.hour === hour ? "" : hour;
      refreshWithFilters();
    });
  });
}

function renderMinuteChart(minutes) {
  const rows = minutes.slice(0, 40).reverse();
  const max = Math.max(1, ...rows.map((row) => Number(row.total_tokens || 0)));
  const latest = rows[rows.length - 1] || {};
  $("minute-chart-note").dataset.prefix = rows.length ? `latest ${compact(latest.total_tokens)} tokens · ` : "no recent minutes · ";
  $("minute-chart").innerHTML =
    rows
      .map((row) => {
        const tokens = Number(row.total_tokens || 0);
        const height = Math.max((tokens / max) * 100, tokens ? 3 : 1);
        const priced = Number(row.priced_event_count || 0) > 0;
        const tooltip = [
          minuteLabel(row.minute),
          `API-equivalent cost: ${money(row.estimated_cost_usd)}`,
          `Tokens: ${fmt(tokens)}`,
          `Events: ${fmt(row.event_count)}`,
          `Priced events: ${fmt(row.priced_event_count)}`,
          freshnessText(state.generatedAt),
        ].join("\n");
        return `
          <span class="spark-column ${priced ? "priced" : "unpriced"}"
            title="${escapeHtml(tooltip)}">
            <span style="height:${height}%"></span>
          </span>
        `;
      })
      .join("") || `<p class="empty">No recent minute data.</p>`;
}

function updateFreshnessLabels() {
  const label = freshnessText(state.generatedAt);
  const costNote = $("cost-stack-note");
  const modelNote = $("model-chart-note");
  const hourNote = $("hour-chart-note");
  const minuteNote = $("minute-chart-note");
  if (costNote) costNote.textContent = `${label}${costNote.dataset.suffix || ""}`;
  if (modelNote) modelNote.textContent = `${modelNote.dataset.prefix || ""}${label}`;
  if (hourNote) hourNote.textContent = `${hourNote.dataset.prefix || ""}${label}`;
  if (minuteNote) minuteNote.textContent = `${minuteNote.dataset.prefix || ""}${label}`;
}

setInterval(updateFreshnessLabels, 1000);

function setBar(id, percent) {
  const node = $(id);
  const used = Math.min(Math.max(Number(percent || 0), 0), 100);
  node.style.width = `${used}%`;
  node.style.background = used > 80 ? "var(--hot)" : used > 60 ? "var(--warn)" : "var(--gemini)";
}

function renderFilters(dashboard) {
  const facets = dashboard.filters || {};
  const projectRows = [...(dashboard.breakdowns?.project || [])].sort((a, b) => Number(b.total_tokens || 0) - Number(a.total_tokens || 0));
  const projectTokenCounts = new Map(projectRows.map((row) => [String(row.value), Number(row.total_tokens || 0)]));
  const providerCounts = new Map((dashboard.providers || []).map((row) => [String(row.provider), row]));
  $("filters").innerHTML = FILTER_SPECS.map(([key, label]) => {
    const options = key === "project" ? projectRows.map((row) => String(row.value)) : facets[key] || [];
    const active = Boolean(state.filters[key]);
    return `
      <section class="filter ${active ? "active" : ""}" aria-label="${label} filter">
        <header class="filter-head">
          <span>${label}</span>
          <button class="filter-clear ${active ? "active" : ""}" type="button" data-filter-clear="${key}">All</button>
        </header>
        <div class="filter-options ${key === "provider" ? "provider-filter-options" : ""}">
          ${options
            .map((value) => {
              const selected = state.filters[key] === String(value);
              const displayValue = filterDisplayValue(key, String(value), projectTokenCounts);
              const providerRow = providerCounts.get(String(value));
              if (key === "provider") {
                const logo = providerLogo(String(value));
                return `
                  <button class="filter-option provider-filter-option ${selected ? "selected" : ""}" type="button"
                    data-filter-key="${key}" data-filter-value="${escapeHtml(value)}"
                    title="${escapeHtml(filterOptionTitle(key, String(value), projectTokenCounts))}"
                    aria-pressed="${selected}">
                    ${
                      logo
                        ? `<img class="filter-logo" src="${logo}" alt="" />`
                        : `<span class="filter-logo fallback">${escapeHtml(providerLabel(String(value)).charAt(0))}</span>`
                    }
                    <span class="filter-option-copy">
                      <strong>${escapeHtml(displayValue)}</strong>
                      <small>${fmt(providerRow?.event_count || 0)} events · ${compact(providerRow?.total_tokens || 0)} tokens</small>
                    </span>
                  </button>
                `;
              }
              return `
                <button class="filter-option ${selected ? "selected" : ""}" type="button"
                  data-filter-key="${key}" data-filter-value="${escapeHtml(value)}"
                  title="${escapeHtml(filterOptionTitle(key, String(value), projectTokenCounts))}"
                  aria-pressed="${selected}">
                  ${escapeHtml(displayValue)}
                </button>
              `;
            })
            .join("") || `<span class="filter-empty">No values</span>`}
        </div>
      </section>
    `;
  }).join("");

  document.querySelectorAll("[data-filter-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.filterKey;
      const value = button.dataset.filterValue;
      state.filters[key] = state.filters[key] === value ? "" : value;
      refreshWithFilters();
    });
  });
  document.querySelectorAll("[data-filter-clear]").forEach((button) => {
    button.addEventListener("click", () => {
      state.filters[button.dataset.filterClear] = "";
      refreshWithFilters();
    });
  });
  $("reset-filters").onclick = () => {
    Object.keys(state.filters).forEach((key) => {
      state.filters[key] = "";
    });
    refreshWithFilters();
  };
}

function filterDisplayValue(key, value, projectTokenCounts) {
  if (key === "provider") return providerLabel(value);
  if (key === "project") return `${value} (${compact(projectTokenCounts.get(value) || 0)} tokens)`;
  return value;
}

function filterOptionTitle(key, value, projectTokenCounts) {
  if (key === "project") return `${value}: ${fmt(projectTokenCounts.get(value) || 0)} tokens`;
  if (key === "provider") return providerLabel(value);
  return value;
}

function renderSorts() {
  $("sorts").innerHTML = SORT_SPECS.map(([key, label]) => {
    const selected = state.sort === key;
    return `
      <button class="sort-option ${selected ? "selected" : ""}" type="button" data-sort="${key}" aria-pressed="${selected}">
        ${label}
      </button>
    `;
  }).join("");
  document.querySelectorAll("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      state.sort = button.dataset.sort;
      render(state.dashboard);
    });
  });
}

function renderActiveFilters() {
  const active = FILTER_SPECS.filter(([key]) => state.filters[key]);
  $("active-filters").innerHTML = active
    .map(
      ([key, label]) => `
        <button class="chip" type="button" data-chip="${key}" title="Remove ${label.toLowerCase()} filter">
          ${key === "provider" && providerLogo(state.filters[key]) ? `<img class="chip-logo" src="${providerLogo(state.filters[key])}" alt="" />` : ""}
          <span class="chip-key">${label}</span>
          <span class="chip-value">${escapeHtml(key === "provider" ? providerLabel(state.filters[key]) : state.filters[key])}</span>
          <span class="chip-x" aria-hidden="true">×</span>
        </button>
      `
    )
    .join("");
  document.querySelectorAll("[data-chip]").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.filters[chip.dataset.chip] = "";
      refreshWithFilters();
    });
  });
}

function renderProviderModelTable(providers, models, minuteModelCosts) {
  const providerTotals = new Map(providers.map((row) => [row.provider, row]));
  const rows = sortRows(models).slice(0, 14);
  const totalTokens = Math.max(1, rows.reduce((sum, row) => sum + Number(row.total_tokens || 0), 0));
  const totalEvents = rows.reduce((sum, row) => sum + Number(row.event_count || 0), 0);
  const totalBurn1h = rows.reduce((sum, row) => sum + Number(row.burn_1h || 0), 0);
  const totalCost = rows.reduce((sum, row) => sum + Number(row.estimated_cost_usd || 0), 0);
  const totalActual = rows.reduce((sum, row) => sum + Number(row.actual_charge_usd || 0), 0);
  const maxBurn1h = Math.max(1, ...rows.map((row) => Number(row.burn_1h || 0)));
  const maxEvents = Math.max(1, ...rows.map((row) => Number(row.event_count || 0)));
  const maxCost = Math.max(0.00000001, ...rows.map((row) => Number(row.estimated_cost_usd || 0)));
  const maxActual = Math.max(0.00000001, ...rows.map((row) => Number(row.actual_charge_usd || 0)));
  const sparklineBuckets = buildModelSparklines(minuteModelCosts, 28);
  $("provider-model-note").textContent = `${fmt(rows.length)} model rows`;

  if (!rows.length) {
    $("provider-model-table").innerHTML = `<p class="empty">No model token rows yet.</p>`;
    return;
  }

  const body = rows
    .map((row) => {
      const provider = row.provider || "unknown";
      const color = providerColor(provider);
      const logo = providerLogo(provider);
      const share = (Number(row.total_tokens || 0) / totalTokens) * 100;
      const selectedProvider = state.filters.provider === provider;
      const selectedModel = state.filters.model === row.model;
      const providerTotal = providerTotals.get(provider);
      const trend = sparklineBuckets.get(modelKey(provider, row.model)) || [];
      const tokenPct = (Number(row.total_tokens || 0) / totalTokens) * 100;
      const burnPct = (Number(row.burn_1h || 0) / maxBurn1h) * 100;
      const eventPct = (Number(row.event_count || 0) / maxEvents) * 100;
      const costPct = (Number(row.estimated_cost_usd || 0) / maxCost) * 100;
      const actualPct = (Number(row.actual_charge_usd || 0) / maxActual) * 100;
      const billingMode = row.subscription?.billing_mode || "unknown";
      const actualTitle =
        billingMode === "subscription"
          ? "Subscription-covered usage: $0 actual cost in Tokut"
          : billingMode === "api_billed"
            ? "API-billed account: estimated actual cost until reconciled"
            : "Billing mode unknown: actual cost held at $0 until configured";
      return `
        <tr class="${selectedProvider || selectedModel ? "selected" : ""}" style="--provider-color:${color}">
          <td>
            <button class="provider-cell table-action" type="button" data-provider-row="${escapeHtml(provider)}"
              title="${selectedProvider ? "Clear provider filter" : `Filter to ${providerLabel(provider)}`}">
              ${
                logo
                  ? `<img class="provider-logo" src="${logo}" alt="" />`
                  : `<span class="provider-logo fallback">${escapeHtml(providerLabel(provider).charAt(0))}</span>`
              }
              <span>
                <strong>${escapeHtml(providerLabel(provider))}</strong>
                <small>${fmt(providerTotal?.event_count || row.event_count)} events total</small>
              </span>
            </button>
          </td>
          <td>
            <button class="model-cell table-action" type="button" data-model-row="${escapeHtml(row.model)}"
              title="${selectedModel ? "Clear model filter" : `Filter to ${escapeHtml(row.model || "unknown")}`}">
              <strong>${escapeHtml(row.model || "unknown")}</strong>
              <small>${escapeHtml(row.pricing_source || "pricing unknown")}</small>
            </button>
          </td>
          <td class="spark-cell" title="Recent minute token burn">${modelSparkline(trend)}</td>
          <td class="num right metric-cell" style="--pct:${clampPct(tokenPct)}" title="${fmt(row.total_tokens)} tokens">
            <span>${compact(row.total_tokens)}</span>
          </td>
          <td class="num right metric-cell share-cell" style="--pct:${clampPct(share)}">
            <span>${pct(share)}</span>
          </td>
          <td class="num right metric-cell" style="--pct:${clampPct(burnPct)}" title="${fmt(row.burn_1h)} tokens in last hour">
            <span>${compact(row.burn_1h)}</span>
          </td>
          <td class="num right metric-cell" style="--pct:${clampPct(eventPct)}">
            <span>${fmt(row.event_count)}</span>
          </td>
          <td class="num right metric-cell actual-cell" style="--pct:${clampPct(actualPct)}" title="${escapeHtml(actualTitle)}">
            <span>${money(row.actual_charge_usd)}</span>
          </td>
          <td class="num right metric-cell" style="--pct:${clampPct(costPct)}">
            <span>${money(row.estimated_cost_usd)}</span>
          </td>
        </tr>
      `;
    })
    .join("");

  $("provider-model-table").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Provider</th>
          <th>Model</th>
          <th>Trend</th>
          <th class="right">Tokens</th>
          <th class="right">Share</th>
          <th class="right">1h</th>
          <th class="right">Events</th>
          <th class="right">Actual $</th>
          <th class="right">API equiv</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
      <tfoot>
        <tr>
          <td colspan="3">Shown total</td>
          <td class="num right">${compact(totalTokens)}</td>
          <td class="num right">100%</td>
          <td class="num right">${compact(totalBurn1h)}</td>
          <td class="num right">${fmt(totalEvents)}</td>
          <td class="num right">${money(totalActual)}</td>
          <td class="num right">${money(totalCost)}</td>
        </tr>
      </tfoot>
    </table>
  `;

  document.querySelectorAll("[data-provider-row]").forEach((button) => {
    button.addEventListener("click", () => {
      const provider = button.dataset.providerRow;
      state.filters.provider = state.filters.provider === provider ? "" : provider;
      refreshWithFilters();
    });
  });
  document.querySelectorAll("[data-model-row]").forEach((button) => {
    button.addEventListener("click", () => {
      const model = button.dataset.modelRow;
      state.filters.model = state.filters.model === model ? "" : model;
      refreshWithFilters();
    });
  });
}

function renderSubscriptions(subscriptions) {
  $("subscription-count").textContent = `${fmt(subscriptions.length)} accounts`;
  if (!subscriptions.length) {
    $("subscriptions").innerHTML = `<p class="empty">No provider accounts in the current slice.</p>`;
    return;
  }
  $("subscriptions").innerHTML = subscriptions
    .map((row) => {
      const mode = row.billing_mode || "unknown";
      const actual = Number(row.actual_charge_usd || 0);
      const theoretical = Number(row.theoretical_api_equivalent_usd || 0);
      const planCredits = Number(row.plan_credits_usd ?? (mode === "subscription" ? theoretical : 0));
      const metered = Number(row.metered_usd || 0);
      const color = providerColor(row.provider);
      const detail =
        mode === "subscription"
          ? `${money(planCredits)} credits · ${money(metered)} metered`
          : `${money(theoretical)} meter`;
      return `
        <div class="subscription-row" title="${escapeHtml(subscriptionTooltip(row))}">
          <span class="provider-dot" style="background:${color}"></span>
          <span class="subscription-main">
            <span class="subscription-company">${escapeHtml(row.company || "Unassigned")}</span>
            <span class="subscription-meta">${escapeHtml(providerLabel(row.provider))} / ${escapeHtml(row.account)} · ${escapeHtml(row.subscription || row.plan || "Unknown")} · ${escapeHtml(mode)}</span>
          </span>
          <span class="subscription-money">
            <strong class="num">${money(actual)}</strong>
            <small>${detail}</small>
          </span>
        </div>
      `;
    })
    .join("");
}

function subscriptionTooltip(row) {
  const included = row.included || {};
  const overage = row.overage || {};
  return [
    `Company: ${row.company || "Unassigned"}`,
    `Provider/account: ${providerLabel(row.provider)} / ${row.account}`,
    `Subscription: ${row.subscription || row.plan || "Unknown"}`,
    `Billing mode: ${row.billing_mode || "unknown"}`,
    `Included allowance: ${money(included.allowance_usd)} / ${included.period || "month"}`,
    `Overage: ${overage.mode || "none"} cap ${money(overage.monthly_cap_usd)}`,
    `Meter: ${money(row.theoretical_api_equivalent_usd)}`,
    `Plan credits (discounted): ${money(row.plan_credits_usd)}`,
    `Metered above plan: ${money(row.metered_usd)}`,
    `Cash exposure: ${money(row.actual_charge_usd)} (max ${money(row.cash_exposure_max_usd)})`,
    `Events: ${fmt(row.event_count)}`,
    `Tokens: ${fmt(row.total_tokens)}`,
    row.configured ? "Configured in subscription file" : "Not configured; assign this account to a company",
  ].join("\n");
}

function modelTooltip(row) {
  const subscription = row.subscription || {};
  const billingMode = row.billing_mode || subscription.billing_mode || "unknown";
  const theoretical = Number(row.estimated_cost_usd || 0);
  const actual = billingMode === "subscription" ? 0 : billingMode === "api_billed" ? theoretical : Number(row.actual_charge_usd || 0);
  return [
    `Model: ${row.model || "unknown"}`,
    `Provider: ${providerLabel(row.provider)}`,
    `Company: ${row.company || subscription.company || "Unassigned"}`,
    `Account: ${row.account || subscription.account || "default"}`,
    `Subscription: ${subscription.subscription || subscription.plan || row.plan || "Unknown"}`,
    `Billing mode: ${billingMode}`,
    `API-equivalent cost: ${money(theoretical)}`,
    `Actual charged cost: ${money(actual)}`,
    `Tokens: ${fmt(row.total_tokens)}`,
    `Events: ${fmt(row.event_count)}`,
    "Click to filter this model",
    freshnessText(state.generatedAt),
  ].join("\n");
}

function renderWindows(windows) {
  const labels = ["5m", "30m", "1h", "5h", "7d"];
  const max = Math.max(1, ...labels.map((label) => windows[label]?.total_tokens || 0));
  $("windows").innerHTML = labels
    .map((label) => {
      const usage = windows[label] || {};
      const width = Math.max(((usage.total_tokens || 0) / max) * 100, usage.total_tokens ? 2 : 0);
      return `
        <div class="window">
          <div class="window-top">
            <span class="window-label">${label}</span>
            <strong class="num" title="${fmt(usage.total_tokens)} tokens">${compact(usage.total_tokens)}</strong>
          </div>
          <div class="bar"><span style="width:${width}%"></span></div>
          <small>${money(usage.estimated_cost_usd)} · uncached ${compact(usage.uncached_input_tokens)} · out ${compact(usage.output_tokens)}</small>
        </div>
      `;
    })
    .join("");
}

function renderModels(models) {
  const sorted = sortRows(models);
  const rows = sorted.slice(0, 12);
  $("model-count").textContent = `${fmt(rows.length)} of ${fmt(models.length)} models`;
  if (!rows.length) {
    $("models").innerHTML = `<p class="empty">No priced model events yet.</p>`;
    return;
  }
  const maxCost = Math.max(0.00000001, ...rows.map((row) => row.estimated_cost_usd || 0));
  $("models").innerHTML = rows
    .map((row) => {
      const color = providerColor(row.provider);
      const width = Math.max(((row.estimated_cost_usd || 0) / maxCost) * 100, row.estimated_cost_usd ? 2 : 0);
      const selected = state.filters.model === row.model;
      return `
        <button class="model-row ${selected ? "selected" : ""}" type="button"
          data-model="${escapeHtml(row.model)}" style="--provider-color:${color}"
          title="${escapeHtml(modelTooltip(row))}">
          <span class="provider-dot" style="background:${color}" title="${escapeHtml(providerLabel(row.provider))}"></span>
          <span class="model-main">
            <span class="model-name">${escapeHtml(row.model)}</span>
            <span class="model-meta">${escapeHtml(providerLabel(row.provider))} · ${fmt(row.event_count)} events · ${compact(row.total_tokens)} tokens</span>
          </span>
          <span class="model-cost">
            <strong class="num">${money(row.estimated_cost_usd)}</strong>
            <small>${money(row.cost_1h_usd)} / 1h</small>
          </span>
          <span class="bar model-bar"><span style="width:${width}%; background:${color}"></span></span>
        </button>
      `;
    })
    .join("");

  document.querySelectorAll("[data-model]").forEach((row) => {
    row.addEventListener("click", () => {
      const model = row.dataset.model;
      state.filters.model = state.filters.model === model ? "" : model;
      refreshWithFilters();
    });
  });
}

function renderMinuteCosts(minutes, minuteModels) {
  const rows = minutes.slice(0, 18);
  $("minute-count").textContent = `${fmt(rows.length)} of ${fmt(minutes.length)} minutes`;
  if (!rows.length) {
    $("minute-costs").innerHTML = `<p class="empty">No minute cost buckets yet.</p>`;
    return;
  }
  const modelBuckets = new Map();
  minuteModels.forEach((row) => {
    const bucket = modelBuckets.get(row.minute) || [];
    bucket.push(row);
    modelBuckets.set(row.minute, bucket);
  });
  const maxCost = Math.max(0.00000001, ...rows.map((row) => row.estimated_cost_usd || 0));
  $("minute-costs").innerHTML = rows
    .map((row) => {
      const width = Math.max(((row.estimated_cost_usd || 0) / maxCost) * 100, row.estimated_cost_usd ? 2 : 0);
      const minute = minuteLabel(row.minute);
      const topModels = (modelBuckets.get(row.minute) || [])
        .slice(0, 3)
        .map((modelRow) => `${escapeHtml(modelRow.model)} ${money(modelRow.estimated_cost_usd)}`)
        .join(" · ");
      return `
        <div class="minute-row">
          <span class="minute-main">
            <span class="minute-time">${minute}</span>
            <span class="minute-meta">${fmt(row.event_count)} events · ${compact(row.total_tokens)} tokens${topModels ? ` · ${topModels}` : ""}</span>
          </span>
          <span class="minute-cost">
            <strong class="num">${money(row.estimated_cost_usd)}</strong>
            <small>${fmt(row.priced_event_count)} priced</small>
          </span>
          <span class="bar minute-bar"><span style="width:${width}%"></span></span>
        </div>
      `;
    })
    .join("");
}

function minuteLabel(isoMinute) {
  if (!isoMinute) return "unknown";
  const date = new Date(isoMinute);
  if (Number.isNaN(date.getTime())) return isoMinute;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function renderBreakdown(breakdowns) {
  const tabs = [
    ["project", "Project"],
    ["account", "Account"],
    ["model", "Model"],
    ["user", "User"],
    ["day", "Day"],
    ["hour", "Hour"],
  ];
  $("breakdown-tabs").innerHTML = tabs
    .map(
      ([key, label]) =>
        `<button class="tab ${state.breakdown === key ? "active" : ""}" type="button" role="tab"
          aria-selected="${state.breakdown === key}" data-breakdown="${key}">${label}</button>`
    )
    .join("");
  document.querySelectorAll("[data-breakdown]").forEach((button) => {
    button.addEventListener("click", () => {
      state.breakdown = button.dataset.breakdown;
      renderBreakdown(state.dashboard?.breakdowns || {});
    });
  });

  const rows = sortRows(breakdowns[state.breakdown] || []).slice(0, 10);
  $("breakdowns").innerHTML =
    rows
      .map((row, index) => {
        const color = providerColor(row.provider);
        const filtered = state.filters[state.breakdown] === String(row.value);
        const label = breakdownLabel(row);
        const cost = Number(row.estimated_cost_usd || 0);
        const costShare = row.cost_share_percent ?? 0;
        const figure = cost ? money(cost) : compact(row.total_tokens);
        const figureTitle = cost ? `${money(cost)} estimated` : `${fmt(row.total_tokens)} tokens`;
        const share = cost ? costShare : row.share_percent;
        return `
          <button class="breakdown-row ${filtered ? "selected" : ""}" type="button"
            data-slice-key="${state.breakdown}" data-slice-value="${escapeHtml(String(row.value))}"
            title="${filtered ? "Clear this slice" : `Slice by ${state.breakdown}: ${escapeHtml(label)}`}">
            <span class="rank">${index + 1}</span>
            <span class="breakdown-main">
              <span class="breakdown-label">${escapeHtml(label)}</span>
              <span class="breakdown-meta">${money(row.cost_1h_usd)} / 1h · ${compact(row.burn_1h)} tok / 1h · ${fmt(row.event_count)} events</span>
            </span>
            <span class="breakdown-figures">
              <strong class="num" title="${figureTitle}">${figure}</strong>
              <small>${pct(share)}</small>
            </span>
            <span class="bar breakdown-bar"><span style="width:${Math.min(share || 0, 100)}%; background:${color}"></span></span>
          </button>
        `;
      })
      .join("") || `<p class="empty">No breakdown for this slice yet.</p>`;

  document.querySelectorAll("[data-slice-key]").forEach((row) => {
    row.addEventListener("click", () => {
      const key = row.dataset.sliceKey;
      const value = row.dataset.sliceValue;
      state.filters[key] = state.filters[key] === value ? "" : value;
      refreshWithFilters();
    });
  });
}

function renderAccounts(accounts) {
  const rows = sortRows(accounts).slice(0, 8);
  const max1h = Math.max(1, ...rows.map((account) => account.burn_1h || 0));
  $("accounts").innerHTML =
    rows
      .map((account) => {
        const color = providerColor(account.provider);
        const width = Math.max(((account.burn_1h || 0) / max1h) * 100, account.burn_1h ? 2 : 0);
        return `
          <div class="account-row">
            <span class="provider-dot" style="background:${color}" title="${escapeHtml(providerLabel(account.provider))}"></span>
            <span class="account-main">
              <span class="account-name" title="${escapeHtml(providerLabel(account.provider))} / ${escapeHtml(account.account)}">${escapeHtml(account.account)}</span>
              <span class="account-meta">${fmt(account.event_count)} events · ${money(account.cost_1h_usd)} / 1h · 5h ${compact(account.burn_5h)}</span>
            </span>
            <strong class="num" title="${money(account.estimated_cost_usd)} estimated">${money(account.cost_1h_usd)}</strong>
            <span class="bar account-bar"><span style="width:${width}%; background:${color}"></span></span>
          </div>
        `;
      })
      .join("") || `<p class="empty">No accounts found.</p>`;
}

function breakdownLabel(row) {
  if (row.dimension === "provider") return providerLabel(String(row.value || row.provider));
  if (row.dimension === "account") return `${providerLabel(row.provider)} / ${row.account || row.value}`;
  if (row.dimension === "model") return `${providerLabel(row.provider)} / ${row.value || row.model || row.label}`;
  return row.label;
}

function renderSessions(sessions) {
  const items = sortRows(sessions).slice(0, 14);
  $("session-count").textContent = `${fmt(items.length)} of ${fmt(sessions.length)} shown`;
  if (!items.length) {
    $("sessions").innerHTML = `<p class="empty">No token events yet.</p>`;
    return;
  }
  const header = `
    <div class="session-row session-header" aria-hidden="true">
      <span></span>
      <span>Session</span>
      <span>Project</span>
      <span>Account · Model</span>
      <span class="right">Seen</span>
      <span class="right">1h cost</span>
      <span class="right">Total</span>
    </div>
  `;
  $("sessions").innerHTML =
    header +
    items
      .map((session) => {
        const name = session.thread_name || session.session_id;
        const color = providerColor(session.provider);
        return `
          <div class="session-row">
            <span class="provider-dot" style="background:${color}" title="${escapeHtml(providerLabel(session.provider))}"></span>
            <span class="session-name">
              <strong title="${escapeHtml(name)}">${escapeHtml(name)}</strong>
              <code title="${escapeHtml(session.session_id)}">${escapeHtml(session.session_id)}</code>
            </span>
            <span class="cell-clip" title="${escapeHtml(session.project)}">${escapeHtml(session.project)}</span>
            <span class="cell-clip" title="${escapeHtml(session.account)}${session.model ? ` · ${escapeHtml(session.model)}` : ""}">
              ${escapeHtml(session.account)}${session.model ? ` · ${escapeHtml(session.model)}` : ""}
            </span>
            <span class="right session-age">${ageText(session.latest_at)}</span>
            <strong class="right num" title="${fmt(session.burn_1h)} tokens in last hour">${money(session.cost_1h_usd)}</strong>
            <strong class="right num" title="${fmt(session.total_tokens)} tokens · ${money(session.estimated_cost_usd)} estimated">${compact(session.total_tokens)}</strong>
          </div>
        `;
      })
      .join("");
}

function renderChatDrawer(sessions, current) {
  const sorted = [...sessions].sort((a, b) => new Date(b.latest_at || 0).getTime() - new Date(a.latest_at || 0).getTime());
  const currentId = current?.session_id || "";
  const burning = sorted
    .filter((session) => session.session_id === currentId || Number(session.burn_1h || 0) > 0)
    .sort((a, b) => Number(b.cost_1h_usd || 0) - Number(a.cost_1h_usd || 0) || Number(b.burn_1h || 0) - Number(a.burn_1h || 0))
    .slice(0, 8);
  const quiet = sorted.filter((session) => !burning.some((hot) => hot.session_id === session.session_id)).slice(0, 8);
  const projectGroups = new Map();
  sorted.slice(0, 80).forEach((session) => {
    const project = session.project || "Unknown";
    if (!projectGroups.has(project)) {
      projectGroups.set(project, { sessions: [], burn_1h: 0, cost_1h_usd: 0, total_tokens: 0 });
    }
    const group = projectGroups.get(project);
    group.sessions.push(session);
    group.burn_1h += Number(session.burn_1h || 0);
    group.cost_1h_usd += Number(session.cost_1h_usd || 0);
    group.total_tokens += Number(session.total_tokens || 0);
  });

  const projectRows = [...projectGroups.entries()].sort(
    (a, b) => b[1].cost_1h_usd - a[1].cost_1h_usd || b[1].burn_1h - a[1].burn_1h || b[1].total_tokens - a[1].total_tokens
  );
  $("chat-burning-count").textContent = fmt(burning.length);
  $("chat-project-count").textContent = fmt(projectRows.length);
  $("chat-quiet-count").textContent = fmt(quiet.length);
  $("chat-automation-count").textContent = fmt(sorted.length);
  $("chat-drawer-count").textContent = `${fmt(sessions.length)} chats`;
  $("burning-chats").innerHTML = burning.length
    ? burning.map((session) => chatRow(session, currentId, true)).join("")
    : `<p class="chat-empty">No chats burning in the last hour</p>`;
  $("quiet-chats").innerHTML = quiet.length
    ? quiet.map((session) => chatRow(session, currentId, false)).join("")
    : `<p class="chat-empty">No quiet recent chats</p>`;
  $("project-chats").innerHTML =
    projectRows
      .slice(0, 14)
      .map(([project, group]) => {
        const rows = group.sessions.sort(
          (a, b) => Number(b.cost_1h_usd || 0) - Number(a.cost_1h_usd || 0) || new Date(b.latest_at || 0).getTime() - new Date(a.latest_at || 0).getTime()
        );
        const active = group.burn_1h > 0;
        const meterPct = projectRows[0]?.[1]?.burn_1h ? (group.burn_1h / projectRows[0][1].burn_1h) * 100 : 0;
        return `
          <section class="project-chat-group">
            <button class="project-chat-heading" type="button" data-chat-project="${escapeHtml(project)}">
              <span class="folder-icon" aria-hidden="true"></span>
              <span>
                <strong>${escapeHtml(project)}</strong>
                <small>${money(group.cost_1h_usd)} / 1h · ${compact(group.burn_1h)} tok</small>
              </span>
              ${active ? `<i class="live-pin" aria-label="Live"></i>` : `<span class="project-chat-age">${fmt(rows.length)}</span>`}
            </button>
            <div class="project-meter" aria-hidden="true"><span style="width:${clampPct(meterPct)}%"></span></div>
            <div class="chat-list">
              ${rows.slice(0, 5).map((session) => chatRow(session, currentId, false)).join("") || `<p class="chat-empty">No chats</p>`}
            </div>
          </section>
        `;
      })
      .join("") || `<p class="chat-empty">No project chats yet</p>`;

  document.querySelectorAll("[data-chat-project]").forEach((button) => {
    button.addEventListener("click", () => {
      const project = button.dataset.chatProject;
      state.filters.project = state.filters.project === project ? "" : project;
      refreshWithFilters();
    });
  });
  document.querySelectorAll("[data-chat-session-project]").forEach((button) => {
    button.addEventListener("click", () => {
      const project = button.dataset.chatSessionProject;
      state.filters.project = state.filters.project === project ? "" : project;
      refreshWithFilters();
    });
  });
  document.querySelectorAll("[data-chat-scope]").forEach((button) => {
    button.addEventListener("click", () => {
      const scope = button.dataset.chatScope;
      if (scope === "hot") $("burning-chats")?.scrollIntoView({ block: "start" });
      if (scope === "projects") $("project-chats")?.scrollIntoView({ block: "start" });
      if (scope === "quiet") $("quiet-chats")?.scrollIntoView({ block: "start" });
      if (scope === "all") $("view-sessions")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function chatRow(session, currentId, pinned) {
  const isCurrent = session.session_id === currentId;
  const live = Number(session.burn_1h || 0) > 0;
  const name = session.thread_name || session.session_id;
  const costText = Number(session.cost_1h_usd || 0) ? `${money(session.cost_1h_usd)} / 1h` : `${compact(session.burn_1h)} tok / 1h`;
  return `
    <button class="chat-row ${isCurrent ? "current" : ""} ${live ? "live" : ""} ${pinned ? "pinned" : ""}" type="button"
      data-chat-session-project="${escapeHtml(session.project || "Unknown")}"
      title="${escapeHtml(chatTooltip(session))}">
      <span class="chat-title">${escapeHtml(name)}</span>
      <span class="chat-meta">${escapeHtml(providerLabel(session.provider))} · ${escapeHtml(session.model || "unknown")}</span>
      <span class="chat-age">${ageText(session.latest_at)}</span>
      <span class="chat-burn">${costText}</span>
      <span class="chat-status" aria-label="${live ? "Live burn" : "Idle"}"></span>
    </button>
  `;
}

function chatTooltip(session) {
  return [
    session.thread_name || session.session_id,
    `Project: ${session.project || "Unknown"}`,
    `Provider: ${providerLabel(session.provider)}`,
    `Model: ${session.model || "unknown"}`,
    `Last seen: ${ageText(session.latest_at)}`,
    `1h burn: ${fmt(session.burn_1h)} tokens`,
    `Total: ${fmt(session.total_tokens)} tokens`,
    `API equivalent: ${money(session.estimated_cost_usd)}`,
    "Click to filter dashboard by project",
  ].join("\n");
}

function sortRows(rows) {
  const copy = [...rows];
  const fieldForSort = {
    cost: ["estimated_cost_usd", "cost_1h_usd"],
    tokens: ["total_tokens", "burn_1h"],
    events: ["event_count"],
    recent: ["latest_at"],
    name: ["label", "thread_name", "project", "account", "model", "session_id"],
  }[state.sort] || ["estimated_cost_usd"];

  return copy.sort((a, b) => {
    if (state.sort === "name") {
      return String(firstValue(a, fieldForSort) || "").localeCompare(String(firstValue(b, fieldForSort) || ""));
    }
    if (state.sort === "recent") {
      return new Date(firstValue(b, fieldForSort) || 0).getTime() - new Date(firstValue(a, fieldForSort) || 0).getTime();
    }
    return Number(firstValue(b, fieldForSort) || 0) - Number(firstValue(a, fieldForSort) || 0);
  });
}

function firstValue(row, keys) {
  for (const key of keys) {
    if (row[key] !== undefined && row[key] !== null && row[key] !== "") return row[key];
  }
  return "";
}

function renderLimits(primary, secondary) {
  const rows = [
    ["5h primary", primary],
    ["7d secondary", secondary],
  ];
  $("limits").innerHTML = rows
    .map(([label, data]) => {
      const used = Number(data?.used_percent || 0);
      const color = used > 80 ? "var(--hot)" : used > 60 ? "var(--warn)" : "var(--gemini)";
      return `
        <div class="limit-row">
          <span class="limit-label">${label}</span>
          <span class="limit-figures">
            <strong class="num">${pct(used)}</strong>
            <small>${resetText(data?.resets_at)}</small>
          </span>
          <span class="bar limit-bar"><span style="width:${Math.min(used, 100)}%; background:${color}"></span></span>
        </div>
      `;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function queryString() {
  const params = new URLSearchParams();
  Object.entries(state.filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

async function fetchSnapshot() {
  try {
    const response = await fetch(`/api/snapshot${queryString()}`);
    render(await response.json());
  } catch {
    setConnection(false);
  }
}

function connectEvents() {
  if (state.source) {
    state.source.close();
  }
  const source = new EventSource(`/events${queryString()}`);
  state.source = source;
  source.addEventListener("open", () => setConnection(true));
  source.addEventListener("error", () => setConnection(false));
  source.addEventListener("snapshot", (event) => {
    setConnection(true);
    render(JSON.parse(event.data));
  });
}

function refreshWithFilters() {
  fetchSnapshot();
  connectEvents();
}

function setDrawerOpen(open) {
  state.drawerOpen = open;
  document.body.classList.toggle("drawer-open", open);
  $("control-drawer").setAttribute("aria-hidden", String(!open));
  $("drawer-toggle").setAttribute("aria-expanded", String(open));
}

function setChatDrawerOpen(open) {
  state.chatDrawerOpen = open;
  document.body.classList.toggle("chat-drawer-open", open);
  $("chat-drawer").setAttribute("aria-hidden", String(!open));
  $("chat-drawer-toggle").setAttribute("aria-expanded", String(open));
}

function setupChrome() {
  $("drawer-toggle").addEventListener("click", () => setDrawerOpen(!state.drawerOpen));
  $("drawer-close").addEventListener("click", () => setDrawerOpen(false));
  $("drawer-done").addEventListener("click", () => setDrawerOpen(false));
  $("chat-drawer-toggle").addEventListener("click", () => setChatDrawerOpen(!state.chatDrawerOpen));
  $("chat-drawer-close").addEventListener("click", () => setChatDrawerOpen(false));
  $("mtd-spend-focus").addEventListener("input", (event) => {
    state.mtdSpendFocus = Number(event.target.value || 100);
    renderMtdSpendChart(state.dashboard?.mtd_spend || []);
  });

  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-view-target]").forEach((item) => item.classList.toggle("active", item === button));
      const target = document.getElementById(button.dataset.viewTarget);
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.drawerOpen) setDrawerOpen(false);
    if (event.key === "Escape" && state.chatDrawerOpen) setChatDrawerOpen(false);
  });
}

async function boot() {
  setupChrome();
  await fetchSnapshot();
  connectEvents();
}

boot();
