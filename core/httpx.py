import asyncio
from typing import Any
import json

from core.storage_manager import StorageManager
from core.logger import logger


class Httpx:
    def __init__(self, target: str):
        self.httpx_path = "bin/httpx/httpx.exe"
        self.target = target
        self.storage = StorageManager()

    async def _subdomains(self) -> list[str]:
        await self.storage.init()
        rows = await self.storage.get_all(self.target)
        return [row.subdomain for row in rows]

    async def run_httpx(self) -> list[dict]:
        hosts = await self._subdomains()
        if not hosts:
            await self.storage.close()
            return []

        proc = await asyncio.create_subprocess_exec(
            self.httpx_path,
            "-silent",
            "-json",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        input_data = "\n".join(hosts).encode() + b"\n"
        stdout, stderr = await proc.communicate(input=input_data)

        if stderr:
            err_text = stderr.decode(errors="replace").strip()
            if err_text:
                logger.error(f"[httpx] {err_text}")

        raw_results = []
        for line in stdout.decode(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw_results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        # Persist: translate raw httpx output -> StorageManager's schema,
        # then fill in the hosts httpx never answered for as dead.
        update_payload = self._build_update_payload(hosts, raw_results)
        await self.storage.update_httpx_results(self.target, update_payload)
        await self.storage.close()

        return raw_results

    def _build_update_payload(
        self, hosts: list[str], raw_results: list[dict]
    ) -> list[dict]:
        """Map httpx's raw JSON lines onto StorageManager's expected keys.

        httpx emits one JSON object per *attempted* host, keyed by "input"
        (the original hostname you fed it), "status_code", and "title".
        Confirmed live sample line:

            {"input": "pmbounces.hackerone.com", "status_code": 200,
             "title": "Postmark — Email delivery for web apps",
             "failed": False, ...}

        Two distinct "dead" cases:
          1. httpx emits a line but sets "failed": True (connection refused,
             TLS error, etc. after a real attempt) — status_code/title will
             usually be absent or stale, so we don't trust them.
          2. httpx never emits a line at all for that host (DNS resolution
             failed before any HTTP attempt was made).

        Both are recorded as alive=False; only a line with failed=False
        gets alive=True plus its status_code/title.
        """
        payload: dict[str, dict] = {}

        for raw in raw_results:
            host = raw.get("input") or raw.get("url")
            if not host:
                continue

            if raw.get("failed"):
                payload[host] = {"subdomain": host, "alive": False}
            else:
                payload[host] = {
                    "subdomain": host,
                    "alive": True,
                    "status_code": raw.get("status_code"),
                    "title": raw.get("title"),
                }

        # Anything we sent in but didn't get a response line for = dead.
        for host in hosts:
            if host not in payload:
                payload[host] = {"subdomain": host, "alive": False}

        return list(payload.values())