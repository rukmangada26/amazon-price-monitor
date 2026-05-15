import pytest
from unittest.mock import patch, MagicMock
from monitor import fetch_price, send_notification, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_pairs(price: int) -> list:
    """Build a minimal Keepa csv pair list: [fake_time, price]."""
    return [1000, price]


def _keepa_response(amazon_price: int = 3499000, new_price: int = -1) -> MagicMock:
    """Mock a Keepa API response. Prices are in paise (INR minor unit)."""
    mock = MagicMock()
    mock.ok = True
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "products": [{"csv": [_csv_pairs(amazon_price), _csv_pairs(new_price)]}]
    }
    return mock


def _empty_keepa_response() -> MagicMock:
    mock = MagicMock()
    mock.ok = True
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"products": []}
    return mock


# ---------------------------------------------------------------------------
# fetch_price
# ---------------------------------------------------------------------------

def test_fetch_price_converts_paise_to_rupees(monkeypatch):
    monkeypatch.setenv("KEEPA_API_KEY", "test-key")
    with patch("monitor.requests.get", return_value=_keepa_response(3499000)):
        price = fetch_price("B0CWVDN3HZ")
    assert price == 34990


def test_fetch_price_falls_back_to_marketplace_when_amazon_unavailable(monkeypatch):
    monkeypatch.setenv("KEEPA_API_KEY", "test-key")
    with patch("monitor.requests.get", return_value=_keepa_response(-1, 3350000)):
        price = fetch_price("B0CWVDN3HZ")
    assert price == 33500


def test_fetch_price_raises_when_product_not_in_keepa(monkeypatch):
    monkeypatch.setenv("KEEPA_API_KEY", "test-key")
    with patch("monitor.requests.get", return_value=_empty_keepa_response()):
        with pytest.raises(ValueError, match="Product not found"):
            fetch_price("B0CWVDN3HZ")


def test_fetch_price_raises_when_both_prices_unavailable(monkeypatch):
    monkeypatch.setenv("KEEPA_API_KEY", "test-key")
    with patch("monitor.requests.get", return_value=_keepa_response(-1, -1)):
        with pytest.raises(ValueError, match="Price not available"):
            fetch_price("B0CWVDN3HZ")


def test_fetch_price_calls_keepa_with_correct_params(monkeypatch):
    monkeypatch.setenv("KEEPA_API_KEY", "my-secret-key")
    with patch("monitor.requests.get", return_value=_keepa_response()) as mock_get:
        fetch_price("B0CWVDN3HZ")
    params = mock_get.call_args[1]["params"]
    assert params["key"] == "my-secret-key"
    assert params["domain"] == 10
    assert params["asin"] == "B0CWVDN3HZ"
    assert "stats" not in params


# ---------------------------------------------------------------------------
# send_notification
# ---------------------------------------------------------------------------

def test_send_notification_connects_to_gmail_and_sends(monkeypatch):
    monkeypatch.setenv("GMAIL_SENDER", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password-123")
    recipients = ["a@gmail.com", "b@gmail.com", "c@gmail.com"]

    with patch("monitor.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        send_notification(34000, recipients)

    mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("sender@gmail.com", "app-password-123")

    sendmail_args = mock_server.sendmail.call_args[0]
    assert sendmail_args[0] == "sender@gmail.com"
    assert sendmail_args[1] == recipients
    assert "34,000" in sendmail_args[2]
    assert "35,000" in sendmail_args[2]
    assert "B0CWVDN3HZ" in sendmail_args[2]


def test_send_notification_subject_contains_price(monkeypatch):
    monkeypatch.setenv("GMAIL_SENDER", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password-123")

    with patch("monitor.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        send_notification(33500, ["x@gmail.com"])

    _, _, raw_message = mock_server.sendmail.call_args[0]
    assert "33,500" in raw_message


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def test_main_skips_if_flag_exists(tmp_path, monkeypatch):
    flag = tmp_path / "notified.flag"
    flag.write_text("already notified")
    monkeypatch.setattr("monitor.FLAG_FILE", flag)

    with patch("monitor.fetch_price") as mock_fetch:
        main()

    mock_fetch.assert_not_called()


def test_main_does_not_notify_when_price_at_or_above_threshold(tmp_path, monkeypatch):
    flag = tmp_path / "notified.flag"
    monkeypatch.setattr("monitor.FLAG_FILE", flag)
    monkeypatch.setenv("RECIPIENT_EMAILS", "a@gmail.com,b@gmail.com,c@gmail.com")

    with patch("monitor.fetch_price", return_value=35000), \
         patch("monitor.send_notification") as mock_notify:
        main()

    mock_notify.assert_not_called()
    assert not flag.exists()


def test_main_notifies_and_commits_flag_when_price_below_threshold(tmp_path, monkeypatch):
    flag = tmp_path / "notified.flag"
    monkeypatch.setattr("monitor.FLAG_FILE", flag)
    monkeypatch.setenv("GMAIL_SENDER", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password-123")
    monkeypatch.setenv("RECIPIENT_EMAILS", "a@gmail.com,b@gmail.com,c@gmail.com")

    with patch("monitor.fetch_price", return_value=34000), \
         patch("monitor.send_notification") as mock_notify, \
         patch("monitor.subprocess.run") as mock_run:
        main()

    mock_notify.assert_called_once_with(34000, ["a@gmail.com", "b@gmail.com", "c@gmail.com"])
    assert flag.exists()

    git_commands = [call[0][0] for call in mock_run.call_args_list]
    assert ["git", "add", str(flag)] in git_commands
    assert any("commit" in cmd for cmd in git_commands)
    assert any("push" in cmd for cmd in git_commands)


def test_main_exits_with_error_when_fetch_fails(tmp_path, monkeypatch):
    flag = tmp_path / "notified.flag"
    monkeypatch.setattr("monitor.FLAG_FILE", flag)
    monkeypatch.setenv("RECIPIENT_EMAILS", "a@gmail.com")

    with patch("monitor.fetch_price", side_effect=ValueError("Price not available")), \
         patch("monitor.send_notification") as mock_notify:
        with pytest.raises(ValueError, match="Price not available"):
            main()

    mock_notify.assert_not_called()
