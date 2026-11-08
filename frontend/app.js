/* BantayPondo GUI
 * Live mode: uses the FastAPI backend (/api/snapshot, /api/chat with Gemini).
 * Static mode (GitHub Pages): loads data/snapshot.json and answers questions with
 * the same rule-based agents in the browser. Both modes cite every source.
 */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const peso = (n) => n == null ? "—" : n >= 1e9 ? `₱${(n / 1e9).toFixed(2)}B` : n >= 1e6 ? `₱${(n / 1e6).toFixed(1)}M` : `₱${Math.round(n).toLocaleString("en-PH")}`;
const pesoFull = (n) => n == null ? "—" : `₱${n.toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const num = (n) => n.toLocaleString("en-PH");
const title = (s) => (s || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\b(Of|De|Del|And|Ng)\b/g, (w) => w.toLowerCase());
const town = (m) => title((m || "").replace(/\s*\(.*?\)\s*/g, " ").trim());
const PORTAL = "https://transparency.dpwh.gov.ph/";

const RULES = {
  above_abc: { label: "Cost above approved budget", sev: 3, icon: '<path d="M12 19V5M5 12l7-7 7 7"/>' },
  contractor_concentration: { label: "One contractor dominates a province", sev: 2, icon: '<circle cx="12" cy="12" r="9"/><path d="M12 3v9l6.4 6.4"/>' },
  late_completion: { label: "Finished very late", sev: 1, icon: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2.5M9 2h6"/>' },
  possible_duplicate: { label: "Same work, several contracts", sev: 1, icon: '<rect x="8" y="8" width="12" height="12" rx="1"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>' },
  status_inconsistency: { label: "Status doesn't match progress", sev: 3, icon: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>' },
  overdue: { label: "Past deadline, not finished", sev: 2, icon: '<rect x="3" y="5" width="18" height="16" rx="1"/><path d="M3 10h18M8 3v4M16 3v4"/>' },
};
const DISCLAIMER = "Paalala: Ito ay mga palatandaan para suriin (flags for review), hindi patunay ng katiwalian. Always verify using the linked sources.";

let S = null;          // snapshot
let LIVE = false;      // backend available?
let shown = 25;
let filtered = [];
let byId = new Map();

async function load() {
  try {
    const r = await fetch("api/snapshot");
    if (!r.ok) throw 0;
    S = await r.json();
    LIVE = true;
  } catch {
    const r = await fetch("data/snapshot.json");
    S = await r.json();
  }
  S.projects.forEach((p) => byId.set(p.id, p));
  $("#dataNote").textContent = `${num(S.stats.projects)} DPWH flood control projects loaded · data as of ${S.generated_at.slice(0, 10)}`;
  $("#genAt").textContent = `Snapshot generated ${S.generated_at.slice(0, 10)}.`;
  $("#askMode").textContent = LIVE
    ? "Live mode: AI agents answer using only the stored records."
    : "Demo mode: agents run in your browser using the stored records. Run the backend for Gemini-written answers.";
  renderSample(); renderTiles(); renderStats(); renderFilters(); applyFilters();
  renderBars(); renderSources(); renderChips(); initMap();
}

/* ---------- sections ---------- */
function scoreClass(s) { return s >= 3 ? "high" : s === 2 ? "mid" : s === 1 ? "" : "none"; }
function flagTags(p) { return [...new Set(p.flags.map((f) => f[0]))].map((r) => `<span class="tag">${esc(RULES[r]?.label || r)}</span>`).join(""); }
function srcUrl(p) { return S.urls[p.u]; }            // exact file the record came from
function srcPage(p) { return S.sources[p.src]?.url || srcUrl(p); } // human-readable page

function renderSample() {
  const p = S.projects[0];
  $("#sample .sample-body").innerHTML = `
    <h3>${esc(p.name)}</h3>
    <dl>
      <dt>Location</dt><dd>${esc(town(p.muni))}, ${esc(title(p.prov))}</dd>
      <dt>Contractor</dt><dd>${esc(p.contractor)}</dd>
      <dt>Contract cost</dt><dd>${pesoFull(p.amount)}</dd>
      <dt>Risk score</dt><dd><span class="score ${scoreClass(p.score)}">${p.score}</span></dd>
    </dl>
    <div>${flagTags(p)}</div>
    <div class="links"><button class="btn" type="button" data-open="${p.id}">See why it's flagged</button></div>`;
}

function renderTiles() {
  $("#ruleTiles").innerHTML = Object.entries(RULES).filter(([k]) => S.rules[k]?.count).map(([k, r]) => {
    const info = S.rules[k] || { meaning: "", count: 0 };
    return `<div class="tile sev${r.sev}">
      <div class="ring"><svg viewBox="0 0 24 24">${r.icon}</svg></div>
      <h3>${esc(r.label)}</h3>
      <p>${esc(info.meaning)}</p>
      <div class="n">${num(info.count)}<small>projects flagged</small></div>
    </div>`;
  }).join("");
}

function renderStats() {
  const st = S.stats;
  const icon = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  $("#statRow").innerHTML = `
    <div class="stat">${icon('<path d="M3 21h18M5 21V10l7-5 7 5v11M9 21v-6h6v6"/>')}<div><b>${num(st.projects)}</b><span>projects checked</span></div></div>
    <div class="stat">${icon('<circle cx="12" cy="12" r="9"/><path d="M9 8h4a2.5 2.5 0 0 1 0 5H9V8zM9 13v4M7 10.5h8"/>')}<div><b>${peso(st.value)}</b><span>total contract cost</span></div></div>
    <div class="stat">${icon('<path d="M5 21V4M5 4h12l-2 4 2 4H5"/>')}<div><b>${num(st.flagged)}</b><span>projects flagged for review</span></div></div>
    <div class="stat">${icon('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>')}<div><b>${num(st.contractors)}</b><span>contractors</span></div></div>
    <p class="insight">Across all ${num(st.projects)} contracts, <strong>${(st.near_abc_share * 100).toFixed(1)}%</strong> were awarded within 0.1% of the approved budget. Procurement watchdogs often read bids that land right at the ceiling as a sign of weak competition. Because this pattern covers the whole program, it isn't counted as a flag on single projects.</p>`;
}

function renderFilters() {
  $("#fProv").insertAdjacentHTML("beforeend", S.provinces.map((p) => `<option value="${esc(p.name)}">${esc(title(p.name))} (${p.projects})</option>`).join(""));
  $("#fRule").insertAdjacentHTML("beforeend", Object.entries(RULES).filter(([k]) => S.rules[k]?.count).map(([k, r]) => `<option value="${k}">${esc(r.label)}</option>`).join(""));
  let t;
  ["#fQ", "#fProv", "#fRule", "#fFlagged"].forEach((id) => $(id).addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { shown = 25; applyFilters(); }, 150); }));
  $("#more").addEventListener("click", () => { shown += 25; renderRows(); });
  $("#heroSearch").addEventListener("submit", (e) => {
    e.preventDefault();
    $("#fQ").value = $("#heroQ").value;
    $("#fFlagged").checked = false;
    shown = 25; applyFilters();
    $("#explore").scrollIntoView();
  });
}

function matches(p, words) {
  const hay = `${p.code} ${p.name} ${p.muni} ${p.prov} ${p.contractor} ${p.region}`.toLowerCase();
  return words.every((w) => hay.includes(w));
}

function applyFilters() {
  const words = $("#fQ").value.toLowerCase().split(/\s+/).filter(Boolean);
  const prov = $("#fProv").value, rule = $("#fRule").value, flagged = $("#fFlagged").checked;
  filtered = S.projects.filter((p) =>
    (!prov || p.prov === prov) && (!flagged || p.score > 0) &&
    (!rule || p.flags.some((f) => f[0] === rule)) && (!words.length || matches(p, words)));
  $("#count").textContent = `${num(filtered.length)} project${filtered.length === 1 ? "" : "s"} · total ${peso(filtered.reduce((a, p) => a + (p.amount || 0), 0))}`;
  renderRows();
}

function renderRows() {
  const rows = filtered.slice(0, shown);
  $("#rows").innerHTML = rows.length ? rows.map((p) => `
    <tr data-open="${p.id}">
      <td><span class="score ${scoreClass(p.score)}" title="Risk score">${p.score}</span></td>
      <td><a class="pname" href="#" data-open="${p.id}">${esc(p.name)}</a><span class="code">${esc(p.code)}</span></td>
      <td>${esc(town(p.muni))}<br><span class="code">${esc(title(p.prov))}</span></td>
      <td>${esc(p.contractor)}</td>
      <td class="num">${peso(p.amount)}</td>
      <td>${flagTags(p) || '<span class="code">None</span>'}</td>
    </tr>`).join("") : `<tr><td colspan="6" class="empty">No projects match. Try another town, or untick "Flagged only".</td></tr>`;
  $("#more").hidden = filtered.length <= shown;
}

function renderBars() {
  const top = S.contractors.slice(0, 12), max = top[0]?.value || 1;
  $("#bars").innerHTML = top.map((c) => `
    <li><span class="bn"><button type="button" data-contractor="${esc(c.name)}">${esc(c.name)}</button><br><small>${c.projects} projects in ${c.provinces} province${c.provinces > 1 ? "s" : ""}${c.flagged ? ` · ${c.flagged} flagged` : ""}</small></span>
    <span class="bt"><i style="width:${(c.value / max * 100).toFixed(1)}%"></i></span>
    <span class="bv">${peso(c.value)}</span></li>`).join("");
}

function renderSources() {
  $("#srcGrid").innerHTML = Object.values(S.sources).map((s) => `
    <div class="src">
      <span class="badge ${s.official === false ? "mirror" : ""}">${s.official === false ? "Community copy · in use" : "Official source"}</span>
      <h3>${esc(s.name)}</h3>
      <p>${esc(s.covers)}</p>
      <p>${esc(s.publisher)}</p>
      <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a>
    </div>`).join("");
}

/* ---------- detail dialog ---------- */
function openDetail(id) {
  const p = byId.get(Number(id));
  if (!p) return;
  const flags = p.flags.length ? p.flags.map(([r, sev, d]) => `
    <div class="flag s${sev}"><strong>${esc(RULES[r]?.label || r)}</strong> · ${esc(d)}<p>${esc(S.rules[r]?.meaning || "")}</p></div>`).join("")
    : `<p class="muted">No checks flagged this project.</p>`;
  $("#dBody").innerHTML = `
    <span class="score ${scoreClass(p.score)}">${p.score}</span>
    <h2 id="dTitle">${esc(p.name)}</h2>
    <dl>
      <dt>Contract ID</dt><dd>${esc(p.code)}</dd>
      <dt>Type of work</dt><dd>${esc(p.cat || "—")}</dd>
      <dt>Location</dt><dd>${esc(town(p.muni))}, ${esc(title(p.prov))} (${esc(p.region)})</dd>
      <dt>Implementing office</dt><dd>${esc(p.office || "—")}</dd>
      <dt>Contractor</dt><dd>${esc(p.contractor)}</dd>
      <dt>Approved budget</dt><dd>${pesoFull(p.abc)}</dd>
      <dt>Contract cost</dt><dd>${pesoFull(p.amount)}</dd>
      <dt>Start</dt><dd>${esc(p.start || "—")}</dd>
      <dt>Target completion</dt><dd>${esc(p.target || "—")}</dd>
      <dt>Actual completion</dt><dd>${esc(p.done || "—")}</dd>
    </dl>
    <h3>Flags</h3>${flags}
    <div class="links">
      <a class="btn" href="${PORTAL}" target="_blank" rel="noopener" data-copy="${esc(p.code)}">Verify on DPWH portal</a>
      <a class="btn ghost" style="margin:0" href="${esc(srcPage(p))}" target="_blank" rel="noopener">View dataset page</a>
    </div>
    <p class="verify-tip" id="vTip"><span>On the DPWH portal, search for contract ID ${esc(p.code)}. Clicking the button copies it for you.</span>
      <br><a href="${esc(srcUrl(p))}" target="_blank" rel="noopener">Download raw CSV</a> (the exact file this record came from)</p>`;
  $("#detail").showModal();
}
document.addEventListener("click", (e) => {
  const cp = e.target.closest("[data-copy]");
  if (cp) {
    navigator.clipboard?.writeText(cp.dataset.copy).then(() => {
      const tip = $("#vTip");
      if (tip) tip.querySelector("span").textContent = `Copied ${cp.dataset.copy}. Paste it into the search box on the DPWH portal.`;
    }).catch(() => {});
    return; // let the link open normally
  }
  const o = e.target.closest("[data-open]");
  if (o) { e.preventDefault(); openDetail(o.dataset.open); return; }
  const c = e.target.closest("[data-contractor]");
  if (c) { $("#fQ").value = c.dataset.contractor; $("#fProv").value = ""; $("#fFlagged").checked = false; shown = 25; applyFilters(); $("#explore").scrollIntoView(); }
});

/* ---------- map ---------- */
function initMap() {
  if (!window.L) { $("#leaflet").innerHTML = '<p class="empty">The map could not load. Check your connection.</p>'; return; }
  const map = L.map("leaflet", { preferCanvas: true, scrollWheelZoom: false }).setView([12.3, 122.5], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors" }).addTo(map);
  const pts = [...S.projects].sort((a, b) => a.score - b.score); // risky dots on top
  for (const p of pts) {
    if (p.lat == null || p.lng == null) continue;
    const color = p.score >= 3 ? "#CE1126" : p.score === 2 ? "#F2B705" : p.score === 1 ? "#0038A8" : "#A3ADBC";
    L.circleMarker([p.lat, p.lng], { radius: p.score >= 3 ? 5 : 3.5, color, fillColor: color, fillOpacity: .8, weight: 1 })
      .bindPopup(`<strong>${esc(p.name)}</strong><br>${esc(town(p.muni))}, ${esc(title(p.prov))}<br>${peso(p.amount)} · risk ${p.score}<br><button type="button" data-open="${p.id}">Open project</button>`)
      .addTo(map);
  }
}

/* ---------- ask ---------- */
const CHIPS = ["Show suspicious projects in Bulacan", "Sino ang top contractors sa Cebu?", "Which projects cost more than the approved budget?", "Show projects finished very late in Pampanga"];
function renderChips() {
  $("#chips").innerHTML = CHIPS.map((c) => `<button type="button">${esc(c)}</button>`).join("");
  $("#chips").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") ask(e.target.textContent); });
  $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#askQ").value.trim(); if (q) { ask(q); $("#askQ").value = ""; } });
}

function bubble(html, who) {
  const d = document.createElement("div");
  d.className = `msg ${who}`;
  d.innerHTML = html;
  $("#chat").append(d);
  $("#chat").scrollTop = $("#chat").scrollHeight;
  return d;
}

async function ask(q) {
  bubble(esc(q), "me");
  const wait = bubble('<span class="typing">Agents are working…</span>', "bot");
  let out;
  if (LIVE) {
    try {
      const r = await fetch("api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      if (!r.ok) throw 0;
      const j = await r.json();
      out = { steps: j.steps, html: esc(j.answer).replace(/\n/g, "<br>"), cites: j.citations };
    } catch { out = localAsk(q); }
  } else out = localAsk(q);
  wait.innerHTML = `<div class="trace">${out.steps.map((s) => `<span>${esc(s)}</span>`).join("")}</div>${out.html}
    ${out.cites.length ? `<div class="cites"><strong>Sources</strong><ol>${out.cites.map((c) => `<li><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.label)}</a></li>`).join("")}</ol></div>` : ""}`;
  wait.querySelectorAll("[data-open]").forEach((a) => a.setAttribute("href", "#"));
}

/* Browser version of the backend agents (supervisor → analyst/contractors/auditor → explainer). */
function localAsk(q) {
  const ql = q.toLowerCase();
  const mentioned = (name) => name && name.length > 2 && new RegExp(`\\b${name.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(ql);
  const prov = [...S.provinces].sort((a, b) => b.name.length - a.name.length).find((p) => mentioned(p.name))?.name || null;
  const contractor = S.contractors.find((c) => mentioned(c.name))?.name || null;
  let rule = null;
  if (/approved budget|abc|above|lampas|sobra/.test(ql)) rule = "above_abc";
  else if (/late|delay|huli|tagal/.test(ql)) rule = "late_completion";
  else if (/split|duplicate|phase|ulit|pare-pareho/.test(ql)) rule = "possible_duplicate";
  else if (/dominat|concentrat|monopol/.test(ql)) rule = "contractor_concentration";

  let route = "flags";
  if (/\b(coa|audit)\b/.test(ql)) route = "audit";
  else if (/contractor|kontratista|\btop\b|sino/.test(ql) && !contractor && !rule) route = "contractors";
  const steps = [`Supervisor → ${route === "flags" ? "Analyst" : route === "contractors" ? "Analyst (contractors)" : "Auditor"}`];
  const where = prov ? ` sa ${title(prov)}` : "";
  const cites = [];
  const cite = (url, label) => { let i = cites.findIndex((c) => c.url === url); if (i < 0) { cites.push({ url, label }); i = cites.length - 1; } return i + 1; };

  if (route === "audit") {
    steps.push("Auditor: 0 findings", "Explainer");
    return { steps, cites: [], html: `<p>Wala pang COA audit findings na naka-load sa demo na ito, kaya wala akong masasabi tungkol diyan. No audit records are loaded yet, so no claims are made.</p><p class="disc">You can read COA annual audit reports at <a href="https://www.coa.gov.ph/" target="_blank" rel="noopener">coa.gov.ph</a>.</p>` };
  }

  if (route === "contractors") {
    const agg = new Map();
    for (const p of S.projects) {
      if (prov && p.prov !== prov) continue;
      const a = agg.get(p.contractor) || { n: 0, v: 0, f: 0, u: p.u };
      a.n++; a.v += p.amount || 0; a.f += p.score > 0; agg.set(p.contractor, a);
    }
    const top = [...agg.entries()].sort((a, b) => b[1].v - a[1].v).slice(0, 8);
    steps.push(`Analyst: ${top.length} contractors`, "Explainer");
    if (!top.length) return { steps, cites: [], html: "<p>Walang nakitang datos na tugma. No matching records, so no claims are made.</p>" };
    const n = cite(srcPage({ u: top[0][1].u, src: S.projects[0].src }), "DPWH flood control project list (BetterGov.ph export via Hugging Face)");
    return { steps, cites, html: `<p>Ito ang mga contractor na may pinakamalaking kabuuang halaga ng flood control contracts${where} [${n}]:</p>
      <ul>${top.map(([c, a]) => `<li><strong>${esc(c)}</strong>: ${a.n} projects, ${peso(a.v)}${a.f ? `, ${a.f} flagged for review` : ""}</li>`).join("")}</ul>
      <p>Hindi mali ang malaking kabuuan mismo. Tingnan ang "One contractor dominates a province" check para sa konsentrasyon.</p><p class="disc">${esc(DISCLAIMER)}</p>` };
  }

  let list = S.projects.filter((p) => p.score > 0 && (!prov || p.prov === prov) && (!contractor || p.contractor === contractor) && (!rule || p.flags.some((f) => f[0] === rule)));
  const total = list.length;
  list = list.slice(0, 8);
  steps.push(`Analyst: ${total} flagged projects`, "Explainer");
  if (!list.length) return { steps, cites: [], html: `<p>Walang nakitang flagged project na tugma sa tanong${where}. No matching records, so no claims are made.</p>` };
  const n = cite(srcPage(list[0]), "DPWH flood control project list (BetterGov.ph export via Hugging Face)");
  const portal = cite(PORTAL, "DPWH Transparency Portal (official, for verifying contract IDs)");
  const who = contractor ? ` ng ${esc(contractor)}` : "";
  const what = rule ? ` para sa check na "${esc(RULES[rule].label)}"` : "";
  return { steps, cites, html: `<p>May <strong>${num(total)}</strong> flagged na proyekto${who}${where}${what} [${n}]. Ito ang pinakamataas ang risk score:</p>
    <ul>${list.map((p) => `<li><a href="#" data-open="${p.id}">${esc(p.name)}</a> (${esc(p.code)}, ${esc(town(p.muni))}): ${peso(p.amount)}, risk ${p.score}. ${esc(p.flags.map((f) => f[2]).join(" "))}</li>`).join("")}</ul>
    <p>I-check ang contract ID sa DPWH portal bago gumawa ng konklusyon [${portal}].</p><p class="disc">${esc(DISCLAIMER)}</p>` };
}

load().catch(() => { $("#dataNote").textContent = "Project data could not load. Refresh the page to try again."; });
