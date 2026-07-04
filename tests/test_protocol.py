"""Protocol parsing tests."""

from bifrost_plugin.ib_gateway.protocol import parse_stream_fields


def test_parse_ping_command() -> None:
    msg, err = parse_stream_fields(
        {
            "req_id": "abc-123",
            "v": "1",
            "op": "ping",
            "payload": "{}",
            "caller": "test",
        },
        stream_id="1-0",
    )
    assert err is None
    assert msg is not None
    assert msg.op == "ping"
    assert msg.req_id == "abc-123"


def test_parse_unknown_op() -> None:
    msg, err = parse_stream_fields(
        {"req_id": "x", "v": "1", "op": "not_real", "payload": "{}"},
        stream_id="2-0",
    )
    assert msg is None
    assert err is not None
