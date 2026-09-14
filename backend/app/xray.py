import asyncio
import hashlib
import json
import logging
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .models import AccessKey, ConnectionSession, User
from .services.accounts import user_allowed
from .services.audit import audit


logger = logging.getLogger("arena.xray")


class XrayRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class XrayClient:
    protocol: str
    credential: str
    user_id: str
    node_id: str
    channel: str = "websocket"

    @property
    def inbound_tag(self) -> str:
        if self.channel == "reality":
            return "arena-vless-reality"
        return f"arena-{self.protocol}-ws"

    @property
    def email(self) -> str:
        if self.channel == "reality":
            return f"{self.credential}@reality.arena"
        return f"{self.credential}@{self.protocol}.arena"

    def payload(self) -> dict:
        payload = {"id": self.credential, "email": self.email, "level": 0}
        if self.channel == "reality":
            payload["flow"] = "xtls-rprx-vision"
        return payload


class XrayRuntime:
    """Own the Xray process and update inbound users without dropping live sessions."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._log_task: asyncio.Task | None = None
        self._stats_task: asyncio.Task | None = None
        self._clients: dict[tuple[str, str], XrayClient] = {}
        self._ip_limit_rule_tags: set[str] = set()
        self._allowed_reality_ips: dict[str, set[str]] = {}
        self.last_error = ""

    @property
    def api_address(self) -> str:
        return f"{self.settings.xray_api_host}:{self.settings.xray_api_port}"

    @property
    def running(self) -> bool:
        return bool(self.process and self.process.returncode is None)

    @staticmethod
    def _client_key(client: XrayClient) -> tuple[str, str]:
        return client.inbound_tag, client.credential

    def _clients_from_keys(self, keys: list[AccessKey]) -> dict[tuple[str, str], XrayClient]:
        clients: dict[tuple[str, str], XrayClient] = {}
        for key in keys:
            protocol = key.node.protocol
            allowed, _ = user_allowed(key.user)
            if (
                protocol not in {"vless", "vmess"}
                or not key.enabled
                or not key.node.enabled
                or not allowed
            ):
                continue
            if key.node.transport == "websocket":
                client = XrayClient(
                    protocol=protocol,
                    credential=key.credential,
                    user_id=key.user_id,
                    node_id=key.node_id,
                )
                clients[self._client_key(client)] = client
            elif (
                self.settings.xray_reality_enabled
                and protocol == "vless"
                and key.node.transport == "tcp"
                and key.node.security == "reality"
            ):
                client = XrayClient(
                    protocol=protocol,
                    credential=key.credential,
                    user_id=key.user_id,
                    node_id=key.node_id,
                    channel="reality",
                )
                clients[self._client_key(client)] = client
        return clients

    def build_config(self, keys: list[AccessKey]) -> dict:
        return self._build_config(list(self._clients_from_keys(keys).values()))

    def _build_config(self, clients: list[XrayClient]) -> dict:
        grouped = {
            tag: [client.payload() for client in clients if client.inbound_tag == tag]
            for tag in ("arena-vless-ws", "arena-vmess-ws", "arena-vless-reality")
        }

        def inbound(protocol: str, port: int) -> dict:
            protocol_settings: dict = {"clients": grouped[f"arena-{protocol}-ws"]}
            if protocol == "vless":
                protocol_settings["decryption"] = "none"
            return {
                "tag": f"arena-{protocol}-ws",
                "listen": self.settings.xray_listen_host,
                "port": port,
                "protocol": protocol,
                "settings": protocol_settings,
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": {
                        "path": f"/internal/{protocol}",
                        "acceptProxyProtocol": False,
                    },
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
            }

        inbounds = [
            {
                "tag": "api",
                "listen": self.settings.xray_api_host,
                "port": self.settings.xray_api_port,
                "protocol": "dokodemo-door",
                "settings": {"address": self.settings.xray_api_host},
            },
            inbound("vless", 11000),
            inbound("vmess", 11001),
        ]
        if self.settings.xray_reality_enabled:
            inbounds.append(self._reality_inbound(grouped["arena-vless-reality"]))

        return {
            "log": {"loglevel": "warning"},
            "api": {
                "tag": "api",
                "services": ["HandlerService", "StatsService", "RoutingService"],
            },
            "policy": {
                "levels": {
                    "0": {
                        "statsUserUplink": True,
                        "statsUserDownlink": True,
                        "statsUserOnline": True,
                    }
                },
                "system": {"statsInboundUplink": True, "statsInboundDownlink": True},
            },
            "stats": {},
            "inbounds": inbounds,
            "outbounds": [
                {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}},
                {"tag": "blocked", "protocol": "blackhole"},
            ],
            "routing": {
                "domainStrategy": "AsIs",
                "rules": [
                    {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
                ],
            },
        }

    def _reality_inbound(self, clients: list[dict]) -> dict:
        return {
            "tag": "arena-vless-reality",
            "listen": self.settings.xray_listen_host,
            "port": self.settings.xray_reality_listen_port,
            "protocol": "vless",
            "settings": {"clients": clients, "decryption": "none"},
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "target": self.settings.xray_reality_target,
                    "xver": 0,
                    "serverNames": [self.settings.xray_reality_server_name],
                    "privateKey": self.settings.xray_reality_private_key,
                    "shortIds": [self.settings.xray_reality_short_id],
                    "minClientVer": "0.0.0",
                },
            },
            "sniffing": {
                "enabled": True,
                "destOverride": ["http", "tls", "quic"],
                "routeOnly": True,
            },
        }

    def _load_keys(self, db: Session) -> list[AccessKey]:
        return list(
            db.scalars(
                select(AccessKey).options(joinedload(AccessKey.user), joinedload(AccessKey.node))
            ).unique()
        )

    async def start(self, db: Session) -> None:
        if not self.settings.xray_enabled:
            logger.warning("Xray runtime is disabled")
            return
        desired = self._clients_from_keys(self._load_keys(db))
        async with self._lock:
            await self._start_locked(desired)
        if self.settings.xray_reality_enabled and self._stats_task is None:
            self._stats_task = asyncio.create_task(self._stats_loop())

    async def reconcile(self, db: Session) -> None:
        if not self.settings.xray_enabled:
            return
        desired = self._clients_from_keys(self._load_keys(db))
        async with self._lock:
            if not self.running:
                await self._stop_locked()
                await self._start_locked(desired)
                return

            remove = [client for key, client in self._clients.items() if key not in desired]
            add = [client for key, client in desired.items() if key not in self._clients]
            try:
                if remove:
                    await self._remove_clients(remove)
                if add:
                    await self._add_clients(add)
                self._clients = desired
            except Exception:
                logger.exception("Dynamic Xray user sync failed; restarting with desired state")
                await self._stop_locked()
                await self._start_locked(desired)

    async def _start_locked(self, desired: dict[tuple[str, str], XrayClient]) -> None:
        self.settings.xray_config_dir.mkdir(parents=True, exist_ok=True)
        path = Path(self.settings.xray_config_dir) / "config.json"
        await self._write_json(path, self._build_config(list(desired.values())))
        test = await self._run_process(
            [self.settings.xray_binary, "run", "-test", "-c", str(path)], timeout=15
        )
        if test.returncode != 0:
            self.last_error = (test.stderr or test.stdout or "unknown validation error")[-2000:]
            raise XrayRuntimeError(f"Xray configuration rejected: {self.last_error}")

        self.process = await asyncio.create_subprocess_exec(
            self.settings.xray_binary,
            "run",
            "-c",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._log_task = asyncio.create_task(self._drain_logs(self.process))
        try:
            await self._wait_for_api()
        except Exception:
            await self._stop_locked()
            raise
        self._clients = desired
        self.last_error = ""
        logger.info("Xray started with %s dynamic client(s)", len(desired))

    async def _add_clients(self, clients: list[XrayClient]) -> None:
        for inbound_tag in ("arena-vless-ws", "arena-vmess-ws", "arena-vless-reality"):
            group = [client for client in clients if client.inbound_tag == inbound_tag]
            if not group:
                continue
            protocol = group[0].protocol
            settings: dict = {"clients": [client.payload() for client in group]}
            if protocol == "vless":
                settings["decryption"] = "none"
            patch = {
                "inbounds": [
                    {
                        "tag": inbound_tag,
                        "listen": self.settings.xray_listen_host,
                        "port": self._inbound_port(inbound_tag),
                        "protocol": protocol,
                        "settings": settings,
                    }
                ]
            }
            path = Path(self.settings.xray_config_dir) / f"add-{inbound_tag}.json"
            await self._write_json(path, patch)
            await self._run_cli(["api", "adu", f"-server={self.api_address}", str(path)])

    async def _remove_clients(self, clients: list[XrayClient]) -> None:
        for inbound_tag in ("arena-vless-ws", "arena-vmess-ws", "arena-vless-reality"):
            emails = [client.email for client in clients if client.inbound_tag == inbound_tag]
            if emails:
                await self._run_cli(
                    [
                        "api",
                        "rmu",
                        f"-server={self.api_address}",
                        f"-tag={inbound_tag}",
                        *emails,
                    ]
                )

    def _inbound_port(self, inbound_tag: str) -> int:
        return {
            "arena-vless-ws": 11000,
            "arena-vmess-ws": 11001,
            "arena-vless-reality": self.settings.xray_reality_listen_port,
        }[inbound_tag]

    async def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        result = await self._run_process([self.settings.xray_binary, *args], timeout=10)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown Xray API error").strip()
            raise XrayRuntimeError(detail)
        return result

    async def _wait_for_api(self) -> None:
        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            if not self.running:
                raise XrayRuntimeError("Xray stopped before its API became ready")
            try:
                _, writer = await asyncio.open_connection(
                    self.settings.xray_api_host, self.settings.xray_api_port
                )
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.1)
        raise XrayRuntimeError("Timed out waiting for the Xray API")

    async def _drain_logs(self, process: asyncio.subprocess.Process) -> None:
        if not process.stdout:
            return
        async for line in process.stdout:
            logger.info("core: %s", line.decode(errors="replace").rstrip())

    async def _stats_loop(self) -> None:
        interval = self.settings.xray_stats_interval_seconds
        while True:
            await asyncio.sleep(interval)
            try:
                await self._sync_reality_state()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Could not synchronize REALITY usage and online IPs")

    async def _sync_reality_state(self) -> None:
        clients = {
            client.email: client
            for client in self._clients.values()
            if client.channel == "reality"
        }
        if not self.running or not clients:
            return

        traffic_result = await self._run_cli(
            [
                "api",
                "statsquery",
                f"-server={self.api_address}",
                "-pattern=@reality.arena",
                "-reset",
            ]
        )
        traffic = self.parse_user_stats(traffic_result.stdout)

        online_result = await self._run_cli(
            ["api", "statsgetallonlineusers", f"-server={self.api_address}"]
        )
        online_emails = [
            email
            for email in self.parse_online_users(online_result.stdout)
            if email in clients
        ]
        online: dict[str, dict[str, int]] = {}

        async def load_ips(email: str) -> tuple[str, dict[str, int]]:
            result = await self._run_cli(
                [
                    "api",
                    "statsonlineiplist",
                    f"-server={self.api_address}",
                    f"-email={email}",
                ]
            )
            return email, self.parse_online_ips(result.stdout)

        if online_emails:
            for email, ips in await asyncio.gather(*(load_ips(email) for email in online_emails)):
                online[email] = ips

        limits = await asyncio.to_thread(
            self._persist_reality_state, clients, traffic, online
        )
        await self._sync_ip_limit_rules(online, limits)

        from .database import SessionLocal

        with SessionLocal() as db:
            await self.reconcile(db)

    @staticmethod
    def parse_user_stats(raw: str) -> dict[str, dict[str, int]]:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise XrayRuntimeError("Xray returned invalid traffic statistics") from exc
        result: dict[str, dict[str, int]] = defaultdict(
            lambda: {"uplink": 0, "downlink": 0}
        )
        for item in payload.get("stat", []):
            parts = str(item.get("name", "")).split(">>>")
            if len(parts) != 4 or parts[0] != "user" or parts[2] != "traffic":
                continue
            direction = parts[3]
            if direction in {"uplink", "downlink"}:
                result[parts[1]][direction] += max(0, int(item.get("value", 0)))
        return dict(result)

    @staticmethod
    def parse_online_users(raw: str) -> list[str]:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise XrayRuntimeError("Xray returned invalid online-user data") from exc
        users: list[str] = []
        for value in payload.get("users", []):
            parts = str(value).split(">>>")
            users.append(parts[1] if len(parts) == 3 and parts[0] == "user" else str(value))
        return users

    @staticmethod
    def parse_online_ips(raw: str) -> dict[str, int]:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise XrayRuntimeError("Xray returned invalid online-IP data") from exc
        return {
            str(ip): int(last_seen)
            for ip, last_seen in payload.get("ips", {}).items()
        }

    @staticmethod
    def _persist_reality_state(
        clients: dict[str, XrayClient],
        traffic: dict[str, dict[str, int]],
        online: dict[str, dict[str, int]],
    ) -> dict[str, int]:
        from .database import SessionLocal

        now = datetime.now(timezone.utc)
        active_keys = {
            (client.user_id, client.node_id, ip)
            for email, ips in online.items()
            if (client := clients.get(email)) is not None
            for ip in ips
        }
        limits: dict[str, int] = {}
        with SessionLocal() as db:
            open_sessions = list(
                db.scalars(
                    select(ConnectionSession).where(
                        ConnectionSession.gateway_instance == "xray-reality",
                        ConnectionSession.ended_at.is_(None),
                    )
                )
            )
            session_index = {
                (session.user_id, session.node_id, session.source_ip): session
                for session in open_sessions
            }
            users: dict[str, User] = {}

            for email, client in clients.items():
                user = users.get(client.user_id)
                if user is None:
                    user = db.get(User, client.user_id)
                    if user is None:
                        continue
                    users[client.user_id] = user
                limits[email] = user.max_ips
                counters = traffic.get(email, {})
                uplink = max(0, int(counters.get("uplink", 0)))
                downlink = max(0, int(counters.get("downlink", 0)))
                if uplink or downlink:
                    if user.starts_at is None:
                        user.starts_at = now
                        if user.validity_days:
                            user.expires_at = now + timedelta(days=user.validity_days)
                    user.used_up_bytes += uplink
                    user.used_down_bytes += downlink

                email_ips = online.get(email, {})
                for ip in email_ips:
                    key = (client.user_id, client.node_id, ip)
                    session = session_index.get(key)
                    if session is None:
                        session = ConnectionSession(
                            user_id=client.user_id,
                            node_id=client.node_id,
                            source_ip=ip,
                            user_agent="Xray REALITY",
                            gateway_instance="xray-reality",
                        )
                        db.add(session)
                        session_index[key] = session
                        audit(
                            db,
                            "reality.connected",
                            entity_type="user",
                            entity_id=client.user_id,
                            detail={"node_id": client.node_id, "ip": ip},
                        )
                    session.last_seen_at = now

                if len(email_ips) == 1 and (uplink or downlink):
                    ip = next(iter(email_ips))
                    session = session_index.get((client.user_id, client.node_id, ip))
                    if session is not None:
                        session.uplink_bytes = (session.uplink_bytes or 0) + uplink
                        session.downlink_bytes = (session.downlink_bytes or 0) + downlink

            for session in open_sessions:
                key = (session.user_id, session.node_id, session.source_ip)
                if key not in active_keys:
                    session.ended_at = now
                    session.last_seen_at = now
                    session.status = "closed"
                    session.close_reason = "xray_offline"
                    audit(
                        db,
                        "reality.disconnected",
                        entity_type="user",
                        entity_id=session.user_id,
                        detail={"node_id": session.node_id, "ip": session.source_ip},
                    )
            db.commit()
        return limits

    async def _sync_ip_limit_rules(
        self, online: dict[str, dict[str, int]], limits: dict[str, int]
    ) -> None:
        desired_rules: dict[str, dict] = {}
        active_emails = set(online)
        for email in list(self._allowed_reality_ips):
            if email not in active_emails:
                self._allowed_reality_ips.pop(email, None)

        for email, ips_with_time in online.items():
            limit = max(1, limits.get(email, 1))
            current = self._allowed_reality_ips.setdefault(email, set())
            current.intersection_update(ips_with_time)
            if len(current) > limit:
                current.intersection_update(
                    sorted(current, key=lambda ip: ips_with_time[ip])[:limit]
                )
            candidates = sorted(
                (ip for ip in ips_with_time if ip not in current),
                key=lambda ip: ips_with_time[ip],
            )
            current.update(candidates[: max(0, limit - len(current))])
            for ip in set(ips_with_time) - current:
                digest = hashlib.sha256(f"{email}|{ip}".encode()).hexdigest()[:16]
                tag = f"arena-ip-limit-{digest}"
                desired_rules[tag] = {
                    "type": "field",
                    "ruleTag": tag,
                    "inboundTag": ["arena-vless-reality"],
                    "source": [ip],
                    "user": [email],
                    "outboundTag": "blocked",
                }

        desired_tags = set(desired_rules)
        remove = sorted(self._ip_limit_rule_tags - desired_tags)
        if remove:
            await self._run_cli(
                ["api", "rmrules", f"-server={self.api_address}", *remove]
            )
            self._ip_limit_rule_tags.difference_update(remove)

        add = sorted(desired_tags - self._ip_limit_rule_tags)
        if add:
            path = Path(self.settings.xray_config_dir) / "ip-limit-rules.json"
            await self._write_json(
                path,
                {
                    "routing": {
                        "rules": [desired_rules[tag] for tag in add],
                    }
                },
            )
            await self._run_cli(
                [
                    "api",
                    "adrules",
                    f"-server={self.api_address}",
                    "-append",
                    str(path),
                ]
            )
            self._ip_limit_rule_tags.update(add)

    async def stop(self) -> None:
        if self._stats_task:
            self._stats_task.cancel()
            await asyncio.gather(self._stats_task, return_exceptions=True)
            self._stats_task = None
        async with self._lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        process = self.process
        self.process = None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        if self._log_task:
            self._log_task.cancel()
            await asyncio.gather(self._log_task, return_exceptions=True)
        self._log_task = None
        self._clients = {}
        self._ip_limit_rule_tags = set()
        self._allowed_reality_ips = {}

    @staticmethod
    async def _write_json(path: Path, data: dict) -> None:
        encoded = json.dumps(data, ensure_ascii=True, indent=2) + "\n"
        temp = path.with_suffix(path.suffix + ".tmp")
        await asyncio.to_thread(temp.write_text, encoded, "utf-8")
        await asyncio.to_thread(temp.replace, path)

    @staticmethod
    async def _run_process(args: list[str], timeout: float) -> subprocess.CompletedProcess:
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise XrayRuntimeError(f"Command timed out: {' '.join(args[:3])}")
        return subprocess.CompletedProcess(
            args=args,
            returncode=process.returncode,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )


xray_runtime = XrayRuntime()
