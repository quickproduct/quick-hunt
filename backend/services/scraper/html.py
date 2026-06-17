"""selectolax-backed drop-in for the subset of the BeautifulSoup API the
scraper actually uses.

Why: HTML parsing (BeautifulSoup + lxml) is the single heaviest CPU/RAM step in
the scraper after Chromium itself. selectolax wraps the C `lexbor` engine and is
roughly 5-30x faster and ~3-5x lighter for the CSS-selector workload these
adapters run (.select / .select_one / .get_text / .get).

Scope: this is NOT a full BeautifulSoup replacement. It supports only the
methods the adapters call — .select, .select_one, .find, .find_all, .get_text,
.text, .get and item access. It parses HTML only; XML/RSS feeds (e.g.
weworkremotely) must keep using real bs4, since lexbor mangles non-HTML tags.

Usage mirrors bs4 so call sites only change their import:
    from services.scraper.html import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")   # the parser arg is accepted & ignored
"""
from __future__ import annotations

from typing import Iterable, Optional, Union

from selectolax.parser import HTMLParser, Node


def _css_from_find(name: Optional[str] = None, attrs: Optional[dict] = None, **kwargs) -> str:
    """Translate a bs4 ``find``/``find_all`` call into a CSS selector.

    Handles the forms the codebase uses: ``find("script", id="__NEXT_DATA__")``
    and ``find_all("a", href=True)``. ``class_`` / ``class`` and ``id`` map to
    CSS class/id; ``attr=True`` becomes an attribute-presence selector
    ``[attr]``; ``attr="v"`` becomes ``[attr="v"]``.
    """
    sel = name or "*"
    merged: dict = dict(attrs or {})
    merged.update(kwargs)

    id_ = merged.pop("id", None)
    if id_ is not None and id_ is not True:
        sel += f"#{id_}"

    cls = merged.pop("class_", None)
    if cls is None:
        cls = merged.pop("class", None)
    if cls:
        classes = cls.split() if isinstance(cls, str) else cls
        for c in classes:
            sel += f".{c}"

    for key, val in merged.items():
        if val is True:
            sel += f"[{key}]"
        elif val is not None and val is not False:
            sel += f'[{key}="{val}"]'
    return sel


class _Node:
    """Wraps a selectolax ``Node`` with a bs4-compatible surface."""

    __slots__ = ("_node",)

    def __init__(self, node: Node) -> None:
        self._node = node

    # -- CSS selection ------------------------------------------------------
    def select(self, css: str) -> list["_Node"]:
        return [_Node(n) for n in self._node.css(css)]

    def select_one(self, css: str) -> Optional["_Node"]:
        n = self._node.css_first(css)
        return _Node(n) if n is not None else None

    def find(self, name: Optional[str] = None, attrs: Optional[dict] = None, **kwargs) -> Optional["_Node"]:
        return self.select_one(_css_from_find(name, attrs, **kwargs))

    def find_all(self, name: Optional[str] = None, attrs: Optional[dict] = None, **kwargs) -> list["_Node"]:
        return self.select(_css_from_find(name, attrs, **kwargs))

    # -- text ---------------------------------------------------------------
    def get_text(self, separator: str = "", strip: bool = False) -> str:
        txt = self._node.text(deep=True, separator=separator, strip=strip)
        if strip and txt:
            txt = txt.strip()
        return txt or ""

    @property
    def text(self) -> str:
        return self._node.text(deep=True) or ""

    # -- attributes ---------------------------------------------------------
    def get(self, attr: str, default=None):
        val = self._node.attributes.get(attr, default)
        # Value-less attributes (e.g. ``disabled``) come back as None; bs4
        # returns "" for those, but callers here only read value attributes.
        return default if val is None else val

    def __getitem__(self, attr: str):
        val = self._node.attributes.get(attr)
        if val is None:
            raise KeyError(attr)
        return val

    @property
    def attrs(self) -> dict:
        return {k: (v if v is not None else "") for k, v in self._node.attributes.items()}

    def __iter__(self) -> Iterable["_Node"]:
        return iter(_Node(n) for n in self._node.iter())

    def __bool__(self) -> bool:
        return self._node is not None


class BeautifulSoup(_Node):
    """Drop-in for ``bs4.BeautifulSoup`` over selectolax (HTML only)."""

    def __init__(self, markup: Union[str, bytes] = "", features: Optional[str] = None, **kwargs) -> None:
        if isinstance(markup, bytes):
            markup = markup.decode("utf-8", "replace")
        tree = HTMLParser(markup or "")
        root = tree.root
        if root is None:  # pathological/empty input — synthesize an empty doc
            root = HTMLParser("<html></html>").root
        super().__init__(root)
