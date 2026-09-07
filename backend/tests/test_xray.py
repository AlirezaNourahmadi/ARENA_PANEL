from backend.app.models import AccessKey, Node, User
from backend.app.xray import XrayRuntime


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
    assert config["api"]["services"] == ["HandlerService", "StatsService"]
    assert [inbound["port"] for inbound in config["inbounds"]] == [10085, 11000, 11001]
    assert config["inbounds"][1]["settings"]["decryption"] == "none"
    assert config["inbounds"][1]["streamSettings"]["wsSettings"]["path"] == "/internal/vless"
    assert config["inbounds"][2]["protocol"] == "vmess"
    assert config["routing"]["rules"][0]["outboundTag"] == "api"
