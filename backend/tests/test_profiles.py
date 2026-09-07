import json

from backend.app.models import AccessKey, Node, User
from backend.app.security import encrypt_payload
from backend.app.services.profiles import cisco_credentials, wireguard_profile


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
