"""Local media storage and file metadata helpers."""

import hashlib
import os
import uuid
from pathlib import Path


class MediaManager:
    """Store uploaded evidence/recordings and return safe metadata.

    The original prototype exposed metadata-only registration.  The current
    boundary also supports real multipart uploads, hashing files as they are
    written and keeping storage references relative to the configured root.
    """

    ALLOWED_SUBDIRS = {"evidence", "recordings"}
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024

    def __init__(self, storage_root="uploads"):
        self.storage_root = storage_root

    def _root_path(self):
        path = Path(self.storage_root)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register_file(self, filename, metadata=None):
        safe_filename = (filename or "").strip()
        if not safe_filename:
            raise ValueError("Filename is required.")

        safe_filename = os.path.basename(safe_filename).replace("\\", "/")
        if safe_filename in {"", ".", ".."}:
            raise ValueError("Filename is invalid.")

        meta = metadata or {}
        storage_reference = str(meta.get("storage_reference") or safe_filename).strip()
        if not storage_reference:
            raise ValueError("Storage reference is required.")

        storage_reference = os.path.basename(storage_reference).replace("\\", "/")
        payload = {
            "filename": safe_filename,
            "storage_reference": storage_reference,
            "storage_root": self.storage_root,
            "metadata": meta,
        }
        return payload

    def save_upload(self, file_storage, subdir):
        """Persist a multipart upload and return its chain-of-custody metadata."""
        if subdir not in self.ALLOWED_SUBDIRS:
            raise ValueError("Invalid storage category.")
        if file_storage is None or not getattr(file_storage, "filename", None):
            raise ValueError("A file is required.")

        original_filename = os.path.basename(str(file_storage.filename).replace("\\", "/"))
        if original_filename in {"", ".", ".."}:
            raise ValueError("Filename is invalid.")

        stored_filename = f"{uuid.uuid4().hex}_{original_filename}"
        destination_dir = self._root_path() / subdir
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / stored_filename

        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with open(destination, "wb") as handle:
                while True:
                    chunk = file_storage.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > self.MAX_UPLOAD_BYTES:
                        raise ValueError("File exceeds the 50 MB upload limit.")
                    digest.update(chunk)
                    handle.write(chunk)
        except Exception:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        return {
            "filename": original_filename,
            "stored_filename": stored_filename,
            "storage_reference": f"{subdir}/{stored_filename}",
            "storage_root": self.storage_root,
            "content_type": getattr(file_storage, "mimetype", None),
            "size_bytes": size_bytes,
            "sha256_hash": digest.hexdigest(),
        }

    def resolve_path(self, storage_reference):
        """Resolve a reference below the storage root, rejecting traversal."""
        if not storage_reference:
            return None

        parts = str(storage_reference).replace("\\", "/").split("/")
        if len(parts) != 2 or parts[0] not in self.ALLOWED_SUBDIRS:
            return None

        subdir, stored_filename = parts
        if stored_filename in {"", ".", ".."} or "/" in stored_filename or "\\" in stored_filename:
            return None

        root = self._root_path().resolve()
        candidate = (root / subdir / stored_filename).resolve()
        if root not in candidate.parents or not candidate.is_file():
            return None
        return candidate

    def delete(self, storage_reference, subdir=None):
        """Delete a stored object if it exists; return whether one was removed."""
        if subdir is not None:
            prefix = f"{subdir}/"
            if not str(storage_reference or "").replace("\\", "/").startswith(prefix):
                return False
        path = self.resolve_path(storage_reference)
        if path is None:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True
