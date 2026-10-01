# Author: Shawn Canady
"""app.py - Streamlit app for the tool calling agent.

Run with:  streamlit run app.py

The model can never save a note by itself. When it asks to, the app shows
exactly what would be saved and waits. The note is only saved when the user
clicks Confirm.
"""

import json

import streamlit as st
from groq import Groq

from agent import MAX_ITERATIONS, MODEL, run_agent
from tools import dispatch

st.set_page_config(page_title="Tool Calling Agent")
st.title("Tool Calling Agent")
st.caption(
    f"Model: {MODEL} | Tools: calculate, list_notes, save_note | "
    f"Max {MAX_ITERATIONS} tool rounds per question"
)

# --- API key: read from .streamlit/secrets.toml, never written in the code ---
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    api_key = None

if not api_key:
    st.error(
        "No Groq API key found. Put GROQ_API_KEY in .streamlit/secrets.toml "
        "and restart the app."
    )
    st.stop()

client = Groq(api_key=api_key)

# --- Session state (Streamlit keeps this between reruns) ---
st.session_state.setdefault("history", [])   # the chat messages
st.session_state.setdefault("tool_log", [])  # every tool call so far
st.session_state.setdefault("pending", [])   # saves waiting for the user


def status_label(result):
    """Short label for the tool log, based on how the result starts."""
    if result.startswith("NOT RUN"):
        return "[pending]"
    if result.startswith("Error") or result.startswith("Cancelled"):
        return "[error]"
    return "[ok]"


# --- Sidebar: the tool log ---
with st.sidebar:
    st.header("Tool log")
    if st.button("Clear chat and log"):
        st.session_state.history = []
        st.session_state.tool_log = []
        st.session_state.pending = []
        st.rerun()
    if not st.session_state.tool_log:
        st.info("No tools called yet. Try: What is 15% of 240?")
    for number, entry in enumerate(st.session_state.tool_log, start=1):
        with st.expander(f"{number}. {entry['tool']} {status_label(entry['result'])}"):
            st.markdown(f"**Round:** {entry['round']}")
            st.markdown("**Arguments**")
            st.code(entry["arguments"] or "{}", language="json")
            st.markdown("**Result**")
            st.code(entry["result"])

# --- Chat history ---
for turn in st.session_state.history:
    with st.chat_message(turn["role"]):
        st.write(turn["content"])

# --- Saves waiting for the user. The note is only saved on a Confirm click. ---
for index, item in enumerate(list(st.session_state.pending)):
    args = json.loads(item["arguments"])
    with st.container(border=True):
        st.warning(
            f'**Confirmation needed.** Save a new note titled "{args.get("title")}" '
            f'with the text: "{args.get("text")}"'
        )
        col_yes, col_no, _ = st.columns([1, 1, 3])

        if col_yes.button("Confirm", key=f"yes_{index}"):
            result = dispatch(item["tool"], item["arguments"], confirmed=True)
            st.session_state.tool_log.append({
                "round": "confirmed by user",
                "tool": item["tool"],
                "arguments": item["arguments"],
                "result": result,
            })
            if result.startswith("Error"):
                message = f"The note was not saved. {result}"
            else:
                message = result
            st.session_state.history.append({"role": "assistant", "content": message})
            st.session_state.pending.pop(index)
            st.rerun()

        if col_no.button("Cancel", key=f"no_{index}"):
            st.session_state.tool_log.append({
                "round": "cancelled by user",
                "tool": item["tool"],
                "arguments": item["arguments"],
                "result": "Cancelled by the user. Nothing was saved.",
            })
            st.session_state.history.append(
                {"role": "assistant", "content": "Okay, I did not save that note."}
            )
            st.session_state.pending.pop(index)
            st.rerun()

# --- New message from the user ---
prompt = st.chat_input("Ask me to calculate, list your notes, or save a note")
if prompt:
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                answer, new_calls = run_agent(client, st.session_state.history)
            except Exception as error:  # bad key, network problem, rate limit, etc.
                answer, new_calls = f"Sorry, the request failed: {error}", []
        st.write(answer)

    st.session_state.history.append({"role": "assistant", "content": answer})
    st.session_state.tool_log.extend(new_calls)

    # Any save the model asked for goes in the waiting list for the user.
    for call in new_calls:
        if call["result"].startswith("NOT RUN"):
            st.session_state.pending.append(
                {"tool": call["tool"], "arguments": call["arguments"]}
            )
    st.rerun()
