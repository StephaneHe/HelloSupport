// HelloSupport web demo — vanilla JS: config, health, Server-Sent Events trace rendering.
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const NEEDS_RETRIEVAL = ["malfunction", "documentation"];
const CATEGORY_HELP = {
  malfunction: "a failure reported on postgres / nginx / redis → documentalist, then technician with get_service_status REQUIRED",
  documentation: "“what should I check?” → documentalist, then technician without tool (sourced checklist)",
  history: "incident history → technician directly, query_incidents (SQL) REQUIRED",
  out_of_scope: "another product → technician directly, no tool: states its limits",
  vague: "service unclear → technician directly, no tool: asks one clarifying question",
};
let CONFIG = null;
let source = null;
let llmCalls = {};

// ------------------------------------------------------------------ theme
const theme = localStorage.getItem("hs-theme") ||
  (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
document.documentElement.dataset.theme = theme;
$("#theme").onclick = () => {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = t;
  localStorage.setItem("hs-theme", t);
};

// ------------------------------------------------------------------ init
async function init() {
  CONFIG = await (await fetch("/api/config")).json();
  $("#version").textContent = "v" + CONFIG.version;
  for (const m of CONFIG.models) $("#model").add(new Option(`${m.label}`, m.alias, false, m.alias === CONFIG.default_model));
  for (const s of CONFIG.scenarios) $("#scenario").add(new Option(`${s.id} — ${s.label}`, s.id));
  if (CONFIG.docs_url) {
    for (const [id, path] of [["#docs-link", "/"], ["#arch-link", "/#architecture"]]) {
      $(id).href = CONFIG.docs_url + path;
      $(id).hidden = false;
    }
  }
  $("#cases").innerHTML = CONFIG.cases.map((c) =>
    `<button class="case" data-id="${c.id}" title="${esc(c.question)}">
       <b><span class="cid">${c.id}</span>${esc(c.label)}</b><small>${esc(c.question)} · ${c.scenario}</small>
     </button>`).join("");
  document.querySelectorAll(".case").forEach((b) => b.onclick = () => {
    const c = CONFIG.cases.find((x) => x.id === b.dataset.id);
    $("#question").value = c.question;
    $("#scenario").value = c.scenario;
    ask();
  });
  $("#ask-form").onsubmit = (e) => { e.preventDefault(); ask(); };
  health();
  setInterval(health, 15000);
}

async function health() {
  try {
    const h = await (await fetch("/api/health")).json();
    const pill = $("#health");
    if (!h.llm.reachable) { pill.className = "pill err"; pill.textContent = "LM Studio offline"; return; }
    const missing = Object.values(h.models).filter((id) => !h.llm.available.includes(id));
    if (missing.length) { pill.className = "pill warn"; pill.textContent = "model missing: " + missing.join(", "); return; }
    if (h.tools !== "ready") { pill.className = "pill warn"; pill.textContent = "tools " + h.tools; return; }
    pill.className = "pill ok";
    pill.textContent = h.busy ? `ready · busy (${h.waiting} waiting)` : "ready";
    pill.title = "Loaded in LM Studio: " + (h.llm.loaded.join(", ") || "none (loaded on first use)");
  } catch { $("#health").className = "pill err"; $("#health").textContent = "server unreachable"; }
}

// ------------------------------------------------------------------ run
function setStatus(text, cls) { const p = $("#run-status"); p.textContent = text; p.className = "pill " + cls; }

function resetRun() {
  $("#trace").innerHTML = ""; $("#sources").innerHTML = ""; $("#metrics").innerHTML = "";
  $("#answer").className = "answer muted"; $("#answer").textContent = "Working…";
  llmCalls = {};
  document.querySelectorAll(".step").forEach((s) => s.classList.remove("done", "skipped", "active"));
  $("#category").innerHTML = "Waiting for the triage…";
}

function ask() {
  const question = $("#question").value.trim();
  if (!question) return;
  if (source) source.close();
  resetRun();
  $("#ask-btn").disabled = true;
  document.querySelectorAll(".case").forEach((b) => b.disabled = true);
  setStatus("starting", "run");
  if (innerWidth < 900) $("#answer").scrollIntoView({ behavior: "smooth", block: "start" });  // mobile: show the answer card
  const params = new URLSearchParams({ question, model: $("#model").value, scenario: $("#scenario").value });
  source = new EventSource("/api/ask?" + params);
  source.addEventListener("queued", (e) => setStatus(`queued (#${JSON.parse(e.data).position})`, "warn"));
  source.addEventListener("status", (e) => { const d = JSON.parse(e.data); addEv("status", "", `<span class="who">server</span> ${esc(d.stage)}${d.model ? ` · <code>${esc(d.model)}</code>` : ""}${d.scenario ? ` · scenario <code>${esc(d.scenario)}</code>` : ""}`); setStatus("running", "run"); });
  source.addEventListener("trace", (e) => onTrace(JSON.parse(e.data)));
  source.addEventListener("result", (e) => onResult(JSON.parse(e.data)));
  source.addEventListener("error", (e) => {
    if (e.data) { const d = JSON.parse(e.data); showError(d.message); }
  });
  source.addEventListener("done", finish);
  source.onerror = () => { if (source && source.readyState === EventSource.CLOSED) finish(); else if (source) { showError("Connection to the demo server lost."); finish(); } };
}

function finish() {
  if (source) { source.close(); source = null; }
  $("#ask-btn").disabled = false;
  document.querySelectorAll(".case").forEach((b) => b.disabled = false);
  health();
}

function showError(msg) {
  $("#answer").className = "answer";
  $("#answer").innerHTML = `<div class="error-box">${esc(msg)}</div>`;
  setStatus("error", "err");
  addEv("error", "", `<span class="who">error</span> ${esc(msg)}`);
}

// ------------------------------------------------------------------ trace rendering
function kindOf(agent) { return agent === "triage" ? "router" : (agent === "documentalist" || agent === "technician") ? "agent" : "code"; }

function addEv(cls, t, html) {
  const li = document.createElement("li");
  li.className = "ev " + cls;
  li.innerHTML = `<span class="t">${t === "" ? "" : Number(t).toFixed(1) + " s"}</span><div>${html}</div>`;
  const trace = $("#trace");
  trace.appendChild(li);
  trace.scrollTop = trace.scrollHeight;  // follow inside the trace box, not the whole page
}

function markStep(name, state) { const s = document.querySelector(`.step[data-step="${name}"]`); if (s) s.classList.add(state); }

function onTrace(e) {
  const who = `<span class="who">${esc(e.agent)}</span>`;
  if (e.type === "start") {
    document.querySelectorAll(".step.active").forEach((s) => { s.classList.remove("active"); s.classList.add("done"); });
    markStep(e.agent, "active");
    addEv(kindOf(e.agent), e.t, `${who} <span class="tag">${kindOf(e.agent).toUpperCase()}</span> started`);
  } else if (e.type === "llm") {
    llmCalls[e.agent] = (llmCalls[e.agent] || 0) + 1;
    let what;
    if (e.route) {
      what = `→ category <span class="cat">${esc(e.route.intent)}</span>${e.route.service ? ` · service <code>${esc(e.route.service)}</code>` : ""}`;
      showCategory(e.route);
    } else {
      what = e.tool_calls.length ? `→ proposes <code>${esc(e.tool_calls.join(", "))}</code>` : "→ answers in text";
    }
    const offered = e.tools_offered && e.tools_offered.length ? ` · tools offered: <code>${esc(e.tools_offered.join(", "))}</code>` : (e.agent === "triage" ? "" : " · no tool offered");
    addEv(kindOf(e.agent), e.t, `${who} LLM call ${e.agent === "triage" ? "" : "#" + llmCalls[e.agent] + "/3"} · ${e.latency_s.toFixed(2)} s · ${e.prompt_tokens}→${e.completion_tokens} tokens ${what}<div class="muted small"><code>${esc(e.model)}</code>${offered}</div>`);
  } else if (e.type === "tool_call") {
    const body = e.tool === "query_incidents"
      ? `<pre class="sql">${esc(e.arguments.sql)}</pre>`
      : ` <code>${esc(JSON.stringify(e.arguments))}</code>`;
    addEv("tool", e.t, `${who} calls MCP tool <b>${esc(e.tool)}</b>${body}`);
  } else if (e.type === "tool_result") {
    addEv(e.ok ? "tool" : "error", e.t, `${who} ← <b>${esc(e.tool)}</b> ${e.ok ? "ok" : "ERROR"} · ${e.duration_s.toFixed(2)} s${renderResult(e)}`);
  } else if (e.type === "limit") {
    const d = String(e.detail || "");
    const label = d.includes("answer discarded") ? "required tool ignored → answer rejected, retry"
      : d.includes("tools withheld") ? "last LLM call: tools withheld, final answer required"
      : d.includes("dropped") ? "duplicate / extra tool calls dropped" : "guardrail";
    addEv("limit", e.t, `${who} <b>${label}</b><div class="muted small">${esc(d)}</div>`);
  } else if (e.type === "error") {
    addEv("error", e.t, `${who} ${esc(e.detail)}`);
  }
}

function renderResult(e) {
  const r = e.result;
  if (!e.ok) return `<div class="small">${esc(typeof r === "string" ? r : JSON.stringify(r))}</div>`;
  if (e.tool === "query_incidents" && r && r.columns) {
    const head = r.columns.map((c) => `<th>${esc(c)}</th>`).join("");
    const rows = r.rows.map((row) => `<tr>${row.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("");
    return `<table class="rows"><tr>${head}</tr>${rows}</table><div class="muted small">${r.row_count} row(s)${r.truncated ? ", truncated" : ""}</div>`;
  }
  if (e.tool === "search_docs" && Array.isArray(r)) {
    return `<ul class="hits">${r.map((h) => `<li class="${h.relevant ? "" : "off"}"><code>${esc(h.doc_id)}#${esc(h.section)}</code> · rerank ${Number(h.rerank_score).toFixed(1)} · cosine ${Number(h.score).toFixed(2)}${h.relevant ? "" : " · off-topic"}</li>`).join("")}</ul>`;
  }
  if (e.tool === "get_service_status" && r && r.status) {
    return ` → <b>${esc(r.service)} = ${esc(r.status)}</b> <span class="muted small">(simulated, scenario ${esc(r.scenario)})</span>`;
  }
  return `<pre class="json">${esc(JSON.stringify(r, null, 1))}</pre>`;
}

function showCategory(route) {
  markStep("triage", "done");
  document.querySelector('.step[data-step="triage"]').classList.remove("active");
  if (!NEEDS_RETRIEVAL.includes(route.intent)) markStep("documentalist", "skipped");
  $("#category").innerHTML = `Category <span class="cat">${esc(route.intent)}</span>${route.service ? ` (service <code>${esc(route.service)}</code>)` : ""}: ${esc(CATEGORY_HELP[route.intent] || "")}`;
}

// ------------------------------------------------------------------ result
function docLink(cite) {
  const m = cite.match(/^([\w-]+)\.md#(.+)$/);
  if (!m || !CONFIG.docs_url) return null;
  return `${CONFIG.docs_url}/kb/${m[1]}/#${m[2].toLowerCase().replace(/\s+/g, "-")}`;
}

function onResult(r) {
  const steps = ["triage", "documentalist", "technician", "post-processing"];
  document.querySelectorAll(".step").forEach((s) => s.classList.remove("active", "done", "skipped"));
  for (const s of steps) markStep(s, r.path.includes(s) ? "done" : "skipped");
  if (r.route) showCategory(r.route);

  let html = esc(r.answer);
  for (const c of r.sources) {
    if (!c.includes(".md#")) continue;
    const href = docLink(c);
    const chip = href ? `<a class="cite" href="${href}" target="_blank" rel="noopener">${esc(c)}</a>` : `<span class="cite">${esc(c)}</span>`;
    html = html.split(esc(c)).join(chip);
  }
  $("#answer").className = "answer";
  $("#answer").innerHTML = html;
  $("#sources").innerHTML = r.sources.length
    ? "<span class='muted'>Sources:</span> " + r.sources.map((c) => { const h = docLink(c); return h ? `<a class="src" href="${h}" target="_blank" rel="noopener">${esc(c)}</a>` : `<span class="src">${esc(c)}</span>`; }).join("")
    : "<span class='muted'>No source cited.</span>";
  const m = r.metrics;
  const tile = (v, l) => `<div class="metric"><b>${v}</b>${l}</div>`;
  $("#metrics").innerHTML = [
    tile(m.total_s + " s", "total"), tile(m.llm_calls, "LLM calls"), tile(m.llm_s + " s", "LLM time"),
    tile(`${m.prompt_tokens} / ${m.completion_tokens}`, "tokens in / out"), tile(m.tool_calls, "tool calls"),
    tile(r.route ? r.route.intent : "—", "category"), tile(`<code>${esc(r.model)}</code>`, "model"),
  ].join("");
  const errs = r.errors.length ? `<div class="small">${r.errors.map(esc).join("<br>")}</div>` : "";
  if (r.path.includes("post-processing")) {
    addEv("code", "", `<span class="who">post-processing</span> <span class="tag">CODE</span> citations normalised, simulation note added · status <b>${esc(r.status)}</b>${errs}`);
  } else {
    addEv("error", "", `no post-processing (no answer from the technician) · status <b>${esc(r.status)}</b>${errs}`);
  }
  setStatus(r.status === "done" ? `done · ${m.total_s} s` : r.status, r.status === "done" ? "ok" : "err");
}

init();
