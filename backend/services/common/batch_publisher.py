"""Batch publisher for Celery tasks.

Reduces queue flooding by accumulating task signatures and flushing them
in configurable batch sizes.  Instead of dispatching N individual tasks
one-by-one (which hammers the broker and causes queue spikes), callers
accumulate them via `add()` / `add_many()` and call `flush()` to send
them in chunks.

Usage (synchronous — inside a Celery task):

    bp = BatchPublisher(chunk_size=50)
    for portal in portals:
        bp.add(scrape_portal_task.s(portal=portal, ...))
    bp.flush()  # sends in chunks of 50

Usage (in scrape_portal_task — batch downstream dispatch):

    bp = BatchPublisher(chunk_size=50)
    for job_id in saved_job_ids:
        bp.add(generate_embedding_task.s(job_id))
        bp.add(run_application_workflow_task.s(job_id, candidate_id))
    bp.flush()
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Default chunk size — 50 is a good balance:
# - Large enough to amortise broker round-trips
# - Small enough to avoid oversized payloads / memory spikes
DEFAULT_CHUNK_SIZE = 50


class BatchPublisher:
    """Accumulate Celery task signatures and flush in chunks.

    Thread-safe for use inside prefork workers (each process has its own
    BatchPublisher instance).
    """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self.chunk_size = max(1, chunk_size)
        self._pending: list = []
        self._total_dispatched: int = 0

    def add(self, signature) -> None:
        """Add a single Celery signature (`.s()` or `.si()`)."""
        self._pending.append(signature)

    def add_many(self, signatures: list) -> None:
        """Add multiple Celery signatures at once."""
        self._pending.extend(signatures)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def total_dispatched(self) -> int:
        return self._total_dispatched

    def flush(self, countdown: int | None = None) -> int:
        """Dispatch all pending tasks in chunks.

        Args:
            countdown: Optional seconds to delay each task. Applied uniformly.

        Returns:
            Total number of tasks dispatched.
        """
        if not self._pending:
            return 0

        dispatched = 0
        while self._pending:
            chunk = self._pending[: self.chunk_size]
            self._pending = self._pending[self.chunk_size :]

            for sig in chunk:
                kwargs = {}
                if countdown is not None:
                    kwargs["countdown"] = countdown
                sig.apply_async(**kwargs)
                dispatched += 1

        self._total_dispatched += dispatched
        logger.info(
            "batch_publisher_flushed",
            dispatched=dispatched,
            total=self._total_dispatched,
            chunk_size=self.chunk_size,
        )
        return dispatched

    def flush_with_stagger(
        self,
        base_countdown: int = 0,
        stagger_seconds: float = 0.1,
    ) -> int:
        """Dispatch all pending tasks with staggered countdown to avoid thundering herd.

        Each task gets: base_countdown + (index_in_chunk * stagger_seconds)

        Args:
            base_countdown: Base delay in seconds before any task runs.
            stagger_seconds: Additional delay between consecutive tasks.

        Returns:
            Total number of tasks dispatched.
        """
        if not self._pending:
            return 0

        dispatched = 0
        idx = 0
        while self._pending:
            chunk = self._pending[: self.chunk_size]
            self._pending = self._pending[self.chunk_size :]

            for sig in chunk:
                cd = base_countdown + int(idx * stagger_seconds)
                sig.apply_async(countdown=cd)
                dispatched += 1
                idx += 1

        self._total_dispatched += dispatched
        logger.info(
            "batch_publisher_flushed_staggered",
            dispatched=dispatched,
            total=self._total_dispatched,
            chunk_size=self.chunk_size,
        )
        return dispatched

    def clear(self) -> None:
        """Discard all pending tasks without dispatching."""
        self._pending.clear()

    def __len__(self) -> int:
        return self.pending_count