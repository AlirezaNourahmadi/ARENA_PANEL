import base64
import json
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from ..models import AccessKey, Node, User
from ..public_url import public_endpoint
from ..security import decrypt_payload
from .accounts import days_remaining


INFO_UUID = "00000000-0000-4000-8000-000000000000"


@dataclass(frozen=True)
class ProxyEndpoint:
    host: str
    port: int
    security: str
    sni: str
    websocket_host: str


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def human_bytes(value: int) -> str:
    if value <= 0:
        return "unlimited"
    gb = value / (1024**3)
    return f"{gb:.1f}".rstrip("0").rstrip(".") + " GB"


def info_profile(user: User) -> str:
    used = human_bytes(user.used_bytes)
    total = human_bytes(user.quota_bytes)
    days = days_remaining(user)
    days_text = "unlimited" if days is None else f"{days} days"
    label = quote(f"ARENA | {used}/{total} | {days_text}", safe="")
    return (
        f"vless://{INFO_UUID}@127.0.0.1:1"
        f"?encryption=none&security=none&type=tcp#{label}"
    )


def public_ws_path(node: Node, user: User) -> str:
    return f"{node.path.rstrip('/')}/{node.id}/{user.id}"


def _proxy_endpoint(node: Node, base_url: str | None) -> ProxyEndpoint:
    metadata = json.loads(node.metadata_json or "{}")
    adaptive = metadata.get("adaptive_endpoint", False) or node.host.lower() == "auto"
    if adaptive and base_url:
        origin = public_endpoint(base_url)
        return ProxyEndpoint(
            host=origin.host,
            port=origin.port,
            security=origin.security,
            sni=origin.host if origin.security == "tls" else "",
            websocket_host=origin.authority,
        )

    host = node.host
    return ProxyEndpoint(
        host=host,
        port=node.port,
        security=node.security,
        sni=node.sni or node.host,
        websocket_host=node.websocket_host or node.sni or node.host,
    )


def vless_uri(
    user: User, node: Node, key: AccessKey, base_url: str | None = None
) -> str:
    endpoint = _proxy_endpoint(node, base_url)
    params = {
        "encryption": "none",
        "security": endpoint.security,
        "type": "ws",
        "host": endpoint.websocket_host,
        "path": public_ws_path(node, user),
        "fp": node.fingerprint,
        "alpn": node.alpn,
    }
    if endpoint.security == "tls":
        params["sni"] = endpoint.sni
    label = quote(f"ARENA - {user.name} - {node.name}", safe="")
    uri_host = (
        f"[{endpoint.host}]"
        if ":" in endpoint.host and not endpoint.host.startswith("[")
        else endpoint.host
    )
    return (
        f"vless://{key.credential}@{uri_host}:{endpoint.port}"
        f"?{urlencode(params)}#{label}"
    )


def vmess_uri(
    user: User, node: Node, key: AccessKey, base_url: str | None = None
) -> str:
    endpoint = _proxy_endpoint(node, base_url)
    payload = {
        "v": "2",
        "ps": f"ARENA - {user.name} - {node.name}",
        "add": endpoint.host,
        "port": str(endpoint.port),
        "id": key.credential,
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": endpoint.websocket_host,
        "path": public_ws_path(node, user),
        "tls": "tls" if endpoint.security == "tls" else "",
        "sni": endpoint.sni,
        "alpn": node.alpn,
        "fp": node.fingerprint,
    }
    return "vmess://" + _b64(json.dumps(payload, ensure_ascii=False).encode())


def proxy_uri(
    user: User, node: Node, key: AccessKey, base_url: str | None = None
) -> str | None:
    if not node.enabled or not key.enabled:
        return None
    if node.protocol == "vless":
        return vless_uri(user, node, key, base_url)
    if node.protocol == "vmess":
        return vmess_uri(user, node, key, base_url)
    return None


def subscription_document(
    user: User, keys: list[AccessKey], base_url: str | None = None
) -> str:
    links = [info_profile(user)]
    links.extend(
        uri
        for key in keys
        if (uri := proxy_uri(user, key.node, key, base_url)) is not None
    )
    return "\n".join(links) + "\n"


def hiddify_deep_link(subscription_url: str, user_name: str) -> str:
    return f"hiddify://import/{quote(subscription_url, safe='')}#{quote('ARENA - ' + user_name, safe='')}"


def wireguard_profile(user: User, node: Node, key: AccessKey) -> str:
    metadata = json.loads(node.metadata_json or "{}")
    secret = decrypt_payload(key.secret_payload)
    if not secret.get("private_key") or not metadata.get("server_public_key"):
        raise ValueError("WireGuard node is missing key material")
    lines = [
        "[Interface]",
        f"PrivateKey = {secret['private_key']}",
        f"Address = {secret['address']}",
        f"DNS = {metadata.get('dns', '1.1.1.1')}",
        "",
        "[Peer]",
        f"PublicKey = {metadata['server_public_key']}",
    ]
    if metadata.get("preshared_key"):
        lines.append(f"PresharedKey = {metadata['preshared_key']}")
    lines.extend(
        [
            f"AllowedIPs = {metadata.get('allowed_ips', '0.0.0.0/0, ::/0')}",
            f"Endpoint = {node.host}:{node.port}",
            f"PersistentKeepalive = {metadata.get('persistent_keepalive', 25)}",
            "",
            f"# ARENA user: {user.name}",
        ]
    )
    return "\n".join(lines) + "\n"


def cisco_profile_xml(user: User, node: Node, key: AccessKey) -> str:
    secret = decrypt_payload(key.secret_payload)
    metadata = json.loads(node.metadata_json or "{}")
    group = metadata.get("group", "ARENA")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<AnyConnectProfile xmlns="http://schemas.xmlsoap.org/encoding/">
  <ClientInitialization><UseStartBeforeLogon UserControllable="true">false</UseStartBeforeLogon></ClientInitialization>
  <ServerList><HostEntry><HostName>ARENA - {user.name}</HostName><HostAddress>{node.host}</HostAddress><UserGroup>{group}</UserGroup></HostEntry></ServerList>
  <!-- Username: {secret.get("username", key.credential)} -->
</AnyConnectProfile>
'''


def cisco_credentials(node: Node, key: AccessKey) -> dict:
    secret = decrypt_payload(key.secret_payload)
    return {
        "server": f"https://{node.host}:{node.port}",
        "username": secret.get("username", key.credential),
        "password": secret.get("password", ""),
    }
