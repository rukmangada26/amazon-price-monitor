import os
import smtplib
import subprocess
from email.message import EmailMessage
from pathlib import Path

import requests

PRODUCT_URL = (
    "https://www.amazon.in/Voltas-Inverter-Copper-Adjustable-Anti-dust"
    "/dp/B0CWVDN3HZ"
)
ASIN = "B0CWVDN3HZ"
THRESHOLD = 35000
FLAG_FILE = Path(__file__).parent / "notified.flag"

_KEEPA_DOMAIN = 10  # Amazon India


def fetch_price(asin: str) -> int:
    """Return current Amazon India price in rupees via Keepa API."""
    api_key = os.environ["KEEPA_API_KEY"]
    response = requests.get(
        "https://api.keepa.com/product",
        params={"key": api_key, "domain": _KEEPA_DOMAIN, "asin": asin, "stats": 1},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    products = data.get("products", [])
    if not products:
        raise ValueError("Product not found in Keepa response")
    current = products[0].get("stats", {}).get("current", [])
    # current[0] = Amazon direct price; current[1] = Marketplace New
    # Keepa uses -1 for "unavailable". Prices are in paise (INR minor unit).
    amazon_price = current[0] if len(current) > 0 else -1
    if amazon_price < 0 and len(current) > 1:
        amazon_price = current[1]
    if amazon_price < 0:
        raise ValueError("Price not available on Keepa for this ASIN")
    return amazon_price // 100


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
    price = fetch_price(ASIN)
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
