"""Global PHP/Python role keyword filter.

Applied post-fetch across all adapters as a single chokepoint in
scraper/tasks.py. The keyword regex matches the language name or any
common framework/CMS in either ecosystem.

Toggle with settings.role_filter_enabled.
"""

import re

_ROLE_KEYWORDS = re.compile(
    r"\b("
    # PHP ecosystem
    r"php|laravel|symfony|codeigniter|cakephp|yii|zend|"
    r"wordpress|drupal|magento|woocommerce|"
    # Python ecosystem
    r"python|django|flask|fastapi|pyramid|tornado|pyspark|"
    r"sqlalchemy|celery|airflow"
    r")\b",
    re.IGNORECASE,
)


def is_target_role(title: str, description: str | None = None) -> bool:
    """Return True if the title or description mentions PHP/Python.

    Title is checked first (cheap). Description is scanned only as a
    fallback when the title is generic ("Software Engineer", "Backend
    Developer", etc.) to avoid dropping otherwise-valid postings.
    """
    if title and _ROLE_KEYWORDS.search(title):
        return True
    if description and _ROLE_KEYWORDS.search(description):
        return True
    return False
