"use strict";
// הממשק של Handy 2. כל הטקסט שמגיע מהשרת מוצג דרך textContent (אף פעם innerHTML), והשרת מאמת מחדש כל ערך שנשלח אליו.
const TOKEN = document.querySelector('meta[name="handy-token"]').content;
const HANDS = { right: "ימין", left: "שמאל", both: "שתיהן" };
const HINTS = { waiting: "ממתין ליד מול המצלמה…", moving: "החזק את היד במקום…", recording: "מקליט…", done: "ההקלטה הסתיימה" };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

let config = null;
let lastState = null;
let shownResult = null;
let toggling = 0;         // זמן הלחיצה האחרונה על מתג השליטה: לא דורסים אותו מהסטטוס כשהוא עוד בדרך לשרת

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// הדף נפתח ישירות מהקובץ (למשל Live Server) ולא מהתוכנה: הטוקן לא הוחלף, ואז כל הנתונים הם דמה, כדי שאפשר לעצב בלי מצלמה
const PREVIEW = TOKEN === "__TOKEN__";
const mock = {
  config: {
    version: 1, app_version: "2.1.0 (תצוגה מקדימה)", control_enabled: false,
    settings: { show_hand_mesh: true, show_face_mesh: true, show_trail: true, show_coords: true, run_in_background: false,
      auto_update_check: true, beta_channel: false, control_source: "hand", control_hand: "both", sensitivity: 1.0, smoothing: 0.5 },
    limits: { sensitivity: [0.4, 3.0], smoothing: [0.0, 1.0] },
    actions: [["none", "ללא"], ["left_click", "קליק שמאלי"], ["right_click", "קליק ימני"], ["double_click", "קליק כפול"], ["middle_click", "קליק אמצעי"],
      ["scroll_up", "גלילה למעלה"], ["scroll_down", "גלילה למטה"],
      ["toggle_control", "הפעלה / כיבוי של השליטה בעכבר"], ["hotkey", "קיצור מקשים…", true], ["script", "הרצת תוכנה / סקריפט…", true]]
      .map(([id, label, param]) => ({ id, label, param: !!param })),
    groups: {
      hand: [["pinch", "צביטה", "none"], ["ok", "אוקיי", "double_click"], ["victory", "ניצחון (V)", "left_click"], ["hang_loose", "היי (Hang Loose)", "right_click"],
        ["thumbs_up", "לייק", "none"], ["thumbs_down", "דיסלייק", "none"], ["fist", "אגרוף", { type: "hotkey", keys: "Ctrl+C" }],
        ["open", "כף פתוחה", "none"], ["point", "הצבעה", "none"], ["three", "שלוש אצבעות", "scroll_up"], ["rock", "רוק", "scroll_down"]]
        .map(([id, name, binding]) => ({ id, name, binding })),
      custom: [{ id: "custom:demo", name: "אצבע קטנה וקמיצה", binding: "none" }],
    },
  },
  state: { config_version: 1, fps: 30, detect: "ניצחון (V)", enabled: false, camera: true, active_hand: "right", recording: null, rec_result: null,
    update: { status: "idle", progress: 0, message: "", notice: null, info: null } },
};

function mockText(b) {
  if (b && typeof b === "object") return b.type === "hotkey" ? `קיצור: ${b.keys}` : `הרצה: ${b.path}`;
  return mock.config.actions.find((a) => a.id === b)?.label || "ללא";
}

async function api(path, body) {
  if (PREVIEW) {
    for (const g of Object.values(mock.config.groups).flat()) g.text = mockText(g.binding);
    if (body !== undefined && path === "/api/set") { mock.config.settings[body.key] = body.value; mock.config.version++; mock.state.config_version++; }
    if (body !== undefined && path === "/api/control") mock.state.enabled = body.enabled;
    if (body !== undefined && path === "/api/binding") {
      const g = Object.values(mock.config.groups).flat().find((x) => x.id === body.gesture);
      if (g) g.binding = body.action === "hotkey" ? { type: "hotkey", keys: body.keys } : body.action === "script" ? { type: "script", path: body.path, args: body.args || "" } : body.action;
    }
    return path === "/api/config" ? mock.config : path === "/api/state" ? mock.state : { ok: true };
  }
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Handy-Token": TOKEN, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "שגיאה");
  return data;
}

const kindOf = (b) => (b && typeof b === "object" ? b.type : b || "none");

// --- שורת מיפוי של מחווה ----------------------------------------------------
function makeRow(g, extraButtons) {
  const row = el("div", "row");
  row.dataset.name = g.name;
  row.append(el("div", "name", g.name));
  const controls = el("div", "controls");
  const select = el("select");
  select.setAttribute("aria-label", "פעולה עבור " + g.name);
  for (const a of config.actions) {
    const o = el("option", "", a.param ? a.label : a.label);
    o.value = a.id;
    select.append(o);
  }
  select.value = kindOf(g.binding);
  controls.append(select);
  for (const b of extraButtons || []) controls.append(b);
  row.append(controls);

  const extra = el("div", "extra");
  const err = el("div", "err");
  row.append(extra, err);

  const save = async (payload) => {
    err.textContent = "";
    try {
      await api("/api/binding", { gesture: g.id, ...payload });
    } catch (e) {
      err.textContent = e.message;
    }
  };

  const buildExtra = (kind) => {
    extra.replaceChildren();
    err.textContent = "";
    const cur = g.binding && typeof g.binding === "object" && g.binding.type === kind ? g.binding : {};
    if (kind === "hotkey") {
      const keys = el("input"); keys.type = "text"; keys.placeholder = "למשל Ctrl+C, Alt+Tab, Win+D"; keys.value = cur.keys || "";
      keys.setAttribute("aria-label", "קיצור מקשים");
      const ok = el("button", "primary", "שמור");
      ok.onclick = () => save({ action: "hotkey", keys: keys.value });
      keys.onkeydown = (ev) => { if (ev.key === "Enter") ok.click(); };
      extra.append(keys, ok, el("span", "muted small", "המקשים לחוצים כל עוד המחווה פעילה"));
    } else if (kind === "script") {
      const path = el("input"); path.type = "text"; path.placeholder = "נתיב מלא לתוכנה או לסקריפט"; path.value = cur.path || "";
      path.setAttribute("aria-label", "נתיב");
      const browse = el("button", "", "עיון…");
      browse.onclick = async () => {
        try { const r = await api("/api/pick-file", {}); if (r.path) path.value = r.path; } catch (e) { err.textContent = e.message; }
      };
      const args = el("input"); args.type = "text"; args.placeholder = "ארגומנטים (אופציונלי)"; args.value = cur.args || "";
      args.setAttribute("aria-label", "ארגומנטים");
      const ok = el("button", "primary", "שמור");
      ok.onclick = () => save({ action: "script", path: path.value, args: args.value });
      extra.append(path, browse, args, ok);
    }
  };

  const param = (id) => config.actions.find((a) => a.id === id)?.param;
  if (param(select.value)) buildExtra(select.value);
  select.onchange = () => {
    if (param(select.value)) buildExtra(select.value);
    else { extra.replaceChildren(); save({ action: select.value }); }
  };
  return row;
}

function renderRows() {
  const g = config.groups;
  $("#rows-hand").replaceChildren(...g.hand.map((x) => makeRow(x)));
  $("#rows-custom").replaceChildren(...g.custom.map(customRow));
  if (!g.custom.length) $("#rows-custom").append(el("p", "muted small", "עדיין אין מחוות מותאמות"));
}

function customRow(g) {
  const btn = (text, cls, fn) => { const b = el("button", cls, text); b.onclick = fn; return b; };
  const call = (body) => api("/api/custom", body).catch((e) => setRecMsg(e.message, false));
  return makeRow(g, [
    btn("אימון עוד", "", () => call({ op: "record", id: g.id, mode: "train" })),
    btn("הקלט מחדש", "", () => call({ op: "record", id: g.id, mode: "replace" })),
    btn("שם", "", () => { const n = prompt("שם חדש:", g.name); if (n !== null) call({ op: "rename", id: g.id, name: n }); }),
    btn("מחק", "danger", () => { if (confirm(`למחוק את '${g.name}'?`)) call({ op: "delete", id: g.id }); }),
  ]);
}

// --- הגדרות ----------------------------------------------------------------
function setupSettings() {
  for (const box of $$('input[type=checkbox][data-key]')) {
    box.onchange = () => api("/api/set", { key: box.dataset.key, value: box.checked }).catch(() => {});
  }
  for (const seg of $$(".seg")) {
    for (const [value, label] of JSON.parse(seg.dataset.options)) {
      const b = el("button", "", label);
      b.dataset.value = value;
      b.onclick = () => api("/api/set", { key: seg.dataset.key, value }).catch(() => {});
      seg.append(b);
    }
  }
  for (const r of $$('input[type=range][data-key]')) {
    r.oninput = () => { $("#v-" + r.dataset.key).textContent = Number(r.value).toFixed(2); };
    r.onchange = () => api("/api/set", { key: r.dataset.key, value: Number(r.value) }).catch(() => {});
  }
}

function applySettings() {
  const s = config.settings;
  $("#version").textContent = config.app_version;
  $("#version-chip").textContent = "v" + config.app_version.split(" ")[0];
  for (const box of $$('input[type=checkbox][data-key]')) box.checked = !!s[box.dataset.key];
  for (const seg of $$(".seg")) for (const b of $$("button", seg)) b.classList.toggle("on", b.dataset.value === s[seg.dataset.key]);
  for (const r of $$('input[type=range][data-key]')) {
    const [lo, hi] = config.limits[r.dataset.key];
    r.min = lo; r.max = hi;
    if (document.activeElement !== r) r.value = s[r.dataset.key];
    $("#v-" + r.dataset.key).textContent = Number(r.value).toFixed(2);
  }
}

async function loadConfig() {
  const focused = document.activeElement;
  if (focused && focused.closest && focused.closest(".rows") && focused.tagName === "INPUT") { config.stale = true; return; }
  const fresh = await api("/api/config");
  config = fresh;
  renderRows();
  applySettings();
}

// --- הקלטה ------------------------------------------------------------------
function setRecMsg(text, ok) {
  const m = $("#rec-msg");
  m.textContent = text || "";
  m.className = "msg " + (text ? (ok ? "ok" : "bad") : "");
}

function renderRecording(st) {
  const r = st.recording;
  $("#rec-start").disabled = !!r;
  $("#rec-cancel").hidden = !r;
  $("#rec-bar").hidden = !r;
  if (r) {
    $("#rec-bar").value = r.progress;
    setRecMsg(`${r.name}: ${HINTS[r.hint] || ""}`, true);
  } else if (!st.rec_result) {
    shownResult = null;
  } else if (st.rec_result.text !== shownResult) {
    shownResult = st.rec_result.text;   // מציגים כל תוצאה פעם אחת, כדי שהודעת שגיאה מקומית לא תידרס בכל סבב
    setRecMsg(shownResult, st.rec_result.ok);
  }
}

// --- עדכונים ----------------------------------------------------------------
function renderUpdate(u) {
  const banner = $("#banner"), text = $("#banner-text"), actions = $(".banner-actions", banner);
  actions.replaceChildren();
  const btn = (label, cls, op) => { const b = el("button", cls, label); b.onclick = () => api("/api/update", { op }); actions.append(b); };
  const link = () => {
    if (u.info && /^https:\/\//.test(u.info.page)) {
      const a = el("a", "", "פתח את דף ההורדה"); a.href = u.info.page; a.target = "_blank"; a.rel = "noopener noreferrer"; actions.append(a);
    }
  };
  let show = true;
  banner.classList.remove("warn");
  if (u.notice) { text.textContent = u.notice.text; btn("אישור", "", "ack"); banner.classList.toggle("warn", u.notice.kind === "failed"); }
  else if (u.status === "available") {
    text.textContent = `גרסה חדשה זמינה: ${u.info.latest}${u.info.prerelease ? " (בטא)" : ""}`;
    btn("עדכן עכשיו", "primary", "install"); btn("אחר כך", "", "dismiss"); btn("דלג על גרסה זו", "", "skip");
  } else if (u.status === "downloading" || u.status === "installing") {
    text.textContent = `${u.message} ${u.status === "downloading" ? Math.round(u.progress * 100) + "%" : ""}`;
  } else if (u.status === "page" || u.status === "blocked") {
    text.textContent = u.message; link(); btn("סגור", "", "dismiss"); banner.classList.add("warn");
  } else show = false;
  banner.hidden = !show;

  const box = $("#update-box");
  const info = u.info && (u.status === "available" || u.status === "downloading" || u.status === "installing");
  box.hidden = !info;
  if (info) {
    $("#update-title").textContent = `גרסה ${u.info.latest}`;
    $("#update-notes").textContent = u.info.notes || "אין הערות לגרסה זו.";
    $("#update-bar").hidden = u.status !== "downloading";
    $("#update-bar").value = u.progress;
  }
  const msg = $("#update-msg");
  if (u.status === "uptodate") { msg.textContent = "הגרסה שלך עדכנית."; msg.className = "msg ok"; }
  else if (u.status === "error") { msg.textContent = "הבדיקה נכשלה: " + u.message; msg.className = "msg bad"; }
  else if (u.status === "checking") { msg.textContent = "בודק…"; msg.className = "msg"; }
  else { msg.textContent = ""; msg.className = "msg"; }
}

// --- סטטוס שוטף -------------------------------------------------------------
function renderState(st) {
  const first = !lastState;
  $("#status").textContent = `${st.fps.toFixed(0)} FPS`;
  $("#detect").textContent = st.detect;
  $("#no-camera").hidden = st.camera;
  if (Date.now() - toggling > 1500) $("#control").checked = st.enabled;
  if (config) {
    const s = config.settings;
    $("#hand-chip").hidden = false;
    $("#hand-line").textContent = s.control_source !== "hand" ? "הסמן זז לפי הראש"
      : st.active_hand ? `יד ${HANDS[st.active_hand]} · שולטת` : `יד שולטת: ${HANDS[s.control_hand]}`;
  }
  const live = new Set(st.detect.split(" + "));
  for (const row of $$(".row")) row.classList.toggle("live", live.has(row.dataset.name));
  // הפעולה של המחווה המזוהה (הראשונה), בכרטיס מתחת לווידאו
  const rows = config ? Object.values(config.groups).flat() : [];
  const hit = rows.find((r) => live.has(r.name));
  $("#detect-action").textContent = hit ? hit.text : "—";
  renderRecording(st);
  renderUpdate(st.update);
  if (first || !config || st.config_version !== config.version || config.stale) loadConfig().catch(() => {});
  lastState = st;
}

let failures = 0;
async function poll() {
  try {
    renderState(await api("/api/state"));
    failures = 0;
  } catch (e) {
    if (++failures === 4) { $("#banner-text").textContent = "החיבור לתוכנה נותק. אפשר לסגור את החלון."; $("#banner").hidden = false; }
  }
  setTimeout(poll, 250);
}

function setupVideo() {
  const img = $("#video");
  if (PREVIEW) {  // בלי מצלמה: מסגרת שחורה עם הכיתוב, כדי לראות את הפריסה
    img.src = "data:image/svg+xml;utf8," + encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect width="800" height="600" fill="#0b0c0f"/>' +
      '<text x="400" y="300" fill="#6b7280" font-size="28" text-anchor="middle" font-family="sans-serif">תצוגה מקדימה: כאן יופיע הווידאו</text></svg>');
    return;
  }
  const connect = () => { img.src = `/video?t=${encodeURIComponent(TOKEN)}&_=${Date.now()}`; };
  img.onerror = () => setTimeout(connect, 1000);
  connect();
}

function setupTabs() {
  for (const t of $$(".tabs button")) {
    t.onclick = () => {
      for (const x of $$(".tabs button")) x.classList.toggle("active", x === t);
      for (const p of $$(".tab")) p.classList.toggle("active", p.id === "tab-" + t.dataset.tab);
    };
  }
}

function setupActions() {
  $("#control").onchange = (e) => { toggling = Date.now(); api("/api/control", { enabled: e.target.checked }).catch(() => {}); };
  $("#rec-start").onclick = () => {
    setRecMsg("", true);
    api("/api/custom", { op: "record", name: $("#rec-name").value, mode: "new" }).then(() => { $("#rec-name").value = ""; })
      .catch((e) => setRecMsg(e.message, false));
  };
  $("#rec-cancel").onclick = () => api("/api/custom", { op: "cancel" });
  $("#check-update").onclick = () => api("/api/update", { op: "check" });
  $("#quit").onclick = () => { if (confirm("לצאת מהתוכנה? השליטה בעכבר תיפסק.")) api("/api/quit", {}).catch(() => {}); };
  // סגירת החלון: אם ההרצה ברקע דולקת התוכנה ממשיכה, אחרת היא יוצאת (השרת מחליט)
  if (!PREVIEW) window.addEventListener("pagehide", () => navigator.sendBeacon(`/api/bye?t=${encodeURIComponent(TOKEN)}`, new Blob(["{}"], { type: "application/json" })));
}

setupTabs();
setupSettings();
setupActions();
setupVideo();
api("/api/config").then((c) => { config = c; renderRows(); applySettings(); }).catch(() => {}).finally(poll);
