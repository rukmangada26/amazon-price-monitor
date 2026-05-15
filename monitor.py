import os
import re
import smtplib
import subprocess
from email.message import EmailMessage
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PRODUCT_URL = (
    "https://www.amazon.in/Voltas-Inverter-Copper-Adjustable-Anti-dust"
    "/dp/B0CWVDN3HZ"
)
THRESHOLD = 35000
FLAG_FILE = Path(__file__).parent / "notified.flag"

# Tried in order; first match with a parseable price wins.
_PRICE_SELECTORS = [
    "span.a-price-whole",
    ".a-price .a-offscreen",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
]


def _parse_price(text: str) -> int | None:
    """Return the integer rupee amount from a price string, or None if unparseable."""
    integer_part = text.split(".")[0]
    digits = re.sub(r"[^\d]", "", integer_part)
    return int(digits) if digits else None


def fetch_price(url: str) -> int:
    """Fetch the current Amazon India price via ScraperAPI (bypasses bot detection)."""
    api_key = os.environ["SCRAPERAPI_KEY"]
    response = requests.get(
        "http://api.scraperapi.com",
        params={"api_key": api_key, "url": url, "country_code": "in"},
        timeout=60,
    )
    if not response.ok:
        print(f"[ScraperAPI] status={response.status_code} body={response.text[:300]!r}")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for selector in _PRICE_SELECTORS:
        element = soup.select_one(selector)
        if element:
            price = _parse_price(element.get_text())
            if price:
                return price
    raise ValueError("Price element not found on page")


def send_notification(price: int, recipients: list[str]) -> None:
    sender = os.environ["GMAIL_SENDER"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    subject = f"Price Alert: Voltas AC now ₹{price:,}"
    body = (
        f"The Voltas Inverter AC price has dropped below your threshold.\n\n"
        f"Current price: ₹{price:,}\n"
        f"Your threshold: ₹{THRESHOLD:,}\n\n"
        f"Buy now: {PRODUCT_URL}"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())


def main() -> None:
    if FLAG_FILE.exists():
        print("Already notified. Exiting.")
        return

    recipients = os.environ["RECIPIENT_EMAILS"].split(",")
    price = fetch_price(PRODUCT_URL)
    print(f"Current price: ₹{price:,}")

    if price < THRESHOLD:
        print("Price below threshold. Sending notification...")
        send_notification(price, recipients)
        FLAG_FILE.write_text(f"Notified at ₹{price:,}\n")
        subprocess.run(["git", "add", str(FLAG_FILE)], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore: price dropped to ₹{price:,}, notified"],
            check=True,
        )
        subprocess.run(["git", "push"], check=True)
        print("Notification sent and flag committed.")
    else:
        print(f"Price ₹{price:,} is above threshold ₹{THRESHOLD:,}. No action.")


if __name__ == "__main__":
    main()
