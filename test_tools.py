# Author: Shawn Canady
"""test_tools.py - tests for the tools, dispatch(), and the agent loop.

No API key is needed. Run from the assignment folder:  python test_tools.py
(pytest also works if you have it installed.)
"""

import inspect
import os
import sys
import tempfile
from types import SimpleNamespace

import agent
import tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def use_temp_notes_file():
    """Point the notes file at a temp folder so the real notes.json is never touched."""
    tools.NOTES_FILE = os.path.join(tempfile.mkdtemp(), "notes.json")
    return tools.NOTES_FILE


def make_call(name, arguments, call_id="call_1"):
    """A fake tool call, shaped like the ones the model sends."""
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def make_reply(content=None, tool_calls=None):
    """A fake model reply."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Plays back scripted replies in order. Repeats the last one if it runs out."""

    def __init__(self, replies):
        self.replies = replies
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        index = min(len(self.requests) - 1, len(self.replies) - 1)
        return self.replies[index]


# ---------------------------------------------------------------------------
# The three tools
# ---------------------------------------------------------------------------

def test_calculate_operations():
    assert tools.calculate(2, 3, "add") == 5
    assert tools.calculate(10, 4, "subtract") == 6
    assert tools.calculate(240, 0.15, "multiply") == 36
    assert tools.calculate(9, 3, "divide") == 3


def test_calculate_rejects_bad_input():
    bad_inputs = [(1, 0, "divide"), (1, 2, "power"), ("a", 2, "add"), (1, None, "add")]
    for a, b, operation in bad_inputs:
        try:
            tools.calculate(a, b, operation)
        except ValueError:
            continue
        raise AssertionError(f"calculate accepted {a!r}, {b!r}, {operation!r}")


def test_list_notes_when_there_are_none():
    use_temp_notes_file()
    assert tools.list_notes() == "You have no saved notes."


def test_save_note_then_list_notes():
    use_temp_notes_file()
    assert "Saved note #1" in tools.save_note("Groceries", "milk and eggs")
    tools.save_note("Second", "another one")
    listing = tools.list_notes()
    assert "Groceries" in listing and "Second" in listing


def test_save_note_checks_input():
    use_temp_notes_file()
    bad_inputs = [("", "text"), ("title", ""), ("t" * 200, "text"), ("title", "x" * 900)]
    for title, text in bad_inputs:
        try:
            tools.save_note(title, text)
        except ValueError:
            continue
        raise AssertionError(f"save_note accepted {title!r}, {text!r}")
    assert tools.list_notes() == "You have no saved notes."


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def test_three_tools_one_writes():
    assert len(tools.TOOLS) == 3
    assert len(tools.TOOL_SCHEMAS) == 3
    assert tools.WRITE_TOOLS == ["save_note"]


def test_schemas_match_functions():
    for schema in tools.TOOL_SCHEMAS:
        info = schema["function"]
        function = tools.TOOLS[info["name"]]
        assert set(info["parameters"]["properties"]) == set(inspect.signature(function).parameters)


def test_descriptions_say_when_to_call():
    for schema in tools.TOOL_SCHEMAS:
        text = schema["function"]["description"].lower()
        assert len(text) > 120, "description is too short"
        assert "call" in text, "description must say when to call the tool"


def test_there_is_no_delete_tool():
    for name in tools.TOOLS:
        assert "delete" not in name and "remove" not in name
    assert not hasattr(tools, "delete_note")


# ---------------------------------------------------------------------------
# dispatch: the name check
# ---------------------------------------------------------------------------

def test_unknown_tool_returns_error_and_runs_nothing():
    path = use_temp_notes_file()
    result = tools.dispatch("delete_all_reservations", "{}", confirmed=True)
    assert result.startswith("Error") and "unknown tool" in result
    assert not os.path.exists(path), "nothing may be written for an unknown tool"


def test_odd_names_are_rejected():
    for name in ["__import__", "eval", "Calculate", "", None]:
        assert tools.dispatch(name, "{}").startswith("Error"), name


# ---------------------------------------------------------------------------
# dispatch: bad input and failing tools
# ---------------------------------------------------------------------------

def test_dispatch_success():
    assert tools.dispatch("calculate", '{"a": 6, "b": 7, "operation": "multiply"}') == "42"


def test_malformed_json_returns_error():
    assert tools.dispatch("calculate", '{"a": 1, ').startswith("Error")


def test_arguments_must_be_an_object():
    assert tools.dispatch("calculate", "[1, 2]").startswith("Error")


def test_wrong_argument_names_return_error():
    assert tools.dispatch("calculate", '{"x": 1, "y": 2}').startswith("Error")


def test_tool_failure_becomes_a_result():
    result = tools.dispatch("calculate", '{"a": 1, "b": 0, "operation": "divide"}')
    assert result.startswith("Error") and "zero" in result


def test_empty_arguments_work_for_list_notes():
    use_temp_notes_file()
    assert tools.dispatch("list_notes", "") == "You have no saved notes."
    assert tools.dispatch("list_notes", None) == "You have no saved notes."


# ---------------------------------------------------------------------------
# dispatch: confirmation before the write
# ---------------------------------------------------------------------------

def test_save_is_blocked_without_confirmation():
    path = use_temp_notes_file()
    result = tools.dispatch("save_note", '{"title": "Dentist", "text": "Tuesday at 3"}')
    assert result.startswith("NOT RUN")
    assert not os.path.exists(path), "nothing may be saved before the user confirms"


def test_save_runs_after_confirmation():
    use_temp_notes_file()
    result = tools.dispatch("save_note", '{"title": "Dentist", "text": "Tuesday at 3"}', confirmed=True)
    assert result == 'Saved note #1: "Dentist"'
    assert "Dentist" in tools.list_notes()


def test_model_cannot_confirm_for_itself():
    path = use_temp_notes_file()
    result = tools.dispatch("save_note", '{"title": "T", "text": "body", "confirmed": true}')
    assert result.startswith("NOT RUN")
    assert not os.path.exists(path)


def test_bad_note_is_rejected_before_asking_the_user():
    use_temp_notes_file()
    result = tools.dispatch("save_note", '{"title": "", "text": "body"}')
    assert result.startswith("Error")


def test_read_only_tools_never_need_confirmation():
    use_temp_notes_file()
    assert not tools.dispatch("calculate", '{"a": 1, "b": 1, "operation": "add"}').startswith("NOT RUN")
    assert not tools.dispatch("list_notes", "{}").startswith("NOT RUN")


# ---------------------------------------------------------------------------
# The agent loop (a fake client stands in for the model, no network)
# ---------------------------------------------------------------------------

def test_loop_answers_without_tools():
    client = FakeClient([make_reply(content="Hello!")])
    answer, log = agent.run_agent(client, [{"role": "user", "content": "hi"}])
    assert answer == "Hello!" and log == []


def test_loop_sends_the_tools_and_model():
    client = FakeClient([make_reply(content="ok")])
    agent.run_agent(client, [{"role": "user", "content": "hi"}])
    request = client.requests[0]
    assert request["tools"] == tools.TOOL_SCHEMAS
    assert request["tool_choice"] == "auto"
    assert request["model"] == "openai/gpt-oss-120b"


def test_loop_runs_a_tool_then_finishes():
    client = FakeClient([
        make_reply(tool_calls=[make_call("calculate", '{"a": 240, "b": 0.15, "operation": "multiply"}')]),
        make_reply(content="15% of 240 is 36."),
    ])
    answer, log = agent.run_agent(client, [{"role": "user", "content": "15% of 240?"}])
    assert answer == "15% of 240 is 36."
    assert len(log) == 1 and log[0]["tool"] == "calculate" and log[0]["result"] == "36.0"
    roles = [m["role"] for m in client.requests[1]["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]


def test_loop_handles_several_rounds():
    use_temp_notes_file()
    client = FakeClient([
        make_reply(tool_calls=[make_call("calculate", '{"a": 2, "b": 21, "operation": "multiply"}', "c1")]),
        make_reply(tool_calls=[make_call("list_notes", "{}", "c2")]),
        make_reply(content="The answer is 42 and you have no notes."),
    ])
    answer, log = agent.run_agent(client, [{"role": "user", "content": "two things"}])
    assert [entry["tool"] for entry in log] == ["calculate", "list_notes"]
    assert [entry["round"] for entry in log] == [1, 2]


def test_loop_unknown_tool_lets_the_model_explain():
    client = FakeClient([
        make_reply(tool_calls=[make_call("delete_all_reservations", "{}")]),
        make_reply(content="Sorry, I cannot do that."),
    ])
    answer, log = agent.run_agent(client, [{"role": "user", "content": "delete everything"}])
    assert answer == "Sorry, I cannot do that."
    assert log[0]["result"].startswith("Error")


def test_loop_bad_arguments_do_not_crash():
    client = FakeClient([
        make_reply(tool_calls=[make_call("calculate", "{not json")]),
        make_reply(content="I could not read that request."),
    ])
    answer, log = agent.run_agent(client, [{"role": "user", "content": "math"}])
    assert answer == "I could not read that request."


def test_loop_never_saves_on_its_own():
    path = use_temp_notes_file()
    client = FakeClient([
        make_reply(tool_calls=[make_call("save_note", '{"title": "Idea", "text": "build an agent"}')]),
        make_reply(content="That note is waiting for your confirmation."),
    ])
    answer, log = agent.run_agent(client, [{"role": "user", "content": "save a note"}])
    assert log[0]["result"].startswith("NOT RUN")
    assert not os.path.exists(path), "the model alone must never be able to save"


def test_loop_stops_at_the_cap():
    client = FakeClient([make_reply(tool_calls=[make_call("list_notes", "{}")])])
    use_temp_notes_file()
    answer, log = agent.run_agent(client, [{"role": "user", "content": "loop"}])
    assert len(client.requests) == agent.MAX_ITERATIONS == 5
    assert answer == agent.CAP_MESSAGE
    assert len(log) == 5


# ---------------------------------------------------------------------------
# Runner, so `python test_tools.py` works without pytest
# ---------------------------------------------------------------------------

def main():
    real_notes_file = tools.NOTES_FILE
    tests = [(name, func) for name, func in sorted(globals().items()) if name.startswith("test_")]
    failed = 0
    for name, func in tests:
        try:
            func()
            print(f"PASS  {name}")
        except Exception as error:
            failed += 1
            print(f"FAIL  {name}: {type(error).__name__}: {error}")
    tools.NOTES_FILE = real_notes_file
    print(f"\n{len(tests) - failed} of {len(tests)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
