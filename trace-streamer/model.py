from dataclasses import dataclass, field
from typing import Any, Optional

from utils import coerce_int_fields, parse_json_field, parse_timestamp_unix_nano

# Attributes the source data stores as strings but which OTel semantic
# conventions (or our own numeric attrs) define as integers. Jaeger and other
# backends can't compare/aggregate on string-typed tags, so these must be
# coerced to int before export.
INTEGER_ATTRIBUTE_KEYS = frozenset(
    {
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.cache_read.input_tokens",
        "gen_ai.usage.cache_creation.input_tokens",
        "gen_ai.request.max_tokens",
        "evenup.agent.turn",
    }
)


@dataclass
class SpanEvent:
    name: str
    time_unix_nano: int
    attributes: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name"),
            time_unix_nano=parse_timestamp_unix_nano(
                data.get("time_unix_nano") or data.get("time") or data.get("timestamp")
            ),
            attributes=parse_json_field(data.get("attributes")),
        )


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    kind: int
    start_time_unix_nano: int
    end_time_unix_nano: int
    status_code: int
    status_message: Optional[str] = None
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    resource_attributes: dict = field(default_factory=dict)

    @property
    def duration_nano(self) -> int:
        return self.end_time_unix_nano - self.start_time_unix_nano

    @classmethod
    def from_dict(cls, data: dict) -> "Span":
        return cls(
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            parent_span_id=data.get("parent_span_id") or None,
            name=data.get("name"),
            kind=int(data.get("kind") or 0),
            start_time_unix_nano=parse_timestamp_unix_nano(data.get("start_time")),
            end_time_unix_nano=parse_timestamp_unix_nano(data.get("end_time")),
            status_code=int(data.get("status_code") or 0),
            status_message=data.get("status_message"),
            attributes=coerce_int_fields(parse_json_field(data.get("attributes")), INTEGER_ATTRIBUTE_KEYS),
            events=[SpanEvent.from_dict(e) for e in (data.get("events") or [])],
            resource_attributes=parse_json_field(data.get("resource_attributes")),
        )
