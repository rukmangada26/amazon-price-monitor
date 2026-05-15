import os
import re
import smtplib
import subprocess
import time
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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# Tried in order; first match wins. Amazon changes layout occasionally.
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
    # Retry up to 3 times — Amazon bot-detection pages return HTTP 200 with no
    # price element; a subsequent request often gets through.
    for attempt in range(3):
        if attempt > 0:
            time.sleep(10)
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for selector in _PRICE_SELECTORS:
            element = soup.select_one(selector)
            if element:
                price = _parse_price(element.get_text())
                if price:
                    return price
    # Log the response snippet to help diagnose what Amazon returned
    print(f"[DEBUG] Response title: {soup.title.string if soup.title else 'no title'}")
    print(f"[DEBUG] Response snippet: {response.text[:1000]!r}")
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
        print(f"Price below threshold. Sending notification...")
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
