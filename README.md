Shawn Canady

 Assignment 7: Agents and Tool Calling

A Streamlit chat app where a Groq-hosted model (openai/gpt-oss-120b) can call three tools. A sidebar tool log shows every call the model made, the arguments it sent, and what came back.

The three tools:

- calculate(a, b, operation) is read-only. It adds, subtracts, multiplies, or divides two numbers.
- list_notes() is read-only. It returns the saved notes from notes.json.
- save_note(title, text) writes. It adds a note to notes.json, and it runs only after the user clicks Confirm.

 Setup

Create and activate a virtual environment, then install the packages:

---
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
---

On Mac or Linux, activate with source .venv/bin/activate instead.

Make sure .gitignore lists .streamlit/secrets.toml.

Put your key in .streamlit/secrets.toml:

---
GROQ_API_KEY = "your-key-here"
---

Confirm the key file is ignored before you push. This must print a line, not nothing:

---
git check-ignore -v .streamlit/secrets.toml
---

 Run

---
streamlit run app.py
---

Try: What is 15% of 240?; Save a note called Dentist: Tuesday at 3 (a Confirm and Cancel box appears, and nothing is saved until you click Confirm); What notes do I have?; and Delete all my notes (there is no such tool, so the model should say it cannot).

 Test

---
python test_tools.py
---

No API key is needed. The loop tests use a fake client that replays scripted model replies, and the notes tests use a temporary file, so your real notes.json is never touched.

 Files

- tools.py: the three tools, their schemas, the TOOLS allow-list, the WRITE_TOOLS list, and dispatch()
- agent.py: the tool calling loop with an iteration cap
- app.py: the Streamlit interface with a tool log and the Confirm / Cancel step
- test_tools.py: tests for the tools, the dispatch guard, confirmation, and the loop
- .streamlit/secrets.toml: the API key (not committed)
- .gitignore: keeps the key and notes.json out of git
- requirements.txt: streamlit and groq

 How the safety works

The model only asks for a tool call: a name and a JSON string of arguments. It never runs anything. My code decides whether the call runs, and dispatch() in tools.py is the only place that happens. It treats everything from the model as untrusted:

1. Name check first. The tool name is checked against the TOOLS allow-list before anything is looked up. An unknown name returns an error to the model and runs nothing. A test proves it: it asks for delete_all_reservations and checks that an error comes back and no file was written.
2. Malformed arguments. The arguments arrive as a JSON string. They are parsed inside a try block, and a bad string comes back to the model as a tool result instead of crashing the app.
3. Tool failures. The tool itself runs inside a try block. If it fails, for example dividing by zero, the error is sent back to the model as a tool result so it can explain the problem to the user.
4. Confirmation before the write. save_note is listed in WRITE_TOOLS. dispatch() will not run it unless confirmed=True, and only the app sets that, after the user clicks Confirm. The agent loop never confirms anything. If the model tries to sneak in its own confirmed argument, the call is still blocked. Until the user clicks, the app shows exactly what would be saved, the title and the text, in a Confirm / Cancel box, so the user sees it before anything changes.
5. Iteration cap. The loop stops after 5 rounds no matter what and returns a clear message, so a model that keeps asking for tools cannot run until the rate limit is gone.

 The function I deliberately did not write

delete_note. The obvious next step after save_note is a way to remove notes, and I chose not to write one. A system prompt that says "never delete" is only a request, and a permission check inside a delete function could have a bug. A function that does not exist cannot be called, however the model is prompted or tricked. If the model asks for a delete, the name check rejects it and the model tells the user it cannot do that. A test called test_there_is_no_delete_tool makes sure it stays that way.

 A description I had to rewrite

save_note. My first description was just "Saves a note." It says what the function does but not when to call it, so the model had no guidance on the cases that matter: it could save things the user never asked to save, or record its own answers as notes. It also had no idea that the save needs approval, so it would tell the user "Done, I saved it!" while the note was still waiting for the Confirm click.

I rewrote it like an instruction to a new employee: call it only when the user clearly asks to save or remember something, never on its own, the user must approve first, until then the note is not saved so never say it is, and this tool cannot edit or delete. The other two descriptions got the same treatment: they say when to call the tool and when not to. test_descriptions_say_when_to_call checks that every description is more than a restatement of the function name.


