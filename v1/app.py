"""Streamlit UI for Version 1 of the AI Escape Room.

Run from the repository root:
    streamlit run v1/app.py
"""

import sys
from pathlib import Path

# Allow "from v1 import ..." when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from v1.game_master import GameMaster, get_api_key, get_model_name, make_client  # noqa: E402
from v1.prompts import ESCAPE_MARKER, OPENING_MESSAGE  # noqa: E402

st.set_page_config(page_title="AI Escape Room - V1", page_icon="🔐")


def new_game() -> None:
    """Reset everything stored for this browser session."""
    st.session_state.messages = [{"role": "assistant", "content": OPENING_MESSAGE}]
    st.session_state.gm = GameMaster(client=make_client()) if get_api_key() else None


# ---------- Sidebar: intro, instructions, restart ----------
with st.sidebar:
    st.header("How to play")
    st.markdown(
        """
You are trapped in a locked library. An AI **Game Master** (Google Gemini)
describes the room and reacts to everything you do.

**Type what you want to do in plain English**, for example:
- *examine the bookshelf*
- *pick up the magnifying glass*
- *try 1234 on the drawer*
- *look behind the painting*

Special commands: **hint** for a nudge, **inventory** to see what you carry.

Goal: find the four-digit door code and escape.
"""
    )
    if st.button("🔄 Restart game", use_container_width=True):
        new_game()
        st.rerun()
    st.caption(f"Version 1 · model: `{get_model_name()}`")

st.title("🔐 AI Escape Room")
st.caption("Version 1 - the LLM runs the whole game")

if not get_api_key():
    st.error(
        "**GEMINI_API_KEY is not set.** Copy `.env.example` to `.env`, add your "
        "free key from https://aistudio.google.com/apikey and restart the app."
    )
    st.stop()

if "messages" not in st.session_state or st.session_state.get("gm") is None:
    new_game()

gm: GameMaster = st.session_state.gm

# ---------- Chat history ----------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧙" if msg["role"] == "assistant" else "🧑"):
        st.markdown(msg["content"])

if gm.escaped:
    st.success("🎉 You escaped the library! Press **Restart game** in the sidebar to play again.")
    st.balloons()

# ---------- Player input ----------
prompt = st.chat_input("What do you do?", disabled=gm.escaped)
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🧙"):
        placeholder = st.empty()
        placeholder.markdown("_The Game Master is thinking..._")
        try:
            # Minor speed patch: show the reply while Gemini is still writing it.
            shown = ""
            for chunk in gm.send_stream(prompt):
                shown += chunk
                visible = shown.replace(ESCAPE_MARKER, "")
                if "[" in visible:  # don't flash a half-written [ESCAPED] marker
                    visible = visible[: visible.rindex("[")]
                placeholder.markdown(visible + " ▌")
            reply = gm.last_reply
        except Exception as exc:  # V1: simple error display, no retries
            reply = f"⚠️ Could not reach Gemini: `{exc}`"
            gm.history.pop()  # drop the unanswered player turn
        placeholder.markdown(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    if gm.escaped:
        st.rerun()
