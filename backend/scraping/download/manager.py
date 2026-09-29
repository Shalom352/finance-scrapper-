"""
UMOA Banking Intelligence — Download Manager

Async HTTP downloader with:
  - Configurable concurrency semaphore
  - Exponential backoff retries for transient errors
  - Content-Type and size limits validation
  - Streaming downloads with early abort on size overflow
  - Comprehensive structured logging
"""
import asyncio
import time
from collections.abc import Sequence
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger
from scraping.common.exceptions import SecurityError
from scraping.common.models import DownloadResult

logger = get_logger(__name__)

# Default allowed content types for document downloads
DEFAULT_ALLOWED_CONTENT_TYPES: Sequence[str] = (
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

DEFAULT_USER_AGENT = (
    "UMOA-Banking-Intelligence-Bot/1.0 (+https://github.com/Shalom352/finance-scrapper-)"
)


class DownloadManager:
    """Manages asynchronous document downloads with retry and security controls."""

    def __init__(
        self,
        concurrency: int = 3,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        max_file_size_bytes: int = 100 * 1024 * 1024,  # 100 MB
        user_agent: str = DEFAULT_USER_AGENT,
        allowed_content_types: Sequence[str] = DEFAULT_ALLOWED_CONTENT_TYPES,
    ) -> None:
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.max_file_size_bytes = max_file_size_bytes
        self.user_agent = user_agent
        self.allowed_content_types = tuple(ct.lower() for ct in allowed_content_types)

    def validate_url(self, url: str) -> None:
        """Validate URL scheme against SSRF / local protocol attacks."""
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            raise SecurityError(f"Unsupported or dangerous URL scheme: {parsed.scheme!r}")
        if not parsed.netloc:
            raise SecurityError(f"URL missing hostname: {url!r}")

    async def download_file(
        self,
        client: httpx.AsyncClient,
        url: str,
        verify_content_type: bool = True,
    ) -> DownloadResult:
        """
        Download a file with retries and safety checks.

        Args:
            client: Pre-configured httpx.AsyncClient.
            url: Remote document URL.
            verify_content_type: Whether to validate the Content-Type header.

        Returns:
            DownloadResult with content or error details.
        """
        self.validate_url(url)

        headers = {"User-Agent": self.user_agent}
        start_time = time.perf_counter()
        attempt = 0

        async with self.semaphore:
            while attempt <= self.max_retries:
                attempt += 1
                try:
                    logger.info("download_attempt", url=url, attempt=attempt)

                    async with client.stream(
                        "GET",
                        url,
                        headers=headers,
                        follow_redirects=True,
                        timeout=self.timeout_seconds,
                    ) as response:
                        status_code = response.status_code

                        # Check HTTP status
                        if response.is_error:
                            # 404, 403, 401 are non-retryable client errors
                            if status_code in (401, 403, 404, 410, 422):
                                logger.warning(
                                    "download_client_error",
                                    url=url,
                                    status=status_code,
                                    attempt=attempt,
                                )
                                return DownloadResult(
                                    url=url,
                                    success=False,
                                    status_code=status_code,
                                    duration_seconds=time.perf_counter() - start_time,
                                    retry_count=attempt - 1,
                                    error_message=f"HTTP {status_code} {response.reason_phrase}",
                                )
                            # For 5xx, raise to trigger retry
                            response.raise_for_status()

                        # Content-Type check
                        content_type = response.headers.get("content-type", "").lower().split(";")[0].strip()
                        if verify_content_type and content_type:
                            if not any(allowed in content_type for allowed in self.allowed_content_types):
                                msg = f"Invalid Content-Type: {content_type!r} (expected one of {self.allowed_content_types})"
                                logger.warning("download_content_type_rejected", url=url, content_type=content_type)
                                return DownloadResult(
                                    url=url,
                                    success=False,
                                    status_code=status_code,
                                    content_type=content_type,
                                    duration_seconds=time.perf_counter() - start_time,
                                    retry_count=attempt - 1,
                                    error_message=msg,
                                )

                        # Content-Length header check
                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > self.max_file_size_bytes:
                            msg = f"File size {content_length} bytes exceeds limit of {self.max_file_size_bytes} bytes"
                            logger.warning("download_size_exceeded", url=url, size=content_length)
                            return DownloadResult(
                                url=url,
                                success=False,
                                status_code=status_code,
                                content_type=content_type,
                                duration_seconds=time.perf_counter() - start_time,
                                retry_count=attempt - 1,
                                error_message=msg,
                            )

                        # Stream content and accumulate
                        chunks: list[bytes] = []
                        total_bytes = 0

                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            total_bytes += len(chunk)
                            if total_bytes > self.max_file_size_bytes:
                                msg = f"Download exceeded max size limit of {self.max_file_size_bytes} bytes during streaming"
                                logger.warning("download_stream_size_exceeded", url=url, current_size=total_bytes)
                                return DownloadResult(
                                    url=url,
                                    success=False,
                                    status_code=status_code,
                                    content_type=content_type,
                                    duration_seconds=time.perf_counter() - start_time,
                                    retry_count=attempt - 1,
                                    error_message=msg,
                                )
                            chunks.append(chunk)

                        content = b"".join(chunks)
                        duration = time.perf_counter() - start_time
                        logger.info(
                            "download_success",
                            url=url,
                            status=status_code,
                            size_bytes=len(content),
                            duration=round(duration, 3),
                        )

                        return DownloadResult(
                            url=url,
                            success=True,
                            status_code=status_code,
                            content=content,
                            content_type=content_type,
                            file_size=len(content),
                            duration_seconds=duration,
                            retry_count=attempt - 1,
                        )

                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                    duration = time.perf_counter() - start_time
                    if attempt > self.max_retries:
                        logger.error(
                            "download_failed_max_retries",
                            url=url,
                            error=str(exc),
                            attempt=attempt,
                            duration=round(duration, 3),
                        )
                        return DownloadResult(
                            url=url,
                            success=False,
                            duration_seconds=duration,
                            retry_count=attempt - 1,
                            error_message=f"Failed after {attempt} attempts: {exc}",
                        )

                    sleep_time = self.backoff_factor ** attempt
                    logger.warning(
                        "download_retry",
                        url=url,
                        error=str(exc),
                        attempt=attempt,
                        next_retry_seconds=round(sleep_time, 2),
                    )
                    await asyncio.sleep(sleep_time)

                except Exception as exc:
                    duration = time.perf_counter() - start_time
                    logger.error("download_unexpected_error", url=url, error=str(exc))
                    return DownloadResult(
                        url=url,
                        success=False,
                        duration_seconds=duration,
                        retry_count=attempt - 1,
                        error_message=f"Unexpected error: {exc}",
                    )

        return DownloadResult(
            url=url,
            success=False,
            duration_seconds=time.perf_counter() - start_time,
            retry_count=attempt,
            error_message="Unknown download failure",
        )
