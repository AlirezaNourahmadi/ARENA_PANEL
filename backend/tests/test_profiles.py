import json
from urllib.parse import parse_qs, urlsplit

from backend.app.models import AccessKey, Node, User
from backend.app.security import encrypt_payload
from backend.app.services.profiles import cisco_credentials, vless_uri, wireguard_profile


def test_wireguard_profile_contains_required_peer_fields():
    user = User(name="Wire User")
    node = Node(
        name="WG",
        slug="wg-test",
        kind="wireguard",
        protocol="wireguard",
        transport="external",
        host="wg.example.test",
        port=51820,
        metadata_json=json.dumps(
            {
                "server_public_key": "server-public-key",
                "dns": "1.1.1.1",
                "allowed_ips": "0.0.0.0/0",
            }
        ),
    )
    key = AccessKey(
        credential="client-public-key",
        secret_payload=encrypt_payload(
            {"private_key": "client-private-key", "address": "10.66.0.2/24"}
        ),
    )
    output = wireguard_profile(user, node, key)
    assert "PrivateKey = client-private-key" in output
    assert "PublicKey = server-public-key" in output
    assert "Endpoint = wg.example.test:51820" in output


def test_cisco_credentials_are_decrypted_for_admin_export():
    node = Node(name="Cisco", slug="cisco-test", host="vpn.example.test", port=443)
    key = AccessKey(
        credential="arena-user",
        secret_payload=encrypt_payload({"username": "arena-user", "password": "secret"}),
    )
    assert cisco_credentials(node, key) == {
        "server": "https://vpn.example.test:443",
        "username": "arena-user",
        "password": "secret",
    }


def test_reality_profile_uses_adaptive_host_and_xray_parameters():
    user = User(id="user-id", name="Reality User")
    node = Node(
        id="node-id",
        name="ARENA Reality",
        slug="arena-reality",
        protocol="vless",
        transport="tcp",
        security="reality",
        host="auto",
        port=2053,
        sni="www.google.com",
        fingerprint="chrome",
        metadata_json=json.dumps(
            {
                "adaptive_endpoint": True,
                "public_key": "public-key",
                "short_id": "0123456789abcdef",
                "flow": "xtls-rprx-vision",
                "spider_x": "/",
            }
        ),
    )
    key = AccessKey(credential="33333333-3333-4333-8333-333333333333")

    uri = vless_uri(user, node, key, "https://panel.example.com")
    parsed = urlsplit(uri)
    params = parse_qs(parsed.query)
    assert parsed.hostname == "panel.example.com"
    assert parsed.port == 2053
    assert params["security"] == ["reality"]
    assert params["type"] == ["tcp"]
    assert params["sni"] == ["www.google.com"]
    assert params["pbk"] == ["public-key"]
    assert params["sid"] == ["0123456789abcdef"]
    assert params["flow"] == ["xtls-rprx-vision"]
