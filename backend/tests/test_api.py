import base64

from fastapi.testclient import TestClient

from backend.app.main import app


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "arena-test-password"},
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": client.cookies["arena_csrf"]}


def test_user_subscription_and_gateway_policy_flow():
    with TestClient(app) as client:
        headers = login(client)
        nodes = client.get("/api/nodes", headers=headers).json()
        assert {node["protocol"] for node in nodes} == {"vless", "vmess"}

        created = client.post(
            "/api/users",
            headers=headers,
            json={
                "name": "Phase One",
                "quota_gb": 1,
                "validity_days": 14,
                "max_ips": 1,
                "speed_mbps": 8,
                "node_ids": [node["id"] for node in nodes],
            },
        )
        assert created.status_code == 201, created.text
        user = created.json()
        assert user["starts_at"] is None
        assert user["speed_limit_bps"] == 1_000_000

        subscription = client.get(user["subscription_url"])
        assert subscription.status_code == 200
        assert "upload=0; download=0; total=1073741824; expire=0" == subscription.headers["subscription-userinfo"]
        document = base64.b64decode(subscription.text).decode()
        lines = document.strip().splitlines()
        assert lines[0].startswith("vless://00000000-0000-4000-8000-000000000000@127.0.0.1:1")
        assert any(line.startswith("vless://") and "@testserver:80" in line for line in lines[1:])
        assert any(line.startswith("vmess://") for line in lines[1:])

        vless = next(node for node in nodes if node["protocol"] == "vless")
        gateway_headers = {"X-Arena-Gateway": "test-gateway-secret-123456789"}
        first = client.post(
            "/api/internal/gateway/authorize",
            headers=gateway_headers,
            json={"user_id": user["id"], "node_id": vless["id"], "source_ip": "203.0.113.10"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["speed_limit_bps"] == 1_000_000
        assert first.json()["upstream_url"].endswith(":11000/internal/vless")

        same_ip = client.post(
            "/api/internal/gateway/authorize",
            headers=gateway_headers,
            json={"user_id": user["id"], "node_id": vless["id"], "source_ip": "203.0.113.10"},
        )
        assert same_ip.status_code == 200
        other_ip = client.post(
            "/api/internal/gateway/authorize",
            headers=gateway_headers,
            json={"user_id": user["id"], "node_id": vless["id"], "source_ip": "203.0.113.11"},
        )
        assert other_ip.status_code == 429

        heartbeat = client.post(
            "/api/internal/gateway/heartbeat",
            headers=gateway_headers,
            json={"session_id": first.json()["session_id"], "uplink_delta": 120, "downlink_delta": 880},
        )
        assert heartbeat.status_code == 200
        current = client.get(f"/api/users/{user['id']}", headers=headers).json()
        assert current["used_bytes"] == 1000
        assert current["starts_at"] is not None


def test_csrf_and_subscription_rotation():
    with TestClient(app) as client:
        headers = login(client)
        denied = client.post("/api/users", json={"name": "No CSRF"})
        assert denied.status_code == 403

        created = client.post("/api/users", headers=headers, json={"name": "Rotated"}).json()
        old_url = created["subscription_url"]
        rotated = client.post(
            f"/api/users/{created['id']}/rotate-subscription", headers=headers
        ).json()
        assert rotated["subscription_url"] != old_url
        assert client.get(old_url).status_code == 404
        assert client.get(rotated["subscription_url"]).status_code == 200


def test_subscription_adapts_to_forwarded_public_origin():
    with TestClient(app) as client:
        headers = login(client)
        public_headers = {
            **headers,
            "host": "internal.service:8000",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "panel.example.com",
        }
        nodes = client.get("/api/nodes", headers=public_headers).json()
        created = client.post(
            "/api/users",
            headers=public_headers,
            json={"name": "Adaptive", "node_ids": [node["id"] for node in nodes]},
        )
        assert created.status_code == 201, created.text
        user = created.json()
        assert user["subscription_url"].startswith("https://panel.example.com/sub/")

        formats = client.get(
            f"/api/users/{user['id']}/formats", headers=public_headers
        ).json()
        assert formats["subscription_url"] == user["subscription_url"]
        vless = next(link for link in formats["direct_links"] if link.startswith("vless://"))
        assert "@panel.example.com:443" in vless
        assert "security=tls" in vless
        assert "host=panel.example.com" in vless
        assert "sni=panel.example.com" in vless

        subscription = client.get(user["subscription_url"], headers=public_headers)
        document = base64.b64decode(subscription.text).decode()
        assert "@panel.example.com:443" in document

        alternate_headers = {
            **headers,
            "x-forwarded-proto": "https",
            "x-forwarded-host": "edge.example.net:8443",
        }
        alternate = client.get(
            f"/api/users/{user['id']}/formats", headers=alternate_headers
        ).json()
        alternate_vless = next(
            link for link in alternate["direct_links"] if link.startswith("vless://")
        )
        assert alternate["subscription_url"].startswith(
            "https://edge.example.net:8443/sub/"
        )
        assert "@edge.example.net:8443" in alternate_vless
        assert "host=edge.example.net%3A8443" in alternate_vless
        assert "sni=edge.example.net" in alternate_vless
