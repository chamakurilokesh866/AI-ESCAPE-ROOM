"""Presentation helpers for the Version 2 Streamlit UI.

Pure functions only (no Streamlit calls), so the look of the room can be
unit-tested. Nothing here reads the secret codes: every value comes from the
public GameState that the UI already shows.
"""

from __future__ import annotations

import html

from v2.state import GameState

ITEM_ICONS = {
    "note": "📜",
    "magnifying glass": "🔍",
    "brass key": "🗝️",
    "index card": "🪪",
    "diary": "📔",
}

# status kind -> (icon, css class)
STATUS_STYLE = {
    "hidden": ("❔", "hidden"),
    "unexplored": ("✨", "new"),
    "examined": ("👁️", "seen"),
    "locked": ("🔒", "locked"),
    "unlocked": ("🔓", "open"),
    "opened": ("✅", "open"),
}


def scene_objects(state: GameState) -> list[dict]:
    """The room's objects as cards: name, icon, status kind/label, examine command."""
    f, seen = state.flags, set(state.examined)

    def explored(name: str, done_label: str = "Examined", done_kind: str = "examined"):
        return (done_kind, done_label) if name in seen else ("unexplored", "Unexplored")

    on_desk = [i for i in ("note", "magnifying glass") if not state.has(i)]
    if "desk" not in seen:
        desk = ("unexplored", "Unexplored")
    elif on_desk:
        desk = ("examined", f"{len(on_desk)} item{'s' if len(on_desk) > 1 else ''} on top")
    else:
        desk = ("opened", "Searched")

    painting = ("opened", "Secret found") if f["compartment_found"] else explored("painting")
    drawer = ("unlocked", "Unlocked") if f["drawer_unlocked"] else ("locked", "Code lock")
    door = ("opened", "Open!") if f["door_open"] else ("locked", "Keypad lock")
    if not f["compartment_found"]:
        compartment = ("hidden", "Not found")
    elif f["compartment_open"]:
        compartment = ("unlocked", "Open")
    else:
        compartment = ("locked", "Keyhole")

    cards = [
        ("desk", "Desk", "🪑", desk),
        ("bookshelf", "Bookshelf", "📚", explored("bookshelf", "Clues found")),
        ("painting", "Painting", "🖼️", painting),
        ("drawer", "Drawer", "🗃️", drawer),
        ("door", "Oak door", "🚪", door),
        ("compartment", "Compartment" if f["compartment_found"] else "???", "🧰"
         if f["compartment_found"] else "❔", compartment),
    ]
    out = []
    for key, name, icon, (kind, label) in cards:
        out.append({
            "key": key, "name": name, "icon": icon, "kind": kind, "label": label,
            "status_icon": STATUS_STYLE[kind][0], "css": STATUS_STYLE[kind][1],
            "command": f"examine the {key}",
            "enabled": kind != "hidden",
        })
    return out


def card_html(obj: dict) -> str:
    return (
        f'<div class="obj-card obj-{obj["css"]}">'
        f'<div class="obj-icon">{obj["icon"]}</div>'
        f'<div class="obj-name">{html.escape(obj["name"])}</div>'
        f'<span class="pill pill-{obj["css"]}">{obj["status_icon"]} {html.escape(obj["label"])}</span>'
        f"</div>"
    )


def inventory_html(inventory: list[str]) -> str:
    if not inventory:
        return '<div class="chips"><span class="chip chip-empty">Your pockets are empty</span></div>'
    chips = "".join(
        f'<span class="chip">{ITEM_ICONS.get(i, "•")} {html.escape(i)}</span>' for i in inventory
    )
    return f'<div class="chips">{chips}</div>'


def checklist_html(steps: list[tuple[str, bool]]) -> str:
    rows = "".join(
        f'<li class="{"done" if done else "todo"}"><span>{"✅" if done else "⬜"}</span>'
        f"{html.escape(label)}</li>"
        for label, done in steps
    )
    return f'<ul class="checklist">{rows}</ul>'


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def hero_html(title: str, story: str, mode: str) -> str:
    return (
        '<div class="hero">'
        '<div class="hero-kicker">AI Escape Room · Version 2</div>'
        f'<h1 class="hero-title">🔐 {html.escape(title)}</h1>'
        f'<p class="hero-story">{html.escape(story)}</p>'
        f'<span class="mode-badge">{html.escape(mode)}</span>'
        "</div>"
    )


def stats_bar_html(moves: int, hints: int, wrong: int, done: int, total: int,
                   start_ms: int, end_ms: int | None) -> str:
    """A small self-contained HTML/JS strip with a live timer (rendered in an iframe)."""
    frozen = "null" if end_ms is None else str(int(end_ms))
    return f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600&family=Lora:wght@400;600&display=swap');
  body {{ margin:0; background:transparent; font-family:'Lora',Georgia,serif; }}
  .bar {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; }}
  .stat {{ min-width:0; background:linear-gradient(180deg,#2a2017,#1d160f);
          border:1px solid #5a4526; border-radius:12px; padding:8px 12px; color:#EDE3D1;
          box-shadow: inset 0 1px 0 rgba(255,220,150,.06); }}
  .lbl {{ font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:#b59a6a; }}
  .val {{ font-family:'Cinzel',Georgia,serif; font-size:20px; color:#f1d48a; margin-top:2px; }}
  .lbl, .val {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  @media (max-width: 640px) {{
    .bar {{ gap:5px; }} .stat {{ padding:6px 6px; border-radius:10px; }}
    .lbl {{ font-size:9px; letter-spacing:.04em; }} .val {{ font-size:16px; }}
  }}
</style>
<div class="bar">
  <div class="stat"><div class="lbl">⏱ Time</div><div class="val" id="t">00:00</div></div>
  <div class="stat"><div class="lbl">👣 Moves</div><div class="val">{moves}</div></div>
  <div class="stat"><div class="lbl">💡 Hints</div><div class="val">{hints}</div></div>
  <div class="stat"><div class="lbl">❌ Wrong</div><div class="val">{wrong}</div></div>
  <div class="stat"><div class="lbl">🧩 Steps</div><div class="val">{done}/{total}</div></div>
</div>
<script>
  const start = {int(start_ms)}, end = {frozen};
  const el = document.getElementById('t');
  function pad(n) {{ return String(n).padStart(2,'0'); }}
  function tick() {{
    const s = Math.max(0, Math.floor(((end ?? Date.now()) - start) / 1000));
    const h = Math.floor(s/3600), m = Math.floor(s%3600/60), sec = s%60;
    el.textContent = (h ? h + ':' + pad(m) : pad(m)) + ':' + pad(sec);
  }}
  tick(); if (end === null) setInterval(tick, 1000);
</script>
"""


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Lora:ital,wght@0,400;0,600;1,400&display=swap');

:root {
  --brass: #C9A24A; --brass-hi: #f1d48a; --ink: #EDE3D1; --muted: #b59a6a;
  --wood: #1d160f; --leather: #2a2017; --edge: #5a4526;
}
html, body, .stApp, [data-testid="stMarkdownContainer"], .stChatMessage {
  font-family: 'Lora', Georgia, serif;
}
.stApp {
  background:
    radial-gradient(1200px 500px at 15% -10%, rgba(201,162,74,.12), transparent 60%),
    radial-gradient(900px 600px at 110% 10%, rgba(120,60,20,.18), transparent 60%),
    #14100C;
}
.block-container { padding-top: 3.4rem; max-width: 1400px; }
h1, h2, h3, h4, .hero-title, .panel-title { font-family: 'Cinzel', Georgia, serif !important; }

/* ---------- hero ---------- */
.hero {
  position: relative; padding: 22px 26px 18px; margin-bottom: 10px; border-radius: 18px;
  background: linear-gradient(135deg, rgba(58,40,22,.95), rgba(26,19,13,.95));
  border: 1px solid var(--edge);
  box-shadow: 0 10px 30px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,220,150,.08);
}
.hero-kicker { color: var(--muted); letter-spacing: .25em; text-transform: uppercase; font-size: .75rem; }
.hero-title {
  margin: .15rem 0 .35rem !important; padding: 0 !important; font-size: 2.3rem !important;
  color: var(--brass-hi) !important; text-shadow: 0 2px 12px rgba(201,162,74,.35);
}
.hero-story { color: #d9cbb1; font-style: italic; max-width: 70ch; margin: 0 0 .4rem; line-height: 1.55; }
.mode-badge {
  position: absolute; top: 18px; right: 22px; font-size: .75rem; padding: 4px 10px;
  border-radius: 999px; border: 1px solid var(--edge); color: var(--brass-hi); background: rgba(0,0,0,.25);
}

/* ---------- panels / cards ---------- */
.panel-title { color: var(--brass-hi); font-size: 1.05rem; letter-spacing: .06em; margin: .2rem 0 .5rem; }
div[class*="st-key-panel"] {
  background: linear-gradient(180deg, rgba(42,32,23,.85), rgba(29,22,15,.85));
  border: 1px solid var(--edge); border-radius: 16px; padding: 14px 16px 12px;
  box-shadow: 0 6px 20px rgba(0,0,0,.35);
}
div[class*="st-key-objcard"] {
  background: linear-gradient(180deg, #2b2118, #1c150f);
  border: 1px solid var(--edge); border-radius: 14px; padding: 10px 10px 8px;
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
}
div[class*="st-key-objcard"]:hover {
  transform: translateY(-2px); border-color: var(--brass); box-shadow: 0 6px 18px rgba(201,162,74,.18);
}
.obj-card { text-align: center; }
.obj-icon { font-size: 2rem; line-height: 1.1; filter: drop-shadow(0 2px 6px rgba(0,0,0,.6)); }
.obj-name { font-family: 'Cinzel', Georgia, serif; color: var(--ink); font-size: .95rem; margin: 2px 0 4px; }
.obj-hidden .obj-icon { opacity: .45; }
.pill {
  display: inline-block; font-size: .72rem; padding: 2px 9px; border-radius: 999px;
  border: 1px solid transparent; white-space: nowrap;
}
.pill-new    { background: rgba(201,162,74,.12); color: var(--brass-hi); border-color: rgba(201,162,74,.35); }
.pill-seen   { background: rgba(140,160,190,.12); color: #c9d6ea; border-color: rgba(140,160,190,.35); }
.pill-locked { background: rgba(190,70,50,.14);  color: #f0a796; border-color: rgba(190,70,50,.45); }
.pill-open   { background: rgba(80,160,90,.15);  color: #a9e2b0; border-color: rgba(80,160,90,.45); }
.pill-hidden { background: rgba(255,255,255,.05); color: #9a8f80; border-color: rgba(255,255,255,.12); }

.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 6px; }
.chip {
  padding: 5px 12px; border-radius: 999px; font-size: .88rem; color: #1b140c;
  background: linear-gradient(180deg, #f1d48a, #c9a24a); border: 1px solid #8a6a2a;
  box-shadow: 0 2px 6px rgba(0,0,0,.35);
}
.chip-empty { background: rgba(255,255,255,.04); color: #9a8f80; border: 1px dashed #5a4526; box-shadow: none; }

.checklist { list-style: none; padding: 0; margin: 4px 0 0; }
.checklist li { display: flex; gap: 8px; padding: 5px 0; border-bottom: 1px dashed rgba(90,69,38,.6); font-size: .9rem; }
.checklist li:last-child { border-bottom: none; }
.checklist li.done { color: #a9e2b0; }
.checklist li.todo { color: #d9cbb1; }

/* ---------- progress bar ---------- */
[data-testid="stProgress"] > div > div > div > div {
  background: linear-gradient(90deg, #8a6a2a, #f1d48a) !important;
}

/* ---------- chat ---------- */
div[class*="st-key-chatlog"] {
  background: linear-gradient(180deg, rgba(20,15,10,.65), rgba(29,22,15,.65));
  border: 1px solid var(--edge); border-radius: 16px; padding: 6px 8px;
}
[data-testid="stChatMessage"] {
  border-radius: 14px; padding: 10px 14px; margin: 6px 4px; line-height: 1.55;
  border: 1px solid rgba(90,69,38,.7);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
[data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) {
  background: linear-gradient(180deg, rgba(58,42,24,.75), rgba(36,27,18,.75));
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {
  background: rgba(70,80,95,.22); border-color: rgba(120,135,160,.35);
  margin-left: auto; width: 86%;
}
[data-testid="stChatInput"] textarea { font-family: 'Lora', Georgia, serif; }

/* ---------- buttons ---------- */
.stButton > button {
  border-radius: 10px; border: 1px solid var(--edge); background: linear-gradient(180deg, #34281c, #241b13);
  color: var(--ink); font-family: 'Lora', Georgia, serif; transition: all .15s ease;
}
.stButton > button:hover:not(:disabled) { border-color: var(--brass); color: var(--brass-hi); box-shadow: 0 0 0 1px rgba(201,162,74,.25); }
div[class*="st-key-quick"] .stButton > button { width: 100%; }

/* ---------- win screen ---------- */
.win {
  text-align: center; padding: 26px 20px 18px; border-radius: 18px; margin-bottom: 12px;
  background: radial-gradient(600px 220px at 50% 0%, rgba(241,212,138,.28), transparent 70%),
              linear-gradient(180deg, #3a2a16, #1d160f);
  border: 1px solid var(--brass); box-shadow: 0 0 40px rgba(201,162,74,.25);
}
.win h2 { color: var(--brass-hi) !important; font-size: 2rem !important; margin: 0 0 .3rem !important; }
.win p { color: #e8dcc4; margin: 0 0 12px; }
.win-stats { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
.win-stat { min-width: 110px; padding: 8px 12px; border-radius: 12px; border: 1px solid var(--edge); background: rgba(0,0,0,.25); }
.win-stat b { display: block; font-family: 'Cinzel', Georgia, serif; font-size: 1.4rem; color: var(--brass-hi); }
.win-stat span { font-size: .72rem; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }

/* ---------- alerts in the theme's colours ---------- */
[data-testid="stAlertContentInfo"] { color: #e8dcc4; }
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) > div {
  background: rgba(201,162,74,.10); border: 1px solid rgba(201,162,74,.35);
}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1d160f, #14100c); border-right: 1px solid var(--edge); }

/* ---------- responsive ---------- */
@media (max-width: 900px) {
  .hero-title { font-size: 1.7rem !important; }
  .mode-badge { position: static; display: inline-block; margin-top: 4px; }
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { width: 94%; }
}
</style>
"""


def win_html(moves: int, time_text: str, hints: int, wrong: int) -> str:
    stats = [(moves, "Moves"), (time_text, "Time"), (hints, "Hints used"), (wrong, "Wrong codes")]
    cells = "".join(f'<div class="win-stat"><b>{v}</b><span>{k}</span></div>' for v, k in stats)
    return (
        '<div class="win"><h2>🏆 You escaped the library!</h2>'
        "<p>The keypad flashes green, the bolt slides back and the heavy oak door swings open.</p>"
        f'<div class="win-stats">{cells}</div></div>'
    )
