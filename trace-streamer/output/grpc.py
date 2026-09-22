import grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from utils import group_by

# Standard grpc/OTLP collector default; override via config.OUTPUT_GRPC_MAX_MESSAGE_SIZE
# to match the actual collector's configured limit.
DEFAULT_MAX_MESSAGE_SIZE = 4 * 1024 * 1024


def _to_any_value(value):
    if isinstance(value, bool):
        return common_pb2.AnyValue(bool_value=value)
    if isinstance(value, int):
        return common_pb2.AnyValue(int_value=value)
    if isinstance(value, float):
        return common_pb2.AnyValue(double_value=value)
    if isinstance(value, dict):
        return common_pb2.AnyValue(kvlist_value=_to_key_value_list(value))
    if isinstance(value, (list, tuple)):
        return common_pb2.AnyValue(
            array_value=common_pb2.ArrayValue(values=[_to_any_value(v) for v in value])
        )
    return common_pb2.AnyValue(string_value=str(value))


def _to_key_values(attributes):
    return [common_pb2.KeyValue(key=k, value=_to_any_value(v)) for k, v in (attributes or {}).items()]


def _to_key_value_list(attributes):
    return common_pb2.KeyValueList(values=_to_key_values(attributes))


def _to_pb_event(event):
    return trace_pb2.Span.Event(
        name=event.name,
        time_unix_nano=event.time_unix_nano,
        attributes=_to_key_values(event.attributes),
    )


def _to_pb_span(span):
    pb_span = trace_pb2.Span(
        trace_id=bytes.fromhex(span.trace_id),
        span_id=bytes.fromhex(span.span_id),
        name=span.name,
        kind=span.kind,
        start_time_unix_nano=span.start_time_unix_nano,
        end_time_unix_nano=span.end_time_unix_nano,
        attributes=_to_key_values(span.attributes),
        events=[_to_pb_event(e) for e in span.events],
        status=trace_pb2.Status(
            code=span.status_code,
            message=span.status_message or "",
        ),
    )
    if span.parent_span_id:
        pb_span.parent_span_id = bytes.fromhex(span.parent_span_id)
    return pb_span


def _build_request(spans):
    resource_groups = group_by(spans, lambda s: tuple(sorted(s.resource_attributes.items())))
    resource_spans = [
        trace_pb2.ResourceSpans(
            resource=resource_pb2.Resource(attributes=_to_key_values(dict(resource_key))),
            scope_spans=[
                trace_pb2.ScopeSpans(
                    scope=common_pb2.InstrumentationScope(name="trace-streamer"),
                    spans=[_to_pb_span(s) for s in resource_spans_group],
                )
            ],
        )
        for resource_key, resource_spans_group in resource_groups.items()
    ]
    return trace_service_pb2.ExportTraceServiceRequest(resource_spans=resource_spans)


class GrpcOutput:
    def __init__(self, endpoint, insecure=True, timeout=10, max_message_size=None):
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_message_size = max_message_size or DEFAULT_MAX_MESSAGE_SIZE
        channel_options = [
            ("grpc.max_send_message_length", self.max_message_size),
            ("grpc.max_receive_message_length", self.max_message_size),
        ]
        self.channel = (
            grpc.insecure_channel(endpoint, options=channel_options)
            if insecure
            else grpc.secure_channel(endpoint, grpc.ssl_channel_credentials(), options=channel_options)
        )
        self.stub = trace_service_pb2_grpc.TraceServiceStub(self.channel)

    def send(self, spans):
        for span in spans:
            request = _build_request([span])
            try:
                resp = self.stub.Export(request, timeout=self.timeout)
                if resp.partial_success.rejected_spans:
                    print(
                        "rejected:",
                        span.span_id,
                        resp.partial_success.rejected_spans,
                        resp.partial_success.error_message,
                    )
                else:
                    print(f"accepted span {span.span_id}")
            except grpc.RpcError as e:
                print(span.span_id, e.code(), e.details())

    def close(self):
        self.channel.close()
