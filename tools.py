# Author: Shawn Canady
"""tools.py - the three tools, their schemas, and dispatch().

    calculate(a, b, operation)   read-only
    list_notes()                 read-only
    save_note(title, text)       WRITES to notes.json, needs the user's confirmation

There is no delete_note function on purpose. A function that does not
exist cannot be called, no matter what the model asks for.

The model only asks for a tool by name. dispatch() decides whether the
tool really runs, so it treats everything from the model as untrusted.
"""

import json
import os
from datetime import datetime

NOTES_FILE = os.path.join(os.path.dirname(__file__), "notes.json")
MAX_TITLE = 80
MAX_TEXT = 500


# ---------------------------------------------------------------------------
# Tool 1 (read-only): calculate
# ---------------------------------------------------------------------------

def calculate(a, b, operation):
    """Do one arithmetic operation on two numbers."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise ValueError("a and b must be numbers")
    if operation == "add":
        return a + b
    if operation == "subtract":
        return a - b
    if operation == "multiply":
        return a * b
    if operation == "divide":
        if b == 0:
            raise ValueError("cannot divide by zero")
        return a / b
    raise ValueError("operation must be add, subtract, multiply, or divide")


# ---------------------------------------------------------------------------
# Notes helpers
# ---------------------------------------------------------------------------

def load_notes():
    """Read the notes file. If there is no file yet, there are no notes."""
    if not os.path.exists(NOTES_FILE):
        return []
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def check_note(title, text):
    """Raise a ValueError if the title or text is not acceptable."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if len(title) > MAX_TITLE:
        raise ValueError(f"title is too long (limit {MAX_TITLE} characters)")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text is too long (limit {MAX_TEXT} characters)")


# ---------------------------------------------------------------------------
# Tool 2 (read-only): list_notes
# ---------------------------------------------------------------------------

def list_notes():
    """Return the saved notes as text."""
    notes = load_notes()
    if not notes:
        return "You have no saved notes."
    lines = []
    for note in notes:
        lines.append(f"#{note['id']} {note['title']}: {note['text']} (saved {note['saved']})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3 (writes): save_note
# ---------------------------------------------------------------------------

def save_note(title, text):
    """Add a new note to notes.json. This changes a file on disk."""
    check_note(title, text)
    notes = load_notes()
    note = {
        "id": len(notes) + 1,
        "title": title.strip(),
        "text": text.strip(),
        "saved": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    notes.append(note)
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)
    return f'Saved note #{note["id"]}: "{note["title"]}"'


# ---------------------------------------------------------------------------
# The allowed tools and their schemas
# ---------------------------------------------------------------------------

# Only names in this dictionary can ever run.
TOOLS = {
    "calculate": calculate,
    "list_notes": list_notes,
    "save_note": save_note,
}

# Tools that change data. These never run until the user confirms.
WRITE_TOOLS = ["save_note"]

# The model only sees these schemas. Each description says WHEN to call the
# tool, the way you would tell a new employee when to use a form.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Do arithmetic on two numbers. Call this whenever the user asks for a "
                "calculation, a percentage, a tip, a total, or any math, even simple "
                "math, instead of working it out yourself. It does one operation at a "
                "time, so for a longer problem call it several times and use each "
                "result in the next call. Do not use it for anything that is not math. "
                "For a percentage, multiply by the percent divided by 100, so 15% of "
                "240 is multiply 240 by 0.15."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "The first number."},
                    "b": {"type": "number", "description": "The second number."},
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "What to do with a and b.",
                    },
                },
                "required": ["a", "b", "operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": (
                "Read back the notes the user has already saved. Call this when the "
                "user asks what notes they have, or asks you to find or recall "
                "something they saved earlier. It only reads. It never changes "
                "anything, so do not call it to save, edit, or delete a note."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": (
                "Save a NEW note to the user's notes file. Call this only when the "
                "user clearly asks you to save, remember, or write down something. "
                "Never call it on your own and never to record your own answers. "
                "Saving changes stored data, so the user is shown exactly what will "
                "be saved and must approve it first. Until they approve, the note is "
                "NOT saved, so never tell the user it is saved. Tell them it is "
                "waiting for their confirmation. This tool cannot edit or delete "
                "existing notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": f"A short title, at most {MAX_TITLE} characters.",
                    },
                    "text": {
                        "type": "string",
                        "description": f"The note body, at most {MAX_TEXT} characters.",
                    },
                },
                "required": ["title", "text"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def dispatch(name, raw_arguments, confirmed=False):
    """Run a tool the model asked for and return the result as text.

    This never raises an error. A problem comes back as text that starts
    with "Error", so the model can explain it to the user.

    confirmed is only set to True by the app, after the user clicks Confirm.
    The model cannot set it. Write tools do not run without it.
    """
    # 1. Check the name against our own list BEFORE looking anything up.
    if name not in TOOLS:
        return f"Error: unknown tool '{name}'. I have no such tool."

    # 2. The arguments are a JSON string that might be empty or broken.
    try:
        if raw_arguments and raw_arguments.strip():
            args = json.loads(raw_arguments)
        else:
            args = {}
    except json.JSONDecodeError:
        return "Error: the arguments were not valid JSON."
    if not isinstance(args, dict):
        return "Error: the arguments must be a JSON object."

    # 3. Write tools need the user's confirmation first.
    if name in WRITE_TOOLS and not confirmed:
        try:
            check_note(args.get("title"), args.get("text"))
        except ValueError as error:
            return f"Error: {error}"
        return (
            f"NOT RUN: {name} changes saved data and needs the user's "
            "confirmation first. Nothing was saved. Tell the user it is "
            "waiting for their confirmation."
        )

    # 4. Run the tool. If it fails, send the failure back as the result.
    try:
        result = TOOLS[name](**args)
    except Exception as error:
        return f"Error: the tool failed: {error}"
    return str(result)
