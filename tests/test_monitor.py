import pytest
from unittest.mock import patch, MagicMock
from monitor import fetch_price


MOCK_HTML_WITH_PRICE = """
<html><body>
  <span class="a-price-whole">34,990<span class="a-decimal-separator">.</span></span>
</body></html>
"""

MOCK_HTML_NO_PRICE = "<html><body><p>Page temporarily unavailable</p></body></html>"


def _mock_response(html: str) -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status = MagicMock()
    return mock


def test_fetch_price_returns_integer():
    with patch("monitor.requests.get", return_value=_mock_response(MOCK_HTML_WITH_PRICE)):
        price = fetch_price("https://www.amazon.in/dp/B0CWVDN3HZ")
    assert price == 34990


def test_fetch_price_strips_commas():
    html = """<html><body>
    <span class="a-price-whole">1,00,000<span class="a-decimal-separator">.</span></span>
    </body></html>"""
    with patch("monitor.requests.get", return_value=_mock_response(html)):
        price = fetch_price("https://www.amazon.in/dp/B0CWVDN3HZ")
    assert price == 100000


def test_fetch_price_raises_when_price_element_missing():
    with patch("monitor.requests.get", return_value=_mock_response(MOCK_HTML_NO_PRICE)):
        with pytest.raises(ValueError, match="Price element not found"):
            fetch_price("https://www.amazon.in/dp/B0CWVDN3HZ")
