from app.ai.metrics import InferenceMetrics
from app.ai.providers import GenerationResult, ModelProvider
from app.config import Settings
from app.design.prompt import build_revision_messages
from app.design.schema import DesignSpec
from app.design.validator import generate_spec, revise_spec


METRICS = InferenceMetrics("stub", "stub", "cpu", "float32", 0, 0, 0, 0, 0)


class QueueProvider(ModelProvider):
    name = "queue"

    def __init__(self, replies):
        super().__init__(Settings(device="cpu"))
        self.replies = iter(replies)
        self.messages = []

    def _generate(self, messages):
        self.messages.append(messages)
        return GenerationResult(next(self.replies), METRICS)


BASE = '{"schema_version":"2.0","unit":"mm","name":"block","parts":[{"id":"body","primitive":"box","dimensions":{"x":100,"y":80,"z":40},"position":{"x":0,"y":0,"z":0}}],"operations":[]}'


def test_validation_retry_sends_failure_reason_back_to_model():
    provider = QueueProvider(["not json", BASE])
    result = generate_spec(provider, "블록", max_attempts=2)
    assert result.attempt_count == 2
    assert "JSON 객체를 찾지 못했습니다" in provider.messages[1][-1]["content"]


def test_revision_prompt_contains_full_current_spec_and_preservation_rule():
    current = generate_spec(QueueProvider([BASE]), "블록").spec
    messages = build_revision_messages(current, "폭만 120mm로 바꿔줘")
    content = messages[-1]["content"]
    assert '"y":80.0' in content
    assert "그대로 유지" in content


def test_revision_preserves_every_unmentioned_field():
    current = generate_spec(QueueProvider([BASE]), "블록").spec
    changed = BASE.replace('"x":100', '"x":120')
    revised = revise_spec(QueueProvider([changed]), current, "폭만 120mm로 바꿔줘").spec
    before = current.model_dump()
    after = revised.model_dump()
    assert after["parts"][0]["dimensions"]["x"] == 120
    before["parts"][0]["dimensions"]["x"] = 120
    assert after == before


def test_revision_expands_top_to_cover_all_legs_without_llm():
    current = DesignSpec.model_validate(
        {
            "schema_version": "2.0",
            "unit": "mm",
            "name": "desk",
            "parts": [
                {
                    "id": "top",
                    "primitive": "box",
                    "dimensions": {"x": 1200, "y": 600, "z": 25},
                    "position": {"x": 0, "y": 0, "z": 750},
                },
                *[
                    {
                        "id": f"leg_{index}",
                        "primitive": "box",
                        "dimensions": {"x": 400, "y": 400, "z": 750},
                        "position": {"x": x, "y": y, "z": 0},
                    }
                    for index, (x, y) in enumerate(
                        [(-600, -300), (600, -300), (-600, 300), (600, 300)],
                        start=1,
                    )
                ],
            ],
            "operations": [
                {
                    "type": "union",
                    "targets": ["top", "leg_1", "leg_2", "leg_3", "leg_4"],
                }
            ],
        }
    )
    provider = QueueProvider([])

    result = revise_spec(
        provider,
        current,
        "위에 판자가 다리를 다 덮어야지 지금 사이즈가 너무 작잖아얼마",
    )

    top = result.spec.parts[0]
    assert isinstance(top, type(current.parts[0]))
    assert top.dimensions.x == 1600
    assert top.dimensions.y == 1000
    assert result.metrics.provider == "rule"
    assert provider.messages == []
