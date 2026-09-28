"""Private random object keys; no public mount and no user-supplied paths."""

import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from .extraction import MAX_BYTES, ProcessingError, validate_file


class PrivateStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, key):
        if not re.fullmatch(r"[a-f0-9]{32}\.(pdf|png|jpg|jpeg)", key):
            raise ValueError("Invalid private storage key")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("Object is outside private storage")
        return path

    def save_upload(self, stream, filename):
        suffix = Path(filename or "").suffix.lower()
        if suffix not in (".pdf", ".png", ".jpg", ".jpeg"):
            raise ProcessingError("WRONG_MIME", "Only PDF, PNG and JPEG files are supported.")
        fd, temporary = tempfile.mkstemp(suffix=suffix, dir=self.root)
        try:
            with os.fdopen(fd, "wb") as dest:
                size = 0
                while chunk := stream.read(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ProcessingError("FILE_SIZE", "Upload exceeds 10 MiB.")
                    dest.write(chunk)
                dest.flush()
                os.fsync(dest.fileno())
            checked = validate_file(temporary)
            key = uuid4().hex + suffix
            os.replace(temporary, self.path(key))
            return key, checked
        finally:
            Path(temporary).unlink(missing_ok=True)

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)

    def read(self, key):
        with self.path(key).open("rb") as source:
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise OSError("Stored object exceeds the limit")
        return data

    @contextmanager
    def materialize(self, key):
        yield self.path(key)

    def check_private(self):
        return None


def check_key(key):
    if not re.fullmatch(r"[a-f0-9]{32}\.(pdf|png|jpg|jpeg)", key):
        raise ValueError("Invalid private storage key")
    return key


class SupabaseStorage:
    """Server-only Storage REST API; sources are never returned as public URLs."""

    def __init__(self, settings, client=None):
        self.bucket = settings.storage_bucket
        self.client = client or httpx.Client(
            base_url=settings.supabase_url + "/storage/v1/",
            headers={"apikey": settings.supabase_secret_key},
            timeout=httpx.Timeout(60, connect=10),
            follow_redirects=False,
        )

    def request(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
            if response.status_code == 404:
                raise FileNotFoundError("Private object not found")
            if not response.is_success:
                raise OSError("Private storage request failed")
            return response
        except httpx.HTTPError as exc:
            raise OSError("Private storage unavailable") from exc

    def check_private(self):
        bucket = self.request("GET", f"bucket/{self.bucket}").json()
        if bucket.get("public") is not False:
            raise RuntimeError("Document bucket must be private before startup.")

    def save_upload(self, stream, filename):
        with tempfile.TemporaryDirectory(prefix="avoirly-upload-") as root:
            local = PrivateStorage(root)
            key, checked = local.save_upload(stream, filename)
            self.request(
                "POST",
                f"object/{self.bucket}/{key}",
                content=checked.data,
                headers={"Content-Type": checked.mime, "x-upsert": "false"},
            )
            return key, checked

    def read(self, key):
        key = check_key(key)
        try:
            with self.client.stream("GET", f"object/authenticated/{self.bucket}/{key}") as response:
                if response.status_code == 404:
                    raise FileNotFoundError("Private object not found")
                if not response.is_success:
                    raise OSError("Private storage request failed")
                data = bytearray()
                for chunk in response.iter_bytes(65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise OSError("Stored object exceeds the limit")
                return bytes(data)
        except httpx.HTTPError as exc:
            raise OSError("Private storage unavailable") from exc

    @contextmanager
    def materialize(self, key):
        key = check_key(key)
        with tempfile.TemporaryDirectory(prefix="avoirly-source-") as root:
            target = Path(root) / key
            target.write_bytes(self.read(key))
            yield target

    def delete(self, key):
        # The delete API is idempotent for absent objects.
        self.request("DELETE", f"object/{self.bucket}", json={"prefixes": [check_key(key)]})


def create_storage(settings):
    return SupabaseStorage(settings) if settings.hosted else PrivateStorage(settings.storage_root)
