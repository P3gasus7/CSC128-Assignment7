# Author: Shawn Canady
"""agent.py - the tool calling loop.

How the loop works:
    1. Send the conversation and the tool schemas to the model.
    2. If the model asks for no tools, that is the final answer. Stop.
    3. Otherwise run each tool with dispatch(), add the results to the
       conversation, and go around again.
    4. Stop after MAX_ITERATIONS rounds no matter what, so the model
       cannot loop forever and use up the rate limit.
"""

from tools import TOOL_SCHEMAS, dispatch

MODEL = "openai/gpt-oss-120b"  # supports tool calling; replaces llama-3.3-70b-versatile, retired by Groq on 2026-08-16
MAX_ITERATIONS = 5

SYSTEM_PROMPT = (
    "You are a helpful assistant with three tools: calculate, list_notes, and "
    "save_note. Use a tool whenever the question needs one, and never guess at "
    "math or at what notes exist. Saving a note needs the user's approval, and "
    "until they approve it the note is not saved, so say it is waiting for "
    "confirmation rather than saying it is saved. If a tool returns an error, "
    "explain the problem to the user plainly. If the user asks for something "
    "you have no tool for, such as deleting or editing a note, say that you "
    "cannot do it."
)

CAP_MESSAGE = (
    "I stopped because I reached the limit of tool-calling rounds without "
    "finishing. Please try a simpler request."
)


def run_agent(client, messages):
    """Let the model call tools until it gives a final answer.

    client:   a Groq client (or a fake one in the tests)
    messages: the chat so far, a list of {"role": ..., "content": ...}

    Returns (answer, tool_log). tool_log has one entry for every tool call:
    the round number, the tool name, the arguments, and the result.
    """
    # Copy the list so the caller's list is not changed, then add the system prompt.
    convo = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)
    tool_log = []

    for round_number in range(1, MAX_ITERATIONS + 1):  # the hard cap
        response = client.chat.completions.create(
            model=MODEL,
            messages=convo,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        message = response.choices[0].message

        # No tool requested means the model is done.
        if not message.tool_calls:
            return message.content or "", tool_log

        # Save the assistant message that asked for the tools.
        requested = []
        for call in message.tool_calls:
            requested.append({
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            })
        convo.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": requested,
        })

        # Run each tool and send its result back to the model.
        for call in message.tool_calls:
            name = call.function.name
            arguments = call.function.arguments
            result = dispatch(name, arguments)  # never confirmed here
            tool_log.append({
                "round": round_number,
                "tool": name,
                "arguments": arguments,
                "result": result,
            })
            convo.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    # We ran out of rounds while the model still wanted tools.
    return CAP_MESSAGE, tool_log
