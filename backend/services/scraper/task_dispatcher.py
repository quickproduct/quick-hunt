"""Custom task dispatcher for queue-based broker routing.

This module provides a wrapper for Celery task dispatching that routes tasks
to the correct broker based on their destination queue.

Broker routing:
  - RabbitMQ: jh_scraping_bulk, jh_scraping_realtime, jh_scraping_enrichment
  - Redis: jh_jobs_maintenance, jh_cover_letter_*, jh_email_*
"""

import os
from typing import Any, Dict, Optional

from celery import Celery
from services.api.core.config import get_settings

settings = get_settings()

# Queue to broker mapping
_REDIS_QUEUES = {
    "jh_jobs_maintenance",
    "jh_cover_letter_bulk",
    "jh_cover_letter_ranking",
    "jh_cover_letter_generation",
    "jh_cover_letter_workflow",
    "jh_email_send",
    "jh_email_retry",
}

_RABBITMQ_QUEUES = {
    "jh_scraping_bulk",
    "jh_scraping_realtime",
    "jh_scraping_enrichment",
}


def get_broker_for_queue(queue_name: str) -> str:
    """Get the appropriate broker URL for a given queue.
    
    Args:
        queue_name: The name of the queue
        
    Returns:
        The broker URL for the queue
    """
    if queue_name in _REDIS_QUEUES or queue_name.startswith("jh_cover_letter_") or queue_name.startswith("jh_email_"):
        return settings.celery_broker_url  # Redis
    else:
        return settings.rabbitmq_url or settings.celery_broker_url  # RabbitMQ or fallback to Redis


def dispatch_task(
    celery_app: Celery,
    task_name: str,
    args: Optional[tuple] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    queue: Optional[str] = None,
    **options: Any,
) -> str:
    """Dispatch a task to the appropriate broker based on its queue.
    
    This is a wrapper around Celery's apply_async that handles broker selection.
    
    Args:
        celery_app: The Celery application instance
        task_name: The name of the task to dispatch
        args: Positional arguments for the task
        kwargs: Keyword arguments for the task
        queue: The queue to dispatch the task to
        **options: Additional options to pass to apply_async
        
    Returns:
        The task ID
    """
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}
    
    # Determine the correct broker for the queue
    if queue:
        broker_url = get_broker_for_queue(queue)
        
        # If the queue uses Redis, we need to dispatch using a Redis broker
        if broker_url.startswith("rediss://") or broker_url.startswith("redis://"):
            # Temporarily override the broker URL for this dispatch
            original_broker = os.environ.get("CELERY_BROKER_URL")
            original_rabbitmq = os.environ.get("RABBITMQ_URL")
            os.environ["CELERY_BROKER_URL"] = broker_url
            os.environ["RABBITMQ_URL"] = ""
            
            try:
                result = celery_app.send_task(task_name, args=args, kwargs=kwargs, queue=queue, **options)
                return result.id
            finally:
                # Restore the original broker URL
                if original_broker:
                    os.environ["CELERY_BROKER_URL"] = original_broker
                else:
                    os.environ.pop("CELERY_BROKER_URL", None)
                if original_rabbitmq:
                    os.environ["RABBITMQ_URL"] = original_rabbitmq
                else:
                    os.environ.pop("RABBITMQ_URL", None)
        # If the queue uses RabbitMQ, we need to dispatch using a RabbitMQ broker
        elif broker_url.startswith("amqp://") or broker_url.startswith("amqps://"):
            # Temporarily override the broker URL for this dispatch
            original_broker = os.environ.get("CELERY_BROKER_URL")
            original_rabbitmq = os.environ.get("RABBITMQ_URL")
            os.environ["CELERY_BROKER_URL"] = broker_url
            os.environ["RABBITMQ_URL"] = broker_url
            
            try:
                result = celery_app.send_task(task_name, args=args, kwargs=kwargs, queue=queue, **options)
                return result.id
            finally:
                # Restore the original broker URL
                if original_broker:
                    os.environ["CELERY_BROKER_URL"] = original_broker
                else:
                    os.environ.pop("CELERY_BROKER_URL", None)
                if original_rabbitmq:
                    os.environ["RABBITMQ_URL"] = original_rabbitmq
                else:
                    os.environ.pop("RABBITMQ_URL", None)
    
    # Default dispatch using the configured broker
    result = celery_app.send_task(task_name, args=args, kwargs=kwargs, queue=queue, **options)
    return result.id
