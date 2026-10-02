from types import SimpleNamespace as NS

import pytest

import hello_support
from hello_support.cli import main
from hello_support.config import Settings
from hello_support.llm import LLMClient

SETTINGS = Settings("http://x/v1", "slm-id", "large-id", "large", 5.0)


class FakeCompletions:
    def __init__(self, arguments: str):
        self.arguments = arguments
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        call = NS(id="c1", function=NS(name="get_time", arguments=self.arguments))
        msg = NS(content=None, tool_calls=[call])
        return NS(model=kwargs["model"], choices=[NS(message=msg, finish_reason="tool_calls")],
                  usage=NS(prompt_tokens=12, completion_tokens=7))


def fake_client(arguments: str):
    comp = FakeCompletions(arguments)
    return NS(chat=NS(completions=comp)), comp


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert hello_support.__version__ in capsys.readouterr().out


def test_resolve_model_aliases():
    assert SETTINGS.resolve_model("slm") == "slm-id"
    assert SETTINGS.resolve_model(None) == "large-id"
    assert SETTINGS.resolve_model("other/model") == "other/model"


def test_chat_normalizes_tool_calls_and_usage():
    client, comp = fake_client('{"timezone": "Europe/Brussels"}')
    r = LLMClient(SETTINGS, client).chat("m", [{"role": "user", "content": "hi"}], tools=[{"x": 1}])
    assert comp.last_kwargs["tools"] == [{"x": 1}]
    assert r.tool_calls[0].name == "get_time"
    assert r.tool_calls[0].arguments == {"timezone": "Europe/Brussels"}
    assert (r.prompt_tokens, r.completion_tokens) == (12, 7)
    assert r.latency_s >= 0


def test_chat_keeps_invalid_json_arguments_as_none():
    client, _ = fake_client("{not json")
    r = LLMClient(SETTINGS, client).chat("m", [])
    assert r.tool_calls[0].arguments is None
    assert r.tool_calls[0].raw_arguments == "{not json"
