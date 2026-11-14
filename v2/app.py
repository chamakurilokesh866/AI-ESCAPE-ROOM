"""Streamlit UI for Version 2 of the AI Escape Room.

Run from the repository root:
    streamlit run v2/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from v2 import llm as llm_mod  # noqa: E402
from v2.game import OPENING_MESSAGE, Game  # noqa: E402
from v2.room import PUZZLES, FINAL_CHALLENGE  # noqa: E402

st.set_page_config(page_title="AI Escape Room - V2", page_icon="🔐", layout="wide")


def new_game() -> None:
    llm = None
    st.session_state.startup_error = None
    if llm_mod.get_api_key():
        try:
            llm = llm_mod.LLM(llm_mod.make_client())
        except Exception as exc:  # e.g. SDK not installed
            st.session_state.startup_error = f"Could not create the Gemini client: {exc}"
    st.session_state.game = Game(llm=llm)
    st.session_state.messages = [{"role": "assistant", "content": OPENING_MESSAGE, "notices": []}]
    st.session_state.last = None


if "game" not in st.session_state:
    new_game()

game: Game = st.session_state.game

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("How to play")
    st.markdown(
        """
You are trapped in a locked library. Type what you want to do in plain English:
- *examine the bookshelf*
- *take the magnifying glass*
- *read the note*
- *use the brass key on the compartment*
- *enter 1234 on the drawer*

Commands: **look**, **inventory**, **hint**, **help**.

**Goal:** solve three puzzles, find the door code and escape.
"""
    )
    if st.button("🔄 Restart game", width="stretch"):
        new_game()
        st.rerun()
    st.divider()
    st.caption("Version 2 · Python enforces the rules, Gemini narrates")
    if game.offline:
        st.caption("Mode: **offline** (keyword parser, built-in text)")
    else:
        st.caption(f"Model: `{game.llm.model}`")
        st.caption(f"Fallback: `{game.llm.fallback_model or 'disabled'}` · retries: {game.llm.max_retries}")

# ---------------------------------------------------------------- header
st.title("🔐 AI Escape Room")
st.caption("Version 2 - Reliable AI Escape Room: structured game state, action validation and guardrails")

if st.session_state.get("startup_error"):
    st.error(st.session_state.startup_error)
if game.offline:
    st.info(
        "**Offline mode:** `GEMINI_API_KEY` is not set, so the game uses its built-in "
        "keyword parser and descriptions. Add your key to `.env` and restart for "
        "Gemini narration (free key: https://aistudio.google.com/apikey)."
    )

# ---------------------------------------------------------------- input
prompt = st.chat_input("What do you do?", disabled=game.state.escaped)
if prompt:
    with st.spinner("The Game Master is thinking..."):
        result = game.turn(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt, "notices": []})
    st.session_state.messages.append(
        {"role": "assistant", "content": result.reply, "notices": result.notices}
    )
    st.session_state.last = result

state = game.state
chat_col, state_col = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------- chat
with chat_col:
    for msg in st.session_state.messages:
        avatar = "🧙" if msg["role"] == "assistant" else "🧑"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            for notice in msg.get("notices", []):
                st.warning(notice, icon="⚠️")
    if state.escaped:
        st.success("🎉 You escaped the library! Press **Restart game** in the sidebar to play again.")
        st.balloons()

# ---------------------------------------------------------------- state panel
with state_col:
    st.subheader("🗺️ Game state")
    done, total = state.progress()
    st.progress(done / total, text=f"Progress: {done}/{total} steps")

    st.markdown("**Puzzles**")
    for pid, label in PUZZLES.items():
        st.markdown(f"{'✅' if pid in state.solved else '⬜'} {label}")
    st.markdown(f"{'✅' if state.escaped else '⬜'} {FINAL_CHALLENGE}")

    st.markdown("**🎒 Inventory**")
    st.markdown(" ".join(f"`{i}`" for i in state.inventory) or "_empty_")

    f = state.flags
    compartment = ("❔ not found" if not f["compartment_found"]
                   else "🔓 open" if f["compartment_open"] else "🔒 locked")
    st.markdown("**Room**")
    st.markdown(
        f"| Object | Status |\n|---|---|\n"
        f"| Drawer | {'🔓 open' if f['drawer_unlocked'] else '🔒 locked'} |\n"
        f"| Compartment | {compartment} |\n"
        f"| Door | {'🚪 open' if f['door_open'] else '🔒 locked'} |"
    )
    st.caption(
        f"Turn {state.turn} · wrong codes: drawer {state.wrong_attempts['drawer']}, "
        f"door {state.wrong_attempts['door']}"
    )

    last = st.session_state.get("last")
    with st.expander("🔍 Last turn (how V2 decided)"):
        if last is None:
            st.caption("No turn yet.")
        elif last.blocked:
            st.markdown(f"**Blocked by guardrail:** `{last.blocked}`. The game state was not changed.")
        else:
            a = last.action
            st.markdown(
                f"- Parsed by: **{last.parser_source}**\n"
                f"- Action: `{a.verb}` target=`{a.target or a.raw_target}` item=`{a.item}` code=`{a.code}`\n"
                f"- Engine verdict: **{'allowed' if last.outcome.ok else 'refused'}** (`{last.outcome.kind}`)\n"
                f"- Narrated by: **{last.narrated_by}**"
            )
    with st.expander("🧾 Game state (JSON)"):
        st.json(state.to_dict())
