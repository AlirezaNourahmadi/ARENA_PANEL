from sqlalchemy import select

from backend.app.database import Base, SessionLocal, engine
from backend.app.models import AccessKey, ConnectionSession, Node, User
from backend.app.xray import XrayClient, XrayRuntime


def test_xray_config_has_separate_websocket_inbounds_and_stats():
    user = User(id="user", name="Test", active=True)
    vless_node = Node(id="vless", name="VLESS", slug="vless", protocol="vless", host="proxy")
    vmess_node = Node(id="vmess", name="VMess", slug="vmess", protocol="vmess", host="proxy")
    keys = [
        AccessKey(user=user, node=vless_node, credential="11111111-1111-4111-8111-111111111111"),
        AccessKey(user=user, node=vmess_node, credential="22222222-2222-4222-8222-222222222222"),
    ]
    config = XrayRuntime().build_config(keys)
    assert config["stats"] == {}
    assert config["api"]["services"] == ["HandlerService", "StatsService", "RoutingService"]
    assert [inbound["port"] for inbound in config["inbounds"]] == [10085, 11000, 11001]
    assert config["policy"]["levels"]["0"]["statsUserOnline"] is True
    assert config["inbounds"][1]["settings"]["decryption"] == "none"
    assert config["inbounds"][1]["streamSettings"]["wsSettings"]["path"] == "/internal/vless"
    assert config["inbounds"][2]["protocol"] == "vmess"
    assert config["routing"]["rules"][0]["outboundTag"] == "api"


def test_xray_config_adds_reality_inbound_with_isolated_user_stats():
    user = User(id="user", name="Test", active=True)
    node = Node(
        id="reality",
        name="REALITY",
        slug="reality",
        protocol="vless",
        transport="tcp",
        security="reality",
        host="auto",
        enabled=True,
    )
    key = AccessKey(
        user=user,
        node=node,
        user_id=user.id,
        node_id=node.id,
        credential="33333333-3333-4333-8333-333333333333",
        enabled=True,
    )
    runtime = XrayRuntime()
    runtime.settings = runtime.settings.model_copy(
        update={
            "xray_reality_enabled": True,
            "xray_reality_private_key": "private-key",
            "xray_reality_public_key": "public-key",
            "xray_reality_short_id": "0123456789abcdef",
            "xray_reality_server_name": "www.google.com",
            "xray_reality_target": "www.google.com:443",
        }
    )

    config = runtime.build_config([key])
    reality = next(item for item in config["inbounds"] if item["tag"] == "arena-vless-reality")
    assert reality["port"] == 12000
    assert reality["settings"]["clients"][0]["flow"] == "xtls-rprx-vision"
    assert reality["settings"]["clients"][0]["email"].endswith("@reality.arena")
    assert reality["streamSettings"]["realitySettings"]["target"] == "www.google.com:443"


def test_xray_stats_parsers():
    traffic = XrayRuntime.parse_user_stats(
        '{"stat":['
        '{"name":"user>>>id@reality.arena>>>traffic>>>uplink","value":12},'
        '{"name":"user>>>id@reality.arena>>>traffic>>>downlink","value":34}'
        ']}'
    )
    assert traffic == {"id@reality.arena": {"uplink": 12, "downlink": 34}}
    assert XrayRuntime.parse_online_users(
        '{"users":["user>>>id@reality.arena>>>online"]}'
    ) == ["id@reality.arena"]
    assert XrayRuntime.parse_online_ips('{"ips":{"203.0.113.7":1789380000}}') == {
        "203.0.113.7": 1789380000
    }


def test_reality_stats_are_persisted_with_trace_session():
    Base.metadata.create_all(engine)
    user_id = "reality-accounting-user"
    node_id = "reality-accounting-node"
    with SessionLocal() as db:
        db.add(User(id=user_id, name="Reality Accounting", active=True, validity_days=7))
        db.add(
            Node(
                id=node_id,
                name="Reality Accounting",
                slug="reality-accounting-node",
                protocol="vless",
                transport="tcp",
                security="reality",
                host="auto",
            )
        )
        db.commit()

    client = XrayClient(
        protocol="vless",
        credential="44444444-4444-4444-8444-444444444444",
        user_id=user_id,
        node_id=node_id,
        channel="reality",
    )
    XrayRuntime._persist_reality_state(
        {client.email: client},
        {client.email: {"uplink": 100, "downlink": 900}},
        {client.email: {"203.0.113.9": 1789380000}},
    )

    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert user.used_up_bytes == 100
        assert user.used_down_bytes == 900
        assert user.starts_at is not None
        session = db.scalar(
            select(ConnectionSession).where(
                ConnectionSession.user_id == user_id,
                ConnectionSession.source_ip == "203.0.113.9",
            )
        )
        assert session is not None
        assert session.gateway_instance == "xray-reality"
        assert session.downlink_bytes == 900
