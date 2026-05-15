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


def _latest_csv_price(csv_pairs: list) -> int:
    """Return the last non-(-1) price from a Keepa csv pair list [time, price, ...], or -1."""
    # Prices sit at odd indices (1, 3, 5, …); walk backwards to find the most recent.
    for i in range(len(csv_pairs) - 1, 0, -2):
        if csv_pairs[i] != -1:
            return csv_pairs[i]
    return -1


def fetch_price(asin: str) -> int:
    """Return current Amazon India price in rupees via Keepa API."""
    api_key = os.environ["KEEPA_API_KEY"]
    response = requests.get(
        "https://api.keepa.com/product",
        params={"key": api_key, "domain": _KEEPA_DOMAIN, "asin": asin},
        timeout=15,
    )
    if not response.ok:
        print(f"[Keepa] status={response.status_code} body={response.text[:500]!r}")
    response.raise_for_status()
    data = response.json()
    products = data.get("products", [])
    if not products:
        raise ValueError("Product not found in Keepa response")
    # csv[0] = Amazon direct price history; csv[1] = Marketplace New
    # Keepa stores prices as [keepaTime, price, keepaTime, price, …] in paise.
    csv = products[0].get("csv") or []
    amazon_price = _latest_csv_price(csv[0]) if len(csv) > 0 else -1
    if amazon_price < 0:
        amazon_price = _latest_csv_price(csv[1]) if len(csv) > 1 else -1
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
