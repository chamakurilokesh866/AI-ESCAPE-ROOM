"""Streamlit UI for Version 2 of the AI Escape Room.

Run from the repository root:
    streamlit run v2/app.py

The UI only *shows* the game. Python (v2.engine) still decides every action,
Gemini still never sees the codes, and narration is still streamed through the
leak guard before it reaches the screen. Quick-action and examine buttons just
send ordinary text commands through the same Game.turn() pipeline as typing.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from v2 import llm as llm_mod  # noqa: E402
from v2 import ui  # noqa: E402
from v2.game import OPENING_MESSAGE, Game  # noqa: E402
from v2.room import FINAL_CHALLENGE, PUZZLES, TITLE  # noqa: E402

st.set_page_config(page_title="AI Escape Room · The Locked Library", page_icon="🔐",
                   layout="wide", initial_sidebar_state="collapsed")

STORY = ("You wake on a cold wooden floor, surrounded by towering shelves and the smell of old "
         "paper. The only exit is a heavy oak door with a four-digit keypad. Search the room, "
         "solve three puzzles and find the code before the candle burns out.")
QUICK_ACTIONS = [("👀 Look around", "look"), ("💡 Hint", "hint"),
                 ("🎒 Inventory", "inventory"), ("❓ Help", "help")]
AVATARS = {"assistant": "🧙", "user": "🧑"}


@st.cache_resource(show_spinner=False)
def gemini_client(api_key: str):
    """One Gemini client per key, reused across turns, restarts and reruns
    (keeps the HTTPS connection warm instead of reconnecting every game)."""
    return llm_mod.make_client(api_key)


def new_game() -> None:
    llm = None
    st.session_state.startup_error = None
    if llm_mod.get_api_key():
        try:
            llm = llm_mod.LLM(gemini_client(llm_mod.get_api_key()))
        except Exception as exc:  # e.g. SDK not installed
            st.session_state.startup_error = f"Could not create the Gemini client: {exc}"
    st.session_state.game = Game(llm=llm)
    st.session_state.messages = [{"role": "assistant", "content": OPENING_MESSAGE, "notices": []}]
    st.session_state.last = None
    st.session_state.hints_used = 0
    st.session_state.wrong_codes = 0  # all wrong codes (the engine resets its counter on success)
    st.session_state.start_time = time.time()
    st.session_state.end_time = None
    st.session_state.celebrated = False
    st.session_state.pending = None


def queue_command(command: str) -> None:
    """Button callback: the command is played on this rerun, exactly as if typed."""
    st.session_state.pending = command


if "game" not in st.session_state:
    new_game()

game: Game = st.session_state.game
st.html(ui.CSS)

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    if st.button("🔄 Restart game", width="stretch", type="primary"):
        new_game()
        st.rerun()
    st.header("How to play")
    st.markdown(
        """
Type what you want to do in plain English, or use the buttons:
- *examine the bookshelf*
- *take the magnifying glass*
- *read the note*
- *use the brass key on the compartment*
- *enter 1234 on the drawer*

Commands: **look**, **inventory**, **hint**, **help**.

**Goal:** solve three puzzles, find the door code and escape.
"""
    )
    st.divider()
    st.caption("Version 2 · Python enforces the rules, Gemini narrates")
    if game.offline:
        st.caption("Mode: **offline** (keyword parser, built-in text)")
    else:
        st.caption(f"Model: `{game.llm.model}`")
        st.caption(f"Fallback: `{game.llm.fallback_model or 'disabled'}` · retries: {game.llm.max_retries}")

# ---------------------------------------------------------------- header
mode = "Offline mode" if game.offline else f"Gemini · {game.llm.model}"
st.markdown(ui.hero_html(TITLE, STORY, mode), unsafe_allow_html=True)
stats_slot = st.container()  # filled at the end so it shows the state *after* this turn

if st.session_state.get("startup_error"):
    st.error(st.session_state.startup_error)
if game.offline:
    st.info(
        "**Offline mode:** `GEMINI_API_KEY` is not set, so the game uses its built-in "
        "keyword parser and descriptions. Add your key to `.env` and restart for "
        "Gemini narration (free key: https://aistudio.google.com/apikey).",
        icon="🕯️",
    )
win_slot = st.container()

chat_col, side_col = st.columns([7, 5], gap="large")

# ---------------------------------------------------------------- chat log
with chat_col:
    # Scrolls and sticks to the newest message; the room panel stays in view.
    chat_box = st.container(height=600, border=False, key="chatlog", autoscroll=True)
    for msg in st.session_state.messages:
        with chat_box.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
            st.markdown(msg["content"])
            for notice in msg.get("notices", []):
                st.warning(notice, icon="⚠️")
    quick_slot = st.container(key="quick")

# ---------------------------------------------------------------- play a turn
typed = st.chat_input("What do you do?  (e.g. examine the painting)", disabled=game.state.escaped)
prompt = typed or st.session_state.pop("pending", None)
st.session_state.pending = None
if prompt and not game.state.escaped:
    with chat_box.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(prompt)
    with chat_box.chat_message("assistant", avatar=AVATARS["assistant"]):
        placeholder = st.empty()
        placeholder.markdown("_🕯️ The Game Master is thinking..._")
        # Narration streams in as Gemini writes it (already checked by the leak guard).
        result = game.turn(prompt, on_text=lambda text: placeholder.markdown(text + " ▌"))
        placeholder.markdown(result.reply)
        for notice in result.notices:
            st.warning(notice, icon="⚠️")
    st.session_state.messages.append({"role": "user", "content": prompt, "notices": []})
    st.session_state.messages.append(
        {"role": "assistant", "content": result.reply, "notices": result.notices}
    )
    st.session_state.last = result
    kind = result.outcome.kind if result.outcome is not None else ""
    st.session_state.hints_used += kind == "hint"
    st.session_state.wrong_codes += kind == "wrong_code"

state = game.state  # the turn may have replaced the state object (rollback)
if state.escaped and st.session_state.end_time is None:
    st.session_state.end_time = time.time()
escaped = state.escaped
done, total = state.progress()
wrong = st.session_state.wrong_codes
start, end = st.session_state.start_time, st.session_state.end_time

# ---------------------------------------------------------------- stats strip
with stats_slot:
    # Only integers go into this HTML (no player or LLM text), so the iframe is safe.
    st.iframe(
        ui.stats_bar_html(state.turn, st.session_state.hints_used, wrong, done, total,
                          int(start * 1000), None if end is None else int(end * 1000)),
        height=72,
    )

# ---------------------------------------------------------------- win screen
if escaped:
    with win_slot:
        st.markdown(ui.win_html(state.turn, ui.fmt_duration((end or time.time()) - start),
                                st.session_state.hints_used, wrong), unsafe_allow_html=True)
        if st.button("🔁 Play again", type="primary", key="play_again"):
            new_game()
            st.rerun()
    if not st.session_state.celebrated:
        st.balloons()
        st.session_state.celebrated = True

# ---------------------------------------------------------------- quick actions
with quick_slot:
    cols = st.columns(len(QUICK_ACTIONS))
    for col, (label, command) in zip(cols, QUICK_ACTIONS):
        col.button(label, key=f"qa_{command}", on_click=queue_command, args=(command,),
                   disabled=escaped, width="stretch")

# ---------------------------------------------------------------- room panel
with side_col:
    with st.container(key="panel_scene"):
        st.markdown('<div class="panel-title">🏛️ The room</div>', unsafe_allow_html=True)
        objects = ui.scene_objects(state)
        for row in (objects[:3], objects[3:]):
            for col, obj in zip(st.columns(3, gap="small"), row):
                with col, st.container(key=f"objcard_{obj['key']}"):
                    st.markdown(ui.card_html(obj), unsafe_allow_html=True)
                    st.button("Examine", key=f"ex_{obj['key']}", icon="🔍",
                              on_click=queue_command, args=(obj["command"],),
                              disabled=escaped or not obj["enabled"], width="stretch")

    with st.container(key="panel_inventory"):
        st.markdown('<div class="panel-title">🎒 Inventory</div>', unsafe_allow_html=True)
        st.markdown(ui.inventory_html(state.inventory), unsafe_allow_html=True)

    with st.container(key="panel_progress"):
        st.markdown('<div class="panel-title">🧩 Progress</div>', unsafe_allow_html=True)
        st.progress(done / total, text=f"{done} of {total} steps complete")
        steps = [(label, pid in state.solved) for pid, label in PUZZLES.items()]
        steps.append((FINAL_CHALLENGE, escaped))
        st.markdown(ui.checklist_html(steps), unsafe_allow_html=True)
        st.caption(f"Wrong codes this game: {wrong} · current attempts: drawer "
                   f"{state.wrong_attempts['drawer']}, door {state.wrong_attempts['door']}")

    last = st.session_state.get("last")
    with st.expander("🔍 Last turn (how V2 decided)"):
        if last is None:
            st.caption("No turn yet.")
        elif last.blocked:
            st.markdown(f"**Blocked by guardrail:** `{last.blocked}`. The game state was not changed.")
        else:
            a = last.action
            st.markdown(
                f"- Parsed by: **{last.parser_source}**"
                f"{' (keyword fast path, no Gemini call)' if last.parser_source == 'fast' else ''}\n"
                f"- Action: `{a.verb}` target=`{a.target or a.raw_target}` item=`{a.item}` code=`{a.code}`\n"
                f"- Engine verdict: **{'allowed' if last.outcome.ok else 'refused'}** (`{last.outcome.kind}`)\n"
                f"- Narrated by: **{last.narrated_by}**"
            )
    with st.expander("🧾 Game state (JSON)"):
        st.json(state.to_dict())
