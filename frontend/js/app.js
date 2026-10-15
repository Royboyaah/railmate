// RailMate frontend - vanilla ES modules, no build step, CSP-friendly (no inline handlers/styles).
import { api, ApiError, session } from "./api.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rupees = (n) => `₹${Number(n).toLocaleString("en-IN")}`;
const duration = (m) => `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
const pct = (p) => `${Math.round(p * 100)}%`;
const isoDate = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

const state = {
  classes: {},
  stations: { from: null, to: null },
  results: [],
  query: null,
  filter: "all",
  sort: "score",
  pendingSave: null,
};

/* ------------------------------------------------------------------ utils */
let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3000);
}

function applyMeters(root) {
  // CSP blocks inline style attributes, so widths are set through the CSSOM.
  $$("[data-w]", root).forEach((el) => { el.style.width = `${Math.max(0, Math.min(100, +el.dataset.w))}%`; });
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/* ------------------------------------------------------------------ routing */
const VIEWS = ["plan", "trips", "help", "insights"];

function showView(name) {
  if (!VIEWS.includes(name)) name = "plan";
  VIEWS.forEach((v) => { $(`#view-${v}`).hidden = v !== name; });
  $$(".nav-link").forEach((a) => {
    const on = a.dataset.view === name;
    a.classList.toggle("active", on);
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  if (name === "trips") loadTrips();
  if (name === "insights") loadInsights();
  if (name === "help") loadTopics();
}
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));

/* ------------------------------------------------------------------ dialog (focus-trapped) */
const dialog = { lastFocus: null };

function openDialog(html, onReady) {
  dialog.lastFocus = document.activeElement;
  $("#dialogBody").innerHTML = html;
  $("#dialog").hidden = false;
  applyMeters($("#dialogBody"));
  if (onReady) onReady($("#dialogBody"));
  const first = $("#dialogBody").querySelector("input, select, button, [tabindex]") || $("#dialogClose");
  first.focus();
}

function closeDialog() {
  $("#dialog").hidden = true;
  $("#dialogBody").innerHTML = "";
  if (dialog.lastFocus) dialog.lastFocus.focus();
}

$("#dialogClose").addEventListener("click", closeDialog);
$("#dialog").addEventListener("mousedown", (e) => { if (e.target.id === "dialog") closeDialog(); });
document.addEventListener("keydown", (e) => {
  if ($("#dialog").hidden) return;
  if (e.key === "Escape") { closeDialog(); return; }
  if (e.key !== "Tab") return;
  const focusables = $$("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])", $(".dialog"))
    .filter((el) => !el.disabled && el.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0], last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
  else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
});

/* ------------------------------------------------------------------ station autocomplete */
function setupCombo(key) {
  const input = $(`#${key}Input`);
  const list = $(`#${key}List`);
  let items = [];
  let active = -1;
  let controller;

  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  };

  const choose = (station) => {
    state.stations[key] = station;
    input.value = `${station.name} (${station.code})`;
    close();
  };

  const render = () => {
    list.innerHTML = items.map((s, i) => `
      <li id="${key}-opt-${i}" role="option" aria-selected="${i === active}" data-i="${i}">
        <span>${esc(s.name)}</span><span class="code">${esc(s.code)}</span>
      </li>`).join("") || `<li role="option" aria-disabled="true" class="muted">No stations found</li>`;
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `${key}-opt-${active}`);
  };

  const search = debounce(async (q) => {
    controller?.abort();
    controller = new AbortController();
    try {
      items = await api(`/stations?q=${encodeURIComponent(q)}&limit=8`, { signal: controller.signal });
      active = items.length ? 0 : -1;
      render();
    } catch (err) {
      if (err.name !== "AbortError") close();
    }
  }, 180);

  input.addEventListener("input", () => {
    state.stations[key] = null;
    search(input.value.trim());
  });
  input.addEventListener("focus", () => { if (!state.stations[key]) search(input.value.trim()); });
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { active = Math.min(active + 1, items.length - 1); render(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); render(); e.preventDefault(); }
    else if (e.key === "Enter" && active >= 0) { choose(items[active]); e.preventDefault(); }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-i]");
    if (li) { e.preventDefault(); choose(items[+li.dataset.i]); }
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
  return { choose, input };
}

const combos = { from: setupCombo("from"), to: setupCombo("to") };

$("#swapBtn").addEventListener("click", () => {
  const { from, to } = state.stations;
  const fv = combos.from.input.value;
  combos.from.input.value = combos.to.input.value;
  combos.to.input.value = fv;
  state.stations.from = to;
  state.stations.to = from;
});

/* ------------------------------------------------------------------ search */
function searchError(msg) {
  const el = $("#searchError");
  el.textContent = msg || "";
  el.hidden = !msg;
}

$("#searchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  runSearch();
});
$$("input[name=priority]").forEach((r) => r.addEventListener("change", () => { if (state.query) runSearch(); }));

async function runSearch() {
  const { from, to } = state.stations;
  if (!from || !to) return searchError("Choose both stations from the suggestions list.");
  if (from.code === to.code) return searchError("Origin and destination must be different.");
  searchError("");

  const params = new URLSearchParams({
    from: from.code, to: to.code, date: $("#dateInput").value, class: $("#classSelect").value,
    priority: $("input[name=priority]:checked").value, transfers: $("#transfersInput").checked,
  });
  const btn = $(".search-btn");
  btn.disabled = true;
  $("#results").innerHTML = `<div class="skeleton"></div><div class="skeleton"></div>`;
  $("#resultsBar").hidden = true;
  try {
    const data = await api(`/journeys?${params}`);
    state.results = data.results;
    state.query = data.query;
    history.replaceState(null, "", `?${params}#plan`);
    renderResults();
  } catch (err) {
    $("#results").innerHTML = "";
    searchError(err.message);
  } finally {
    btn.disabled = false;
  }
}

function visibleResults() {
  let list = state.results.filter((j) =>
    state.filter === "all" || (state.filter === "direct" ? j.transfers === 0 : j.transfers > 0));
  const key = {
    score: (j) => -j.scores.total,
    departure: (j) => j.legs[0].departure,
    duration: (j) => j.total_minutes,
    fare: (j) => j.fare,
  }[state.sort];
  return [...list].sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0));
}

function legHtml(leg) {
  return `
    <div class="leg">
      <div class="leg-head">
        <span class="train-name">${esc(leg.train_name)}</span>
        <span class="tag">#${esc(leg.train_number)}</span>
        <span class="tag">${esc(leg.train_type)}</span>
        ${leg.special ? `<span class="tag tag-warn" title="Seasonal or special service - may not run regularly">Special</span>` : ""}
      </div>
      <div class="timeline">
        <div><div class="time">${esc(leg.departure)}${leg.departure_day ? `<sup>+${leg.departure_day}</sup>` : ""}</div>
             <div class="stn">${esc(leg.from_name)} · ${esc(leg.from_code)}</div></div>
        <div class="track">${duration(leg.duration_min)} · ${Math.round(leg.distance_km)} km</div>
        <div><div class="time">${esc(leg.arrival)}${leg.arrival_day ? `<sup>+${leg.arrival_day}</sup>` : ""}</div>
             <div class="stn">${esc(leg.to_name)} · ${esc(leg.to_code)}</div></div>
      </div>
    </div>`;
}

function scoreRows(s) {
  return ["speed", "cost", "reliability", "convenience"].map((k) => `
    <div class="score-row"><span>${k[0].toUpperCase() + k.slice(1)}</span>
      <div class="meter" role="img" aria-label="${k} ${s[k]} out of 100"><span class="${k}" data-w="${s[k]}"></span></div>
      <span>${s[k]}</span></div>`).join("");
}

function renderResults() {
  const box = $("#results");
  const q = state.query;
  const list = visibleResults();
  $("#resultsBar").hidden = state.results.length === 0;
  const direct = state.results.filter((j) => j.transfers === 0).length;
  $("#resultsSummary").textContent =
    `${state.results.length} option${state.results.length === 1 ? "" : "s"} · ${direct} direct · ${q.class} · ${q.date}`;

  if (!state.results.length) {
    box.innerHTML = `<div class="card empty"><p><strong>No journeys found.</strong></p>
      <p>Try another class, enable connections, or pick a nearby major station.</p></div>`;
    return;
  }
  if (!list.length) {
    box.innerHTML = `<div class="card empty">No results match this filter.</div>`;
    return;
  }
  const bestId = state.results[0].id;
  box.innerHTML = list.map((j) => {
    const idx = state.results.indexOf(j);
    const legs = j.legs.map(legHtml);
    const layover = j.transfers ? `
      <div class="layover">🔁 Change at <strong>${esc(j.legs[0].to_name)}</strong> · ${duration(j.layover_min)} layover
        · <span class="risk ${j.connection_risk > 0.15 ? "High" : j.connection_risk > 0.06 ? "Medium" : "Low"}">
        ${pct(j.connection_risk)} missed-connection risk</span></div>` : "";
    return `
      <article class="card journey ${j.id === bestId ? "pick" : ""}" aria-label="Journey option">
        ${j.id === bestId ? `<span class="pick-badge">★ RailMate pick</span>` : ""}
        <div>
          ${legs[0]}${layover}${legs[1] || ""}
          <p class="muted small">Total ${duration(j.total_minutes)} · ${Math.round(j.distance_km)} km ·
            ${j.transfers ? "1 change" : "Direct"} · Running days: ${esc(j.legs[0].running_days)}</p>
        </div>
        <div class="side">
          <div class="fare">${rupees(j.fare)}</div>
          <span class="muted small">est. per passenger</span>
          <span class="risk ${j.delay_risk}" title="Chance of arriving more than 30 min late">
            ${j.delay_risk} delay risk · ${pct(j.scores.p_late)}</span>
          <div class="total">Score ${j.scores.total}</div>
          <div class="scores">${scoreRows(j.scores)}</div>
          <div class="actions">
            ${j.legs.map((l) => `<button type="button" class="btn btn-ghost btn-sm" data-route="${esc(l.train_number)}"
                data-from="${esc(l.from_code)}" data-to="${esc(l.to_code)}">Route ${j.transfers ? esc(l.train_number) : ""}</button>`).join("")}
            <button type="button" class="btn btn-primary btn-sm" data-save="${idx}">Save trip</button>
          </div>
        </div>
      </article>`;
  }).join("");
  applyMeters(box);
}

$("#results").addEventListener("click", (e) => {
  const route = e.target.closest("[data-route]");
  if (route) return openRoute(route.dataset.route, route.dataset.from, route.dataset.to);
  const save = e.target.closest("[data-save]");
  if (save) openSave(state.results[+save.dataset.save]);
});

$$(".chip[data-filter]").forEach((c) => c.addEventListener("click", () => {
  state.filter = c.dataset.filter;
  $$(".chip[data-filter]").forEach((x) => {
    x.classList.toggle("active", x === c);
    x.setAttribute("aria-pressed", String(x === c));
  });
  renderResults();
}));
$("#sortSelect").addEventListener("change", (e) => { state.sort = e.target.value; renderResults(); });

/* ------------------------------------------------------------------ route dialog */
async function openRoute(number, fromCode, toCode) {
  try {
    const t = await api(`/trains/${encodeURIComponent(number)}`);
    const iFrom = t.halts.findIndex((h) => h.code === fromCode);
    const iTo = t.halts.findIndex((h, i) => i > iFrom && h.code === toCode);
    openDialog(`
      <h3 id="dialogTitle">${esc(t.name)} <span class="muted">#${esc(t.number)}</span></h3>
      <p class="muted small">${esc(t.type)} · ${Math.round(t.distance_km)} km · ${duration(t.duration_min)} ·
        Classes: ${t.classes.map((c) => esc(c.code)).join(", ")} · Running days: ${esc(t.running_days)}</p>
      <div class="table-wrap"><table class="halts">
        <thead><tr><th>Station</th><th>Arr</th><th>Dep</th><th>Day</th><th>km</th></tr></thead>
        <tbody>${t.halts.map((h, i) => `
          <tr class="${i >= iFrom && i <= iTo ? "on" : ""}">
            <td>${esc(h.name)} <span class="muted">${esc(h.code)}</span></td>
            <td>${esc(h.arrival ?? "—")}</td><td>${esc(h.departure ?? "—")}</td>
            <td>${h.day}</td><td>${Math.round(h.km)}</td></tr>`).join("")}</tbody>
      </table></div>`);
  } catch (err) {
    toast(err.message);
  }
}

/* ------------------------------------------------------------------ auth */
function renderAccount() {
  const user = session.user;
  $("#signInBtn").hidden = !!user;
  $("#userMenu").hidden = !user;
  $("#userName").textContent = user ? user.name : "";
  if (user) refreshTripCount(); else $("#tripCount").hidden = true;
}
window.addEventListener("auth:changed", renderAccount);
window.addEventListener("auth:expired", () => toast("Your session expired - please sign in again."));
$("#signInBtn").addEventListener("click", () => openAuth("login"));
$("#signOutBtn").addEventListener("click", () => {
  session.clear();
  toast("Signed out");
  if (location.hash === "#trips") loadTrips();
});

function openAuth(mode, afterLogin) {
  const isLogin = mode === "login";
  openDialog(`
    <h3 id="dialogTitle">${isLogin ? "Sign in" : "Create your account"}</h3>
    <div class="tabs" role="tablist">
      <button type="button" class="tab" role="tab" aria-selected="${isLogin}" data-mode="login">Sign in</button>
      <button type="button" class="tab" role="tab" aria-selected="${!isLogin}" data-mode="register">Create account</button>
    </div>
    <form id="authForm" novalidate>
      <div class="form-grid">
        ${isLogin ? "" : `<div class="field full"><label for="aName">Name</label><input id="aName" autocomplete="name" maxlength="80" required /></div>`}
        <div class="field full"><label for="aEmail">Email</label><input id="aEmail" type="email" autocomplete="email" required /></div>
        <div class="field full"><label for="aPass">Password</label>
          <input id="aPass" type="password" autocomplete="${isLogin ? "current-password" : "new-password"}" minlength="8" required />
          ${isLogin ? "" : `<span class="muted small">At least 8 characters, mixing letters and numbers or symbols.</span>`}</div>
      </div>
      <p id="authError" class="form-error" role="alert" hidden></p>
      <button class="btn btn-primary" type="submit">${isLogin ? "Sign in" : "Create account"}</button>
    </form>`, (root) => {
    $$(".tab", root).forEach((t) => t.addEventListener("click", () => openAuth(t.dataset.mode, afterLogin)));
    $("#authForm", root).addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = $("#authError", root);
      const body = { email: $("#aEmail", root).value.trim(), password: $("#aPass", root).value };
      if (!isLogin) body.name = $("#aName", root).value.trim();
      const btn = e.submitter;
      btn.disabled = true;
      try {
        const res = await api(`/auth/${isLogin ? "login" : "register"}`, { method: "POST", body });
        session.save(res.access_token, res.user);
        closeDialog();
        toast(`Welcome, ${res.user.name}!`);
        if (afterLogin) afterLogin();
      } catch (ex) {
        err.textContent = ex.message;
        err.hidden = false;
        btn.disabled = false;
      }
    });
  });
}

/* ------------------------------------------------------------------ save trip */
function openSave(journey) {
  if (!session.user) {
    toast("Sign in to save trips");
    return openAuth("login", () => openSave(journey));
  }
  const q = state.query;
  openDialog(`
    <h3 id="dialogTitle">Save trip</h3>
    <p>${esc(journey.legs[0].from_name)} → ${esc(journey.legs.at(-1).to_name)} · ${esc(q.date)} · ${esc(state.classes[q.class] || q.class)}</p>
    <p class="muted small">${journey.legs.map((l) => `${esc(l.train_name)} (${esc(l.departure)})`).join(" → ")}</p>
    <form id="saveForm">
      <div class="form-grid">
        <div class="field"><label for="sPax">Passengers</label><input id="sPax" type="number" min="1" max="6" value="1" /></div>
        <div class="field"><label>Estimated total</label><div class="fare" id="sTotal">${rupees(journey.fare)}</div></div>
        <div class="field full"><label for="sNote">Note (optional)</label><input id="sNote" maxlength="200" placeholder="e.g. Diwali trip home" /></div>
      </div>
      <p id="saveError" class="form-error" role="alert" hidden></p>
      <button class="btn btn-primary" type="submit">Save trip</button>
    </form>`, (root) => {
    $("#sPax", root).addEventListener("input", (e) => {
      const n = Math.min(6, Math.max(1, +e.target.value || 1));
      $("#sTotal", root).textContent = rupees(journey.fare * n);
    });
    $("#saveForm", root).addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = e.submitter;
      btn.disabled = true;
      try {
        await api("/trips", {
          method: "POST",
          body: {
            legs: journey.legs.map((l) => ({ train_number: l.train_number, from_code: l.from_code, to_code: l.to_code })),
            travel_date: q.date,
            travel_class: q.class,
            passengers: +$("#sPax", root).value,
            note: $("#sNote", root).value,
          },
        });
        closeDialog();
        toast("Trip saved ✓");
        refreshTripCount();
      } catch (ex) {
        const err = $("#saveError", root);
        err.textContent = ex.message;
        err.hidden = false;
        btn.disabled = false;
      }
    });
  });
}

/* ------------------------------------------------------------------ trips view */
async function refreshTripCount() {
  if (!session.user) return;
  try {
    const trips = await api("/trips");
    $("#tripCount").textContent = trips.length;
    $("#tripCount").hidden = trips.length === 0;
  } catch { /* ignore */ }
}

async function loadTrips() {
  const box = $("#tripsList");
  if (!session.user) {
    box.innerHTML = `<div class="card empty"><p>Sign in to see your saved trips.</p>
      <button type="button" class="btn btn-primary" id="tripsSignIn">Sign in</button></div>`;
    $("#tripsSignIn").addEventListener("click", () => openAuth("login", loadTrips));
    return;
  }
  box.innerHTML = `<div class="skeleton"></div>`;
  try {
    const trips = await api("/trips");
    $("#tripCount").textContent = trips.length;
    $("#tripCount").hidden = trips.length === 0;
    if (!trips.length) {
      box.innerHTML = `<div class="card empty">No saved trips yet. Search for a journey and press “Save trip”.</div>`;
      return;
    }
    box.innerHTML = trips.map((t) => `
      <article class="card trip">
        <div class="trip-legs">
          <strong>${esc(t.legs[0].from_name)} → ${esc(t.legs.at(-1).to_name)}</strong>
          ${t.legs.map((l) => `<span class="small">${esc(l.train_name)} #${esc(l.train_number)} ·
            ${esc(l.from_code)} ${esc(l.departure)} → ${esc(l.to_code)} ${esc(l.arrival)}${l.arrival_day ? ` (+${l.arrival_day})` : ""}</span>`).join("")}
          <span class="muted small">${esc(t.travel_date)} · ${esc(state.classes[t.travel_class] || t.travel_class)} ·
            ${t.passengers} passenger${t.passengers > 1 ? "s" : ""}${t.note ? ` · ${esc(t.note)}` : ""}</span>
        </div>
        <div class="side">
          <div class="fare">${rupees(t.fare_total)}</div>
          <button type="button" class="btn btn-ghost btn-sm btn-danger" data-delete="${t.id}">Delete</button>
        </div>
      </article>`).join("");
  } catch (err) {
    box.innerHTML = `<div class="card empty">${esc(err.message)}</div>`;
  }
}

$("#tripsList").addEventListener("click", (e) => {
  const del = e.target.closest("[data-delete]");
  if (!del) return;
  openDialog(`
    <h3 id="dialogTitle">Delete this trip?</h3>
    <p class="muted">This can't be undone.</p>
    <div class="actions">
      <button type="button" class="btn btn-ghost" id="cancelDel">Cancel</button>
      <button type="button" class="btn btn-primary" id="confirmDel">Delete</button>
    </div>`, (root) => {
    $("#cancelDel", root).addEventListener("click", closeDialog);
    $("#confirmDel", root).addEventListener("click", async () => {
      try {
        await api(`/trips/${del.dataset.delete}`, { method: "DELETE" });
        closeDialog();
        toast("Trip deleted");
        loadTrips();
      } catch (err) { toast(err.message); }
    });
  });
});

/* ------------------------------------------------------------------ help desk */
let topicsLoaded = false;
async function loadTopics() {
  if (topicsLoaded) return;
  try {
    const topics = await api("/helpdesk/topics");
    $("#topics").innerHTML = topics.slice(0, 10).map((t) => `<button type="button" class="chip">${esc(t)}</button>`).join("");
    topicsLoaded = true;
  } catch { /* non-critical */ }
}

async function ask(question) {
  const log = $("#chatLog");
  log.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(question)}</div>`);
  try {
    const r = await api(`/helpdesk?q=${encodeURIComponent(question)}`);
    const related = (r.related || []).map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
    log.insertAdjacentHTML("beforeend", `<div class="msg bot">${esc(r.answer)}
      ${related ? `<div class="related"><span class="small muted">${r.matched ? "Related:" : "Did you mean:"}</span>${related}</div>` : ""}</div>`);
  } catch (err) {
    log.insertAdjacentHTML("beforeend", `<div class="msg bot">${esc(err.message)}</div>`);
  }
  log.scrollTop = log.scrollHeight;
}

$("#chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#chatInput").value.trim();
  if (q) ask(q);
  $("#chatInput").value = "";
});
$("#view-help").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip) ask(chip.textContent.trim());
});

/* ------------------------------------------------------------------ insights */
async function loadInsights() {
  const box = $("#insightsBody");
  try {
    const d = await api("/insights");
    const q = d.dataset.quality || {};
    const m = d.model || {};
    const maxType = Math.max(...d.train_types.map((t) => t.n), 1);
    const maxStn = Math.max(...d.busiest_stations.map((s) => s.train_count), 1);
    box.innerHTML = `
      <div class="kpis">
        <div class="card kpi"><div class="muted small">Trains</div><div class="v">${d.dataset.trains.toLocaleString("en-IN")}</div></div>
        <div class="card kpi"><div class="muted small">Stations served</div><div class="v">${d.dataset.stations.toLocaleString("en-IN")}</div></div>
        <div class="card kpi"><div class="muted small">Halts indexed</div><div class="v">${(q.halts || 0).toLocaleString("en-IN")}</div></div>
        <div class="card kpi"><div class="muted small">Saved trips</div><div class="v">${d.usage.saved_trips}</div></div>
      </div>
      <div class="grid-2">
        <div class="card"><h3>Train types</h3>
          ${d.train_types.map((t) => `<div class="bar-row"><span>${esc(t.type)}</span>
            <div class="meter"><span data-w="${(100 * t.n) / maxType}"></span></div><b>${t.n}</b></div>`).join("")}</div>
        <div class="card"><h3>Busiest stations (trains halting)</h3>
          ${d.busiest_stations.map((s) => `<div class="bar-row"><span>${esc(s.name)}</span>
            <div class="meter"><span data-w="${(100 * s.train_count) / maxStn}"></span></div><b>${s.train_count}</b></div>`).join("")}</div>
      </div>
      <div class="grid-2">
        <div class="card"><h3>Data quality report</h3>
          <p class="muted small">${esc(d.dataset.source)} · ${esc(d.dataset.license)}<br>${esc(d.dataset.note)}</p>
          <div class="table-wrap"><table><tbody>
            <tr><td>Raw schedule rows</td><td>${(q.schedule_rows || 0).toLocaleString("en-IN")}</td></tr>
            <tr><td>Rows without any time (dropped)</td><td>${(q.rows_without_time_dropped || 0).toLocaleString("en-IN")}</td></tr>
            <tr><td>Pass-through rows filtered → real halts</td><td>${(q.halts || 0).toLocaleString("en-IN")}</td></tr>
            <tr><td>Backward time glitches clamped</td><td>${(q.time_glitches_clamped || 0).toLocaleString("en-IN")}</td></tr>
            <tr><td>Trains with distance interpolated by time</td><td>${q.distance_by_time || 0}</td></tr>
            <tr><td>Trains skipped (unusable data)</td><td>${q.trains_skipped || 0}</td></tr>
          </tbody></table></div></div>
        <div class="card"><h3>Delay-risk model</h3>
          ${m.synthetic ? `<div class="warn small"><strong>Trained on synthetic labels.</strong> These metrics show the pipeline works; they are not real-world accuracy.</div>` : ""}
          ${m.status === "model" ? `
            <p class="small">${esc(m.model)} · target: ${esc(m.target)} · selected by ${esc(m.selection)}</p>
            <div class="table-wrap"><table><tbody>
              <tr><td>ROC-AUC (test)</td><td>${m.metrics.roc_auc}</td></tr>
              <tr><td>Brier score (lower is better)</td><td>${m.metrics.brier}</td></tr>
              <tr><td>Brier of constant baseline</td><td>${m.metrics.constant_baseline_brier}</td></tr>
              <tr><td>Train / test rows</td><td>${m.n_train.toLocaleString("en-IN")} / ${m.n_test.toLocaleString("en-IN")}</td></tr>
            </tbody></table></div>
            <h3>Calibration (predicted vs observed)</h3>
            <div class="table-wrap"><table><thead><tr><th>Bin</th><th>n</th><th>Predicted</th><th>Observed</th></tr></thead>
              <tbody>${m.calibration.map((c) => `<tr><td>${esc(c.bin)}</td><td>${c.n}</td><td>${pct(c.predicted)}</td><td>${pct(c.observed)}</td></tr>`).join("")}</tbody></table></div>`
            : `<p class="muted">No trained model found - using a heuristic fallback. Run <code>python -m ml.train_delay_model</code>.</p>`}
        </div>
      </div>`;
    applyMeters(box);
  } catch (err) {
    box.innerHTML = `<div class="card empty">${esc(err.message)}</div>`;
  }
}

/* ------------------------------------------------------------------ init */
async function init() {
  const today = new Date();
  const max = new Date(today);
  max.setDate(max.getDate() + 120);
  const dateInput = $("#dateInput");
  dateInput.min = isoDate(today);
  dateInput.max = isoDate(max);
  dateInput.value = isoDate(today);

  renderAccount();
  showView(location.hash.slice(1) || "plan");

  try {
    state.classes = await api("/classes");
    $("#classSelect").innerHTML = Object.entries(state.classes)
      .map(([k, v]) => `<option value="${esc(k)}" ${k === "3A" ? "selected" : ""}>${esc(v)}</option>`).join("");
  } catch (err) {
    searchError(err.message);
    return;
  }

  // Restore a shared search URL, e.g. /?from=NDLS&to=AGC&date=...&class=CC
  const params = new URLSearchParams(location.search);
  const [from, to] = await Promise.all(["from", "to"].map(async (k) => {
    const code = params.get(k);
    if (!code) return null;
    try { return await api(`/stations/${encodeURIComponent(code)}`); } catch { return null; }
  }));
  if (from) combos.from.choose(from);
  if (to) combos.to.choose(to);
  const date = params.get("date");
  if (date && date >= dateInput.min && date <= dateInput.max) dateInput.value = date;
  if (params.get("class") && state.classes[params.get("class")]) $("#classSelect").value = params.get("class");
  const pr = params.get("priority");
  if (pr && $(`#p-${pr}`)) $(`#p-${pr}`).checked = true;
  if (params.get("transfers") === "false") $("#transfersInput").checked = false;
  if (from && to) runSearch();
}

init().catch((err) => {
  if (err instanceof ApiError) searchError(err.message);
  else console.error(err);
});
