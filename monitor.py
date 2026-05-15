import os
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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


def fetch_price(url: str) -> int:
    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    element = soup.select_one("span.a-price-whole")
    if not element:
        raise ValueError("Price element not found on page")
    raw = element.get_text().replace(",", "").replace(".", "").strip()
    return int(raw)


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
