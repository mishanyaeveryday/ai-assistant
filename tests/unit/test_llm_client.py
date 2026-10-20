import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from agent.tools_adapter import ToolsAdapter  # noqa: E402
from agent.tools_policy import ToolsApprovalPolicy  # noqa: E402


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def is_builtin_tool(self, name):
        return True

    async def get_tools(self):
        return []

    async def call_tool(self, name, args):
        self.calls.append(name)
        return SimpleNamespace(content=[])


# --- The tool loop ---

def tool_call(name="read_image", arguments="{}", **extra):
    from openai.types.chat import ChatCompletionMessage
    return ChatCompletionMessage.model_validate({
        "role": "assistant", "content": None, **extra,
        "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": name, "arguments": arguments}}]})


def text_reply(text):
    from openai.types.chat import ChatCompletionMessage
    return ChatCompletionMessage(role="assistant", content=text)


def run_ask(*replies, registry=None):
    """Asks once, with the model giving `replies` in turn and repeating the
    last one; a reply may be a function of the request's options. Returns the
    answer and the fake model, which keeps what each turn was sent."""
    from agent import orchestrator

    class FakeLLM:
        def __init__(self, llm_model, **kwargs):
            self.llm_model = llm_model
            self.sent = []
            self.options = []

        async def generate(self, messages, **kwargs):
            self.sent.append(list(messages))
            self.options.append(kwargs)
            reply = replies[min(len(self.sent), len(replies)) - 1]
            return reply(kwargs) if callable(reply) else reply

    with patch.object(orchestrator, "LLMClient", FakeLLM):
        client = orchestrator.AIClient(memory=[], mcp_registry=registry or FakeRegistry())
        answer = asyncio.run(client.ask("what is on the screen?"))
    return answer, client.llm


def test_tool_result_goes_back_with_the_call_and_its_reasoning():
    reasoning = [{"type": "reasoning.encrypted", "data": "sig", "format": "google-gemini-v1"}]

    answer, llm = run_ask(tool_call(reasoning_details=reasoning), text_reply("Done."))

    assistant, tool = llm.sent[1][-2:]
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert assistant["reasoning_details"] == reasoning
    assert tool == {"role": "tool", "tool_call_id": "call_1", "content": "(no output)"}
    assert answer == "Done."


def test_malformed_arguments_are_reported_to_the_model_not_run():
    registry = FakeRegistry()

    _, llm = run_ask(tool_call(arguments="{not json"), text_reply("Sorry."), registry=registry)

    assert registry.calls == []
    assert json.loads(llm.sent[1][-1]["content"])["ok"] is False


def test_running_out_of_rounds_still_ends_with_an_answer():
    from agent.orchestrator import MAX_TOOL_ROUNDS

    def model(options):
        if options.get("tool_choice") == "none":
            return text_reply("Here is what I found so far.")
        return tool_call()

    answer, llm = run_ask(model)

    assert answer == "Here is what I found so far."
    assert len(llm.sent) == MAX_TOOL_ROUNDS + 1
    # The final request carries every tool result, the last one included.
    assert llm.sent[-1][-1]["role"] == "tool"


def test_model_that_never_stops_calling_tools_gets_a_note_not_an_empty_answer():
    answer, _ = run_ask(tool_call())

    assert "Stopped after" in answer


def test_tools_are_declared_in_openai_format():
    adapter = ToolsAdapter(FakeRegistry(), ToolsApprovalPolicy())

    tools = adapter.mcp_tools_to_openai_tools([{"name": "make_screenshot", "description": "Shot"}])

    assert tools == [{"type": "function", "function": {
        "name": "make_screenshot", "description": "Shot",
        "parameters": {"type": "object", "properties": {}}}}]


def test_denied_call_is_not_run():
    async def deny(name, args):
        return False

    adapter = ToolsAdapter(FakeRegistry(), ToolsApprovalPolicy(), approve_tool=deny)

    reply = asyncio.run(adapter.call_and_format("click", {}))

    assert adapter.mcp_registry.calls == []
    assert json.loads(reply) == {"ok": False, "error": "User denied execution."}


# --- Today's date ---

def test_date_context_names_the_day_and_the_year_to_search_for():
    from agent.orchestrator import date_context

    text = date_context(datetime(2026, 10, 20, 14, 5, tzinfo=timezone(timedelta(hours=2))))

    assert "Tuesday, 20 October 2026, 14:05 (UTC+0200)" in text
    assert "use 2026" in text


def test_model_is_told_todays_date():
    _, llm = run_ask(text_reply("Hi."))

    system = llm.sent[0][0]
    assert system["role"] == "system"
    assert datetime.now().astimezone().strftime("%d %B %Y") in system["content"]


# --- Transient API errors ---

def make_llm(*outcomes, fallback_models=()):
    from core import llm_client

    client = llm_client.LLMClient.__new__(llm_client.LLMClient)
    client.llm_model = "test-model"
    client.fallback_models = list(fallback_models)
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, str):
            return SimpleNamespace(choices=[SimpleNamespace(message=outcome)])
        return outcome

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=create)))
    return client, calls


def api_error(error_class, status, headers=None):
    import httpx2
    request = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx2.Response(status, headers=headers or {}, request=request)
    return error_class(f"error {status}", response=response, body=None)


def overloaded():
    import openai
    return api_error(openai.InternalServerError, 503)


def generate(client):
    async def no_wait(_):
        pass

    with patch("core.llm_client.asyncio.sleep", no_wait):
        return asyncio.run(client.generate(messages=[], tools=None, temperature=0))


def test_overloaded_model_is_retried():
    client, calls = make_llm(overloaded(), overloaded(), "answer")

    assert generate(client) == "answer"
    assert len(calls) == 3


def test_retries_give_up_eventually():
    import openai
    from core.llm_client import RETRY_DELAYS_SECONDS

    attempts = len(RETRY_DELAYS_SECONDS) + 1
    client, calls = make_llm(*[overloaded() for _ in range(attempts)])

    try:
        generate(client)
        raise AssertionError("expected the error to surface")
    except openai.InternalServerError:
        pass
    assert len(calls) == attempts


def test_reply_without_choices_is_retried():
    client, calls = make_llm(SimpleNamespace(choices=[], error={"message": "provider error"}),
                             "answer")

    assert generate(client) == "answer"
    assert len(calls) == 2


def test_bad_request_is_not_retried():
    import openai

    client, calls = make_llm(api_error(openai.BadRequestError, 400))

    try:
        generate(client)
        raise AssertionError("expected the error to surface")
    except openai.BadRequestError:
        pass
    assert len(calls) == 1


def test_used_up_daily_quota_is_not_retried():
    import openai

    client, calls = make_llm(api_error(openai.RateLimitError, 429, {"retry-after": "59848"}))

    try:
        generate(client)
        raise AssertionError("expected the error to surface")
    except openai.RateLimitError:
        pass
    assert len(calls) == 1


def test_short_rate_limit_is_retried():
    import openai

    per_minute = api_error(openai.RateLimitError, 429, {"retry-after": "12"})
    client, calls = make_llm(per_minute, "answer")

    assert generate(client) == "answer"
    assert len(calls) == 2


def test_fallback_models_are_offered_to_openrouter():
    client, calls = make_llm("answer", fallback_models=["other-model"])

    generate(client)

    assert calls[0]["extra_body"] == {"models": ["test-model", "other-model"]}
    assert "tools" not in calls[0]


def test_tool_choice_is_sent_only_with_tools():
    tools = [{"type": "function", "function": {"name": "web_search"}}]
    client, calls = make_llm("answer", "answer")

    async def no_wait(_):
        pass

    async def scenario():
        await client.generate(messages=[], tools=tools, temperature=0, tool_choice="none")
        await client.generate(messages=[], tools=None, temperature=0, tool_choice="none")

    with patch("core.llm_client.asyncio.sleep", no_wait):
        asyncio.run(scenario())

    assert calls[0]["tool_choice"] == "none"
    assert "tool_choice" not in calls[1]
