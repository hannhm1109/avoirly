"""Private random object keys; no public mount and no user-supplied paths."""

import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

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
