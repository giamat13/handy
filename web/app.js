"use strict";
// הממשק של Handy 2. כל הטקסט שמגיע מהשרת מוצג דרך textContent (אף פעם innerHTML), והשרת מאמת מחדש כל ערך שנשלח אליו.
const TOKEN = document.querySelector('meta[name="handy-token"]').content;
const HANDS = { right: "ימין", left: "שמאל", both: "שתיהן" };
const HINTS = {
  hand: { waiting: "ממתין ליד מול המצלמה…", moving: "החזק את היד במקום…", recording: "מקליט…", done: "ההקלטה הסתיימה" },
  head: { waiting: "ממתין לפנים מול המצלמה…", moving: "החזק את הראש במקום…", recording: "מקליט…", done: "ההקלטה הסתיימה" },
};
const KINDS = { hand: "יד", head: "ראש" };
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
    settings: { show_hand_mesh: true, show_face_mesh: true, show_trail: true, show_coords: true, show_head_axes: true, show_pinch_gauge: true,
      show_ripples: true, autostart: false, run_in_background: false, auto_update_check: true, beta_channel: false, control_source: "hand", control_hand: "both", sensitivity: 1.0, smoothing: 0.5 },
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
      head: [["nod", "הנהון (כן)", "none"], ["shake", "ניעור ראש (לא)", "none"], ["tilt_left", "הטיית ראש שמאלה", "none"], ["tilt_right", "הטיית ראש ימינה", "none"],
        ["lean_forward", "ראש קדימה (התקרבות)", "none"], ["lean_back", "ראש אחורה (התרחקות)", "none"],
        ["eye_wink_left", "קריצה בעין שמאל", "none"], ["eye_wink_right", "קריצה בעין ימין", "none"], ["eye_blink_long", "מצמוץ ארוך", "none"],
        ["face_mouth_open", "פה פתוח", "none"], ["face_smile", "חיוך", "none"], ["face_brows_up", "גבות מורמות", "none"]].map(([id, name, binding]) => ({ id, name, binding, kind: "head" })),
      custom: [{ id: "custom:demo", name: "אצבע קטנה וקמיצה", kind: "hand", binding: "none" },
        { id: "custom:demo2", name: "ראש מוטה ימינה", kind: "head", binding: "none" }],
    },
  },
  state: { config_version: 1, fps: 30, detect: "ניצחון (V)", detect_hand: "ניצחון (V)", detect_head: "ראש מוטה ימינה", enabled: false, camera: true, active_hand: "right", recording: null, rec_result: null,
    conf: { victory: 0.93, point: 0.41, three: 0.38, "custom:demo": 0.12, "custom:demo2": 0.7 },
    perf: { camera_fps: 15.2, tracker_fps: 14.8, hands_ms: 9.1, face_ms: 11.4, logic_ms: 0.6, latency_ms: 38, draw_fps: 14.7, draw_ms: 7.2, encode_ms: 3.1, cursor_hz: 96 },
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
  $("#rows-head").replaceChildren(...g.head.map((x) => makeRow(x)));
  for (const kind of Object.keys(KINDS)) {   // יד וראש: שתי רשימות נפרדות בשתי לשוניות
    const mine = g.custom.filter((x) => (x.kind || "hand") === kind);
    $(`#rows-custom-${kind}`).replaceChildren(...mine.map((x) => customRow(x, kind)));
    if (!mine.length) $(`#rows-custom-${kind}`).append(el("p", "muted small", `עדיין אין מחוות ${KINDS[kind]} מותאמות`));
  }
}

function customRow(g, kind) {
  const btn = (text, cls, fn) => { const b = el("button", cls, text); b.onclick = fn; return b; };
  const call = (body) => api("/api/custom", body).catch((e) => setRecMsg(e.message, false, kind));
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
    box.onchange = () => {
      $("#settings-msg").textContent = "";
      api("/api/set", { key: box.dataset.key, value: box.checked }).catch((e) => {
        box.checked = !box.checked;   // השרת סירב (למשל ההפעלה עם המחשב לא נשמרה): המתג חוזר למצבו האמיתי ויש הסבר
        $("#settings-msg").textContent = e.message;
      });
    };
  }
  for (const seg of $$(".seg[data-key]")) {
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
  for (const seg of $$(".seg[data-key]")) for (const b of $$("button", seg)) b.classList.toggle("on", b.dataset.value === s[seg.dataset.key]);
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
// לכל סוג (hand / head) כרטיס הקלטה משלו, בלשונית שלו: #rec-name-hand, #rec-msg-head וכן הלאה
function setRecMsg(text, ok, kind) {
  for (const k of kind ? [kind] : Object.keys(KINDS)) {
    const m = $(`#rec-msg-${k}`);
    m.textContent = text || "";
    m.className = "msg " + (text ? (ok ? "ok" : "bad") : "");
  }
}

function renderRecording(st) {
  const r = st.recording;
  for (const k of Object.keys(KINDS)) {
    const mine = !!r && r.kind === k;
    $(`#rec-start-${k}`).disabled = !!r;      // מקליטים דבר אחד בכל רגע, בין אם יד או ראש
    $(`#rec-cancel-${k}`).hidden = !mine;
    $(`#rec-bar-${k}`).hidden = !mine;
    if (mine) $(`#rec-bar-${k}`).value = r.progress;
  }
  if (r) {
    setRecMsg(`${r.name}: ${(HINTS[r.kind] || HINTS.hand)[r.hint] || ""}`, true, r.kind);
  } else if (!st.rec_result) {
    shownResult = null;
  } else if (st.rec_result.text !== shownResult) {
    shownResult = st.rec_result.text;   // מציגים כל תוצאה פעם אחת, כדי שהודעת שגיאה מקומית לא תידרס בכל סבב
    setRecMsg(shownResult, st.rec_result.ok, st.rec_result.kind);
  }
}

// --- אבחון: ביטחון בזיהוי וקצב השלבים ----------------------------------------
const NEAR = 0.3;   // מ-30% נחשב "קרוב" למחווה (הגבול עצמו הוא 50%)
let confKey = null;
let confRows = [];

function buildConf() {
  const groups = [["מחוות יד", config.groups.hand], ["מחוות יד שלי", config.groups.custom.filter((g) => g.kind !== "head")],
    ["מחוות ראש מובנות", config.groups.head], ["מחוות ראש שלי", config.groups.custom.filter((g) => g.kind === "head")]];
  const box = $("#conf-bars");
  box.replaceChildren();
  confRows = [];
  for (const [title, items] of groups) {
    if (!items.length) continue;
    box.append(el("div", "bar-row group", title));
    for (const g of items) {
      const fill = el("div", "fill"), pct = el("span", "pct", "0%"), label = el("span", "label", g.name);
      label.title = g.name;
      const track = el("div", "track");
      track.append(fill);
      const row = el("div", "bar-row");
      row.append(label, track, pct);
      box.append(row);
      confRows.push({ id: g.id, name: g.name, row, fill, pct });
    }
  }
  confKey = config.version;
}

function renderConf(st) {
  if (!config) return;
  if (confKey !== config.version) buildConf();
  const conf = st.conf || {};
  for (const r of confRows) {
    const v = conf[r.id] || 0;
    r.fill.style.width = `${Math.round(v * 100)}%`;
    r.pct.textContent = `${Math.round(v * 100)}%`;
    r.row.classList.toggle("hit", v >= 0.5);
    r.row.classList.toggle("close", v >= NEAR && v < 0.5);
  }
  const ranked = confRows.map((r) => ({ name: r.name, v: conf[r.id] || 0 })).sort((a, b) => b.v - a.v);
  const [a, b] = ranked;
  const pc = (x) => `${Math.round(x.v * 100)}%`;
  const note = $("#conf-note");
  let text = "לא רואים יד או ראש מול המצלמה", bad = false;
  if (a && a.v > 0) {
    if (a.v >= 0.5 && b && b.v >= NEAR) { text = `"${a.name}" מזוהה (${pc(a)}), אבל גם "${b.name}" קרובה (${pc(b)}): הן עלולות להתבלבל`; bad = true; }
    else if (a.v >= 0.5) text = `מזוהה: "${a.name}" (${pc(a)})`;
    else if (b && b.v >= NEAR && a.v >= NEAR) { text = `"${a.name}" (${pc(a)}) ו"${b.name}" (${pc(b)}) קרובות לגבול ושתיהן עוד לא מזוהות`; bad = true; }
    else if (a.v >= NEAR) text = `הכי קרובה: "${a.name}" (${pc(a)}), חסר עוד קצת`;
    else text = "אין מחווה קרובה";
  }
  note.textContent = text;
  note.className = "msg " + (bad ? "bad" : "ok");
}

const PERF_ROWS = [
  ["camera_fps", "מצלמה: פריימים שהיא מספקת", "/ש׳"], ["tracker_fps", "מעקב: פריימים שמעובדים", "/ש׳"],
  ["hands_ms", "זיהוי ידיים (MediaPipe)", "ms"], ["face_ms", "זיהוי פנים (MediaPipe)", "ms"],
  ["logic_ms", "מחוות ושליטה בעכבר", "ms"], ["latency_ms", "השהיה: מהפריים עד הסמן", "ms"],
  ["cursor_hz", "עדכוני סמן בשנייה (בזמן תנועה)", "/ש׳"], ["draw_fps", "ציור הווידאו בחלון", "/ש׳"],
  ["draw_ms", "ציור הפריים", "ms"], ["encode_ms", "קידוד JPEG", "ms"],
];

function perfNote(p) {
  if (p.camera_fps == null || p.tracker_fps == null) return ["", true];
  if (p.camera_fps === 0) return ["המצלמה לא מספקת פריימים", false];
  if (p.camera_fps < 24) return [`המצלמה נותנת רק ${p.camera_fps.toFixed(0)} פריימים בשנייה (תאורה חלשה גורמת לזה לרוב), ולכן גם המעקב והסמן לא יעברו את הקצב הזה`, false];
  if (p.tracker_fps < p.camera_fps * 0.85) {
    const work = (p.hands_ms || 0) + (p.face_ms || 0);
    return [`המעקב מעבד ${p.tracker_fps.toFixed(0)} מתוך ${p.camera_fps.toFixed(0)} פריימים שהמצלמה נותנת: זיהוי ידיים ופנים לוקח ${work.toFixed(0)} ms לפריים`, false];
  }
  return ["הקצב תקין: המעקב עומד בקצב של המצלמה", true];
}

function renderPerf(p) {
  p = p || {};
  const body = $("#perf-table tbody");
  if (!body.children.length) for (const [key, label] of PERF_ROWS) {
    const tr = el("tr"); tr.dataset.key = key;
    tr.append(el("td", "", label), el("td", "", "—"));
    body.append(tr);
  }
  const slowest = (p.camera_fps != null && p.camera_fps < 24) ? "camera_fps" : null;
  for (const tr of body.children) {
    const unit = PERF_ROWS.find((r) => r[0] === tr.dataset.key)[2];
    const v = p[tr.dataset.key];
    tr.lastChild.textContent = v == null ? "—" : `${v.toFixed(1)} ${unit}`;
    tr.classList.toggle("slow", tr.dataset.key === slowest);
  }
  const [text, ok] = perfNote(p);
  const note = $("#perf-note");
  note.textContent = text;
  note.className = "msg " + (ok ? "ok" : "bad");
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
  const detectHand = st.detect_hand ?? st.detect, detectHead = st.detect_head ?? "—";   // יד וראש מוצגים בנפרד
  $("#detect-hand").textContent = detectHand;
  $("#detect-head").textContent = detectHead;
  $("#no-camera").hidden = st.camera;
  if (Date.now() - toggling > 1500) $("#control").checked = st.enabled;
  if (config) {
    const s = config.settings;
    $("#hand-chip").hidden = false;
    $("#hand-line").textContent = s.control_source !== "hand" ? "הסמן זז לפי הראש"
      : st.active_hand ? `יד ${HANDS[st.active_hand]} · שולטת` : `יד שולטת: ${HANDS[s.control_hand]}`;
  }
  const liveHand = new Set(detectHand.split(" + ")), liveHead = new Set(detectHead.split(" + "));
  for (const row of $$(".row")) row.classList.toggle("live", liveHand.has(row.dataset.name) || liveHead.has(row.dataset.name));
  // הפעולה של המחווה המזוהה (הראשונה), בכרטיס של כל סוג מתחת לווידאו
  const rows = config ? Object.values(config.groups).flat() : [];
  const handRows = rows.filter((r) => r.kind !== "head"), headRows = rows.filter((r) => r.kind === "head");
  $("#detect-action-hand").textContent = handRows.find((r) => liveHand.has(r.name))?.text || "—";
  $("#detect-action-head").textContent = headRows.find((r) => liveHead.has(r.name))?.text || "—";
  renderRecording(st);
  if ($("#tab-diag").classList.contains("active")) { renderConf(st); renderPerf(st.perf); }   // רק כשהלשונית פתוחה
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
  for (const kind of Object.keys(KINDS)) {   // הלשונית קובעת אם זו מחוות יד או ראש
    $(`#rec-start-${kind}`).onclick = () => {
      setRecMsg("", true, kind);
      api("/api/custom", { op: "record", name: $(`#rec-name-${kind}`).value, mode: "new", kind }).then(() => { $(`#rec-name-${kind}`).value = ""; })
        .catch((e) => setRecMsg(e.message, false, kind));
    };
    $(`#rec-cancel-${kind}`).onclick = () => api("/api/custom", { op: "cancel" });
  }
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
