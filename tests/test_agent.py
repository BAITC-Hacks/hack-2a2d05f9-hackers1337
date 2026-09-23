from __future__ import annotations

import json

from org_audit.agent import OpenAIProvider, analyze_documents
from org_audit.models import Fragment


BEFORE = Fragment("F-BEFORE", "ДО", "before.txt", "текст, строка 1", "Отдел эксплуатации ежедневно проверяет резервное оборудование.", "Отдел эксплуатации")
AFTER = Fragment("F-AFTER", "ПОСЛЕ", "after.txt", "текст, строка 2", "Служба эксплуатации осматривает резервное оборудование каждый день.", "Служба эксплуатации")


class FakeFunctionCall:
    type = "function_call"

    def __init__(self, name: str, arguments: dict, call_id: str):
        self.name = name
        self.arguments = json.dumps(arguments, ensure_ascii=False)
        self.call_id = call_id

    def model_dump(self, exclude_none=True):
        return {
            "type": self.type,
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id,
        }


class FakeResponse:
    def __init__(self, output=None, output_text=""):
        self.output = output or []
        self.output_text = output_text


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        call_number = len(self.calls)
        if call_number == 1:
            return FakeResponse(
                [FakeFunctionCall("search_fragments", {"query": "резервное оборудование", "side": "ДО", "limit": 2}, "call-1")]
            )
        if call_number == 2:
            return FakeResponse(
                output_text=json.dumps(
                    {
                        "before_functions": [
                            {"function": "Проверка резервного оборудования", "unit": "", "evidence_ids": [BEFORE.id]}
                        ],
                        "after_functions": [
                            {"function": "Проверка резервного оборудования", "unit": "", "evidence_ids": [AFTER.id]}
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        if call_number == 3:
            return FakeResponse(
                [FakeFunctionCall("read_fragment", {"fragment_id": AFTER.id}, "call-2")]
            )
        return FakeResponse(
            output_text=json.dumps(
                {
                    "findings": [
                        {
                            "category": "preserved",
                            "function": "Ежедневная проверка резервного оборудования",
                            "explanation": "Формулировка различается, действие и объект совпадают.",
                            "recommendation": "Подтвердить, что периодичность и ответственность не изменились.",
                            "before_evidence_ids": [BEFORE.id],
                            "after_evidence_ids": [AFTER.id],
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_responses_agent_uses_only_safe_tools_and_validates_tool_evidence():
    client = FakeClient()
    events = []
    provider = OpenAIProvider(api_key="mock-only", model="test-model", client=client)
    result = analyze_documents(provider, [BEFORE, AFTER], on_event=events.append)

    assert not result.partial
    assert len(result.findings) == 1
    assert result.findings[0].before_evidence[0].id == BEFORE.id
    assert result.findings[0].after_evidence[0].id == AFTER.id
    assert any("search_fragments" in event for event in events)
    assert any("read_fragment" in event for event in events)
    assert len(client.responses.calls) == 4
    for call in client.responses.calls:
        assert call["store"] is False
        assert {tool["name"] for tool in call["tools"]} == {"search_fragments", "read_fragment"}

