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


from monitor import send_notification


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


from monitor import main


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

    with patch("monitor.fetch_price", side_effect=ValueError("Price element not found")), \
         patch("monitor.send_notification") as mock_notify:
        with pytest.raises(ValueError, match="Price element not found"):
            main()

    mock_notify.assert_not_called()
