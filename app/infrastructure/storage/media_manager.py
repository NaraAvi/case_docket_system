"""Media storage and file handling boundary.

This placeholder defines where uploaded evidence, audio recordings, and
attachment references will be managed in future phases.
"""

import os


class MediaManager:
    """Handles storage references and file metadata."""

    def __init__(self, storage_root="uploads"):
        self.storage_root = storage_root

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
