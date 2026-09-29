"""
UMOA Banking Intelligence — Content-Addressed Storage Manager

Stores downloaded documents organized by SHA-256 hash:
    {storage_root}/{hash[:2]}/{hash}.{extension}

Guarantees:
  - Deduplication via content hashing.
  - Path traversal protection (hashes and extensions strictly sanitized).
  - Exact file integrity verification.
"""
import hashlib
import re
from pathlib import Path

from scraping.common.exceptions import SecurityError, StorageError
from scraping.common.models import StorageResult

_HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SAFE_EXT_PATTERN = re.compile(r"^[a-zA-Z0-9]{1,10}$")


class StorageManager:
    """Manages document file storage using content-addressed SHA-256 layout."""

    def __init__(self, storage_root: str | Path = "./data/downloads") -> None:
        self.storage_root = Path(storage_root).resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        """Compute the lowercase 64-character SHA-256 hex digest of bytes."""
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest().lower()

    @staticmethod
    def sanitize_extension(original_filename: str | None) -> str:
        """Extract and sanitize a safe file extension (e.g. 'pdf')."""
        if not original_filename:
            return "pdf"

        # Extract last component after dot
        parts = original_filename.split(".")
        if len(parts) > 1:
            candidate = parts[-1].split("?")[0].split("#")[0].lower()
            if _SAFE_EXT_PATTERN.match(candidate):
                return candidate

        return "pdf"

    def get_relative_path(self, file_hash: str, ext: str = "pdf") -> str:
        """Return the relative storage path: {hash[:2]}/{hash}.{ext}."""
        self._validate_hash(file_hash)
        ext = self.sanitize_extension(f"file.{ext}")
        return f"{file_hash[:2]}/{file_hash}.{ext}"

    def get_absolute_path(self, file_hash: str, ext: str = "pdf") -> Path:
        """Return the absolute Path on disk for a given hash and extension."""
        rel = self.get_relative_path(file_hash, ext)
        target = (self.storage_root / rel).resolve()

        # Path traversal guard: must be strictly inside storage_root
        if not str(target).startswith(str(self.storage_root)):
            raise SecurityError(f"Path traversal detected: {target}")

        return target

    def exists(self, file_hash: str, ext: str = "pdf") -> bool:
        """Check if a file with the given hash already exists in storage."""
        try:
            path = self.get_absolute_path(file_hash, ext)
            return path.is_file()
        except (SecurityError, StorageError):
            return False

    def store_content(
        self,
        content: bytes,
        original_filename: str | None = None,
        expected_hash: str | None = None,
    ) -> StorageResult:
        """
        Store binary content addressed by its SHA-256 hash.

        If the file already exists on disk, deduplication is triggered
        and the existing file is kept without unnecessary disk write.

        Args:
            content: Raw document bytes.
            original_filename: Original file name or URL for extension inference.
            expected_hash: Optional SHA-256 to verify against.

        Returns:
            StorageResult containing paths and deduplication status.
        """
        if not content:
            raise StorageError("Cannot store empty content")

        file_hash = self.compute_sha256(content)
        if expected_hash and expected_hash.lower() != file_hash:
            raise StorageError(
                f"Content hash mismatch: expected {expected_hash}, calculated {file_hash}"
            )

        ext = self.sanitize_extension(original_filename)
        rel_path = self.get_relative_path(file_hash, ext)
        abs_path = self.get_absolute_path(file_hash, ext)

        is_duplicate = abs_path.is_file()

        if not is_duplicate:
            # Ensure shard directory exists: e.g. ./data/downloads/a4/
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                abs_path.write_bytes(content)
            except OSError as err:
                raise StorageError(f"Failed to write document to {abs_path}: {err}") from err

        return StorageResult(
            file_hash=file_hash,
            file_size=len(content),
            relative_path=rel_path,
            absolute_path=str(abs_path),
            is_duplicate=is_duplicate,
        )

    def _validate_hash(self, file_hash: str) -> None:
        if not file_hash or not _HEX_64_PATTERN.match(file_hash.lower()):
            raise SecurityError(f"Invalid SHA-256 hash format: {file_hash!r}")
