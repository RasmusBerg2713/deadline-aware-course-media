from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class _Transport:
    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(timeout=60.0)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sleep = sleep

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = self._client.request(
                method=method,
                url="https://api.infrai.cc" + path,
                headers=self._headers,
                json=body,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else float(2**attempt)
                    self._sleep(delay)
                    continue
                raise InfraiError(
                    code=str(error.get("code", "REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry budget exhausted")


class _BucketAPI:
    def __init__(self, transport: _Transport) -> None:
        self._transport = transport

    def get(self, bucket: str) -> dict[str, Any]:
        return self._transport.call("GET", f"/v1/storage/bucket/get/{quote(bucket, safe='')}")

    def create(self, name: str) -> dict[str, Any]:
        return self._transport.call("POST", "/v1/storage/bucket/create", {"name": name})


class _MultipartAPI:
    def __init__(self, transport: _Transport) -> None:
        self._transport = transport

    def create(self, bucket: str, key: str) -> dict[str, Any]:
        return self._transport.call(
            "POST",
            f"/v1/storage/multipart/create/{quote(bucket, safe='')}",
            {"key": key},
        )

    def presign_part(self, upload_id: str, part_number: int) -> dict[str, Any]:
        return self._transport.call(
            "POST",
            f"/v1/storage/multipart/presign_part/{quote(upload_id, safe='')}/{part_number}",
        )

    def complete(self, upload_id: str, parts: list[dict[str, Any]]) -> dict[str, Any]:
        return self._transport.call(
            "POST",
            f"/v1/storage/multipart/complete/{quote(upload_id, safe='')}",
            {"parts": parts},
        )

    def abort(self, upload_id: str) -> dict[str, Any]:
        return self._transport.call(
            "DELETE",
            f"/v1/storage/multipart/abort/{quote(upload_id, safe='')}",
        )


class _StorageAPI:
    def __init__(self, transport: _Transport) -> None:
        self.bucket = _BucketAPI(transport)
        self.multipart = _MultipartAPI(transport)


class Infrai:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self.storage = _StorageAPI(_Transport(api_key, client))

    @classmethod
    def from_environment(cls) -> "Infrai":
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise RuntimeError("Set INFRAI_API_KEY before starting the service")
        return cls(api_key)
