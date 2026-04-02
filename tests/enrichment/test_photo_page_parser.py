from __future__ import annotations

import os
import sys

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import photo_pipeline


class _DummyResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


def test_parse_product_page_absolutizes_relative_meta_image(monkeypatch):
    html = """
    <html>
      <head>
        <title>Honeywell 1006187 exact product</title>
        <meta property="product:image" content="/media/catalog/product/670383.jpg" />
      </head>
      <body></body>
    </html>
    """
    monkeypatch.setattr(photo_pipeline.requests, "get", lambda *args, **kwargs: _DummyResponse(html))

    result = photo_pipeline.parse_product_page(
        "https://www.workwearexpress.com/honeywell-1006187-303s",
        pn="1006187",
    )

    assert result["image_url"] == "https://www.workwearexpress.com/media/catalog/product/670383.jpg"


def test_parse_product_page_prefers_product_image_over_banner(monkeypatch):
    html = """
    <html>
      <head>
        <title>Honeywell 033588.17 product page</title>
      </head>
      <body>
        <img src="/iiWWW/admin.nsf/wlkp/B99308BEA0F55610C12574E5004725CA/$file/banner_katalog.jpg" title="Banner" width="900" />
        <img src="/iiWWW/shared.nsf/i/4722965/$FILE/big.jpg" alt="Honeywell Security 033588.17 - Ball-and-socket joint" title="Ball-and-socket joint for wall and corner mounting" width="144" />
      </body>
    </html>
    """
    monkeypatch.setattr(photo_pipeline.requests, "get", lambda *args, **kwargs: _DummyResponse(html))

    result = photo_pipeline.parse_product_page(
        "https://adiglobal.cz/en/produkty110%3A4722965/ball-and-socket-joint-for-wall-and-corner-mounting",
        pn="033588.17",
    )

    assert result["image_url"] == "https://adiglobal.cz/iiWWW/shared.nsf/i/4722965/$FILE/big.jpg"
