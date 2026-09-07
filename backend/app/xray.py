import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .models import AccessKey
from .services.accounts import user_allowed


logger = logging.getLogger("arena.xray")


class XrayRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class XrayClient:
    protocol: str
    credential: str

    @property
    def inbound_tag(self) -> str:
        return f"arena-{self.protocol}-ws"

    @property
    def email(self) -> str:
        return f"{self.credential}@{self.protocol}.arena"

    def payload(self) -> dict:
        return {"id": self.credential, "email": self.email, "level": 0}


class XrayRuntime:
    """Own the Xray process and update inbound users without dropping live sessions."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._log_task: asyncio.Task | None = None
        self._clients: dict[tuple[str, str], XrayClient] = {}
        self.last_error = ""

    @property
    def api_address(self) -> str:
        return f"{self.settings.xray_api_host}:{self.settings.xray_api_port}"

    @property
    def running(self) -> bool:
        return bool(self.process and self.process.returncode is None)

    @staticmethod
    def _client_key(client: XrayClient) -> tuple[str, str]:
        return client.protocol, client.credential

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
            client = XrayClient(protocol=protocol, credential=key.credential)
            clients[self._client_key(client)] = client
        return clients

    def build_config(self, keys: list[AccessKey]) -> dict:
        return self._build_config(list(self._clients_from_keys(keys).values()))

    def _build_config(self, clients: list[XrayClient]) -> dict:
        grouped = {
            protocol: [client.payload() for client in clients if client.protocol == protocol]
            for protocol in ("vless", "vmess")
        }

        def inbound(protocol: str, port: int) -> dict:
            protocol_settings: dict = {"clients": grouped[protocol]}
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

        return {
            "log": {"loglevel": "warning"},
            "api": {"tag": "api", "services": ["HandlerService", "StatsService"]},
            "policy": {
                "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
                "system": {"statsInboundUplink": True, "statsInboundDownlink": True},
            },
            "stats": {},
            "inbounds": [
                {
                    "tag": "api",
                    "listen": self.settings.xray_api_host,
                    "port": self.settings.xray_api_port,
                    "protocol": "dokodemo-door",
                    "settings": {"address": self.settings.xray_api_host},
                },
                inbound("vless", 11000),
                inbound("vmess", 11001),
            ],
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
        for protocol in ("vless", "vmess"):
            group = [client for client in clients if client.protocol == protocol]
            if not group:
                continue
            settings: dict = {"clients": [client.payload() for client in group]}
            if protocol == "vless":
                settings["decryption"] = "none"
            patch = {
                "inbounds": [
                    {
                        "tag": f"arena-{protocol}-ws",
                        "listen": self.settings.xray_listen_host,
                        "port": 11000 if protocol == "vless" else 11001,
                        "protocol": protocol,
                        "settings": settings,
                    }
                ]
            }
            path = Path(self.settings.xray_config_dir) / f"add-{protocol}.json"
            await self._write_json(path, patch)
            await self._run_cli(["api", "adu", f"-server={self.api_address}", str(path)])

    async def _remove_clients(self, clients: list[XrayClient]) -> None:
        for protocol in ("vless", "vmess"):
            emails = [client.email for client in clients if client.protocol == protocol]
            if emails:
                await self._run_cli(
                    [
                        "api",
                        "rmu",
                        f"-server={self.api_address}",
                        f"-tag=arena-{protocol}-ws",
                        *emails,
                    ]
                )

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

    async def stop(self) -> None:
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
