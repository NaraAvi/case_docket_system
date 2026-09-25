"""Media storage and file handling boundary.

Handles real file uploads (evidence, interview recordings) on local disk
under `storage_root`, computing a SHA-256 hash while streaming to disk
(the chain-of-custody hash CPA Section 212 requires), and resolving stored
files back out for serving. `register_file` is kept for the older
metadata-only call sites that don't (yet) carry real file bytes.
"""

import hashlib
import os
import uuid
from pathlib import Path

ALLOWED_SUBDIRS = {"evidence", "recordings"}


class MediaManager:
    """Handles storage references, real file uploads, and file metadata."""

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
        """Stream an uploaded Werkzeug FileStorage to disk, hashing as it goes.

        Returns metadata including the SHA-256 hash and a `storage_reference`
        that `resolve_path` can later turn back into a real file path.
        """
        if subdir not in ALLOWED_SUBDIRS:
            raise ValueError("Invalid storage category.")
        if file_storage is None or not getattr(file_storage, "filename", None):
            raise ValueError("A file is required.")

        original_filename = os.path.basename(file_storage.filename)
        if original_filename in {"", ".", ".."}:
            raise ValueError("Filename is invalid.")

        stored_filename = f"{uuid.uuid4().hex}_{original_filename}"
        destination_dir = self._root_path() / subdir
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / stored_filename

        digest = hashlib.sha256()
        size_bytes = 0
        with open(destination, "wb") as handle:
            while True:
                chunk = file_storage.stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size_bytes += len(chunk)
                handle.write(chunk)

        return {
            "filename": original_filename,
            "stored_filename": stored_filename,
            "storage_reference": f"{subdir}/{stored_filename}",
            "storage_root": self.storage_root,
            "content_type": file_storage.mimetype,
            "size_bytes": size_bytes,
            "sha256_hash": digest.hexdigest(),
        }

    def resolve_path(self, storage_reference):
        """Resolve a `storage_reference` (e.g. "evidence/<uuid>_name.jpg") back
        to an absolute path, rejecting anything that would escape the storage
        root. Returns None if the reference is invalid or the file is missing.
        """
        if not storage_reference:
            return None

        parts = str(storage_reference).replace("\\", "/").split("/")
        if len(parts) != 2 or parts[0] not in ALLOWED_SUBDIRS:
            return None

        subdir, stored_filename = parts
        if stored_filename in {"", ".", ".."} or "/" in stored_filename:
            return None

        candidate = (self._root_path() / subdir / stored_filename).resolve()
        root = self._root_path().resolve()
        if root not in candidate.parents:
            return None
        if not candidate.is_file():
            return None
        return candidate
