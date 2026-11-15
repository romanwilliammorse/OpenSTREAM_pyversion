"""Private, immutable-by-default Blob storage; no scientific calculations.

Uses the official ``vercel-blob==0.5.0`` synchronous API. Its query iterator
follows pagination. Existing-key rejection is performed by Blob's PUT, never
by a list-then-write check. Provider errors are deliberately not echoed.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import time
from urllib.parse import urlsplit

DEFAULT_PREFIX = "openstream/v1/"
_PART = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*\Z")


class CloudStoreError(RuntimeError):
    """Sanitized storage failure; callers must fail closed."""


class BlobConflictError(CloudStoreError):
    """An immutable destination already exists."""


class BlobMissingError(CloudStoreError):
    """No exact matching object is present in the inventory."""


def _safe_key(value, *, prefix=False):
    if not isinstance(value, str) or len(value) > 900:
        raise ValueError("Invalid storage key")
    checked = value[:-1] if prefix and value.endswith("/") else value
    if prefix and checked == "":
        return value
    if not checked or any(not _PART.fullmatch(p) or p in (".", "..") for p in checked.split("/")):
        raise ValueError("Invalid storage key")
    return value


def _field(value, name):
    return value[name] if isinstance(value, dict) else getattr(value, name)


def _put_conflict(error):
    """Only positive collision evidence is eligible for trying another slot.

    SDK 0.5.0 maps an unrecognized HTTP 400 code to 'bad_request'. Keep the
    compatibility message whitelist exact; do not treat arbitrary 400/409,
    permission failures, outages or quota errors as existing objects.
    """
    status, code = getattr(error, "status_code", None), getattr(error, "code", None)
    if status == 412 and code in (None, "precondition_failed"):
        return True  # Our PUT supplies no ifMatch: its only condition is absent key.
    if status in (400, 409, 412) and code in ("blob_already_exists", "already_exists"):
        return True
    messages = {
        "This blob already exists", "This blob already exists.",
        "This blob already exists, use `allowOverwrite: true` to overwrite it.",
        "Vercel Blob: This blob already exists, use `allowOverwrite: true` to overwrite it.",
    }
    return status == 400 and code in (None, "bad_request") and str(error) in messages


def _failure(operation, error):
    status = getattr(error, "status_code", None)
    suffix = f" (HTTP {status})" if type(status) is int and 100 <= status <= 599 else ""
    return CloudStoreError(f"Private storage {operation} failed{suffix}.")


class CloudStore:
    def __init__(self, store_id=None, *, blob_client=None, prefix=DEFAULT_PREFIX):
        store_id = store_id if store_id is not None else os.environ.get("BLOB_STORE_ID", "")
        if not isinstance(store_id, str):
            raise ValueError("Invalid private Blob store identifier")
        store_id = store_id.removeprefix("store_").strip()
        if not re.fullmatch(r"[A-Za-z0-9-]+", store_id):
            raise ValueError("A valid BLOB_STORE_ID is required")
        if not isinstance(prefix, str) or not prefix.endswith("/") or not prefix.strip("/"):
            raise ValueError("Invalid storage prefix")
        _safe_key(prefix, prefix=True)
        self.store_id = store_id
        self.prefix = prefix
        self._host = f"{store_id.lower()}.private.blob.vercel-storage.com"
        self._blob_client = blob_client

    @classmethod
    def from_env(cls):
        """SDK resolves request OIDC, or explicit worker environment credentials."""
        return cls()

    @property
    def client(self):
        if self._blob_client is None:
            try:
                from vercel.blob import sync
            except ImportError:
                raise CloudStoreError("Official private Blob SDK is not installed.") from None
            self._blob_client = sync
        return self._blob_client

    def _pathname(self, key, *, prefix=False):
        return self.prefix + _safe_key(key, prefix=prefix)

    def _url(self, url):
        if not isinstance(url, str) or any(ord(c) < 33 or ord(c) == 127 for c in url):
            raise ValueError("Invalid private storage URL")
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme == "https" and parsed.netloc.lower() == self._host
                     and parsed.hostname == self._host and parsed.port is None
                     and parsed.username is None and parsed.password is None
                     and not parsed.query and not parsed.fragment
                     and parsed.path.startswith("/" + self.prefix))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("URL is outside the configured private storage namespace")
        _safe_key(parsed.path[len(self.prefix)+1:])  # Also rejects percent escapes.
        return url

    def put_bytes(self, key, body, content_type, overwrite=False):
        pathname = self._pathname(key)
        if not isinstance(body, (bytes, bytearray, memoryview)):
            raise TypeError("Storage body must be bytes")
        if type(overwrite) is not bool:
            raise TypeError("overwrite must be a boolean")
        if not isinstance(content_type, str) or not content_type or any(ord(c) < 32 or ord(c) == 127 for c in content_type):
            raise ValueError("Invalid content type")
        body = bytes(body)
        try:
            result = self.client.put_blob(pathname, body, access="private",
                content_type=content_type, content_length=len(body),
                add_random_suffix=False, allow_overwrite=overwrite)
        except Exception as error:
            if not overwrite and _put_conflict(error):
                raise BlobConflictError("Immutable storage object already exists.") from None
            raise _failure("upload", error) from None
        try:
            url = self._url(_field(result, "url"))
            if _field(result, "pathname") != pathname:
                raise ValueError("Unexpected destination")
            if urlsplit(url).path != "/" + pathname:
                raise ValueError("Unexpected object URL")
        except Exception:
            raise CloudStoreError("Private storage returned invalid upload metadata.") from None
        return {"key": key, "url": url, "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}

    def put_json(self, key, obj):
        body = (json.dumps(obj, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
        return self.put_bytes(key, body, "application/json")

    def read_bytes_by_url(self, url):
        url = self._url(url)
        try:
            body = _field(self.client.get_blob(url, access="private"), "body")
            if not isinstance(body, (bytes, bytearray, memoryview)):
                raise TypeError("Invalid response body")
            return bytes(body)
        except Exception as error:
            raise _failure("download", error) from None

    def iter_bytes_by_url(self, url):
        url = self._url(url)
        def chunks():
            try:
                with self.client.stream_blob(url, access="private") as stream:
                    for chunk in stream:
                        if not isinstance(chunk, bytes):
                            raise TypeError("Invalid response chunk")
                        yield chunk
            except Exception as error:
                raise _failure("download", error) from None
        return chunks()

    def get_json_by_url(self, url):
        body = self.read_bytes_by_url(url)
        try:
            def invalid_constant(_):
                raise ValueError("Nonfinite JSON")
            return json.loads(body.decode("utf-8"), parse_constant=invalid_constant)
        except (UnicodeDecodeError, ValueError):
            raise CloudStoreError("Private storage object is not valid JSON.") from None

    def list(self, prefix=""):
        pathname = self._pathname(prefix, prefix=True)
        result = []
        try:
            # query_blobs is an auto-paginated iterator, not a single result page.
            for item in self.client.query_blobs(prefix=pathname, page_size=1000):
                name = _field(item, "pathname")
                if not isinstance(name, str) or not name.startswith(pathname):
                    raise ValueError("Inventory escaped requested prefix")
                key = _safe_key(name[len(self.prefix):])
                url = self._url(_field(item, "url"))
                if urlsplit(url).path != "/" + name:
                    raise ValueError("Inventory URL differs from key")
                size = _field(item, "size")
                if type(size) is not int or size < 0:
                    raise ValueError("Invalid object size")
                uploaded = _field(item, "uploaded_at")
                result.append({"key": key, "url": url, "size": size,
                    "etag": _field(item, "etag"),
                    "uploaded_at": uploaded.isoformat() if hasattr(uploaded, "isoformat") else uploaded})
        except Exception as error:
            raise _failure("inventory", error) from None
        return result

    def _find(self, key):
        _safe_key(key)
        return next((item for item in self.list(key) if item["key"] == key), None)

    def contains(self, key):
        return self._find(key) is not None

    def read_bytes(self, key):
        item = self._find(key)
        if item is None:
            raise BlobMissingError("Storage object is not present.")
        return self.read_bytes_by_url(item["url"])

    def get_json(self, key):
        item = self._find(key)
        if item is None:
            raise BlobMissingError("Storage object is not present.")
        return self.get_json_by_url(item["url"])

    def claim_login_attempt(self, client_ip, secret, *, now=None, limit=5):
        """Consume an immutable slot; false means this minute's slots are full.

        A provider outage raises CloudStoreError (deny login), never permission
        to proceed. The window is a UTC minute, not a rolling 60-second window.
        Slots are not deleted or overwritten; retention is a separate task.
        """
        address = ipaddress.ip_address(client_ip)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("Login limiter requires a secret of at least 32 bytes")
        if type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("Login limit must be between one and five")
        now = time.time() if now is None else now
        if not isinstance(now, (float, int)) or not math.isfinite(now) or now < 0:
            raise ValueError("Invalid login limiter timestamp")
        minute = int(now // 60)
        identity = hmac.new(secret, str(address).encode("ascii"), hashlib.sha256).hexdigest()
        for slot in range(limit):
            key = f"security/login/{identity}/{minute}/{slot}.json"
            try:
                self.put_json(key, {"minute": minute, "slot": slot})
                return True
            except BlobConflictError:
                continue
        return False
