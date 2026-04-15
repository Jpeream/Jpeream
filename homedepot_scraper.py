"""
Home Depot Mexico (homedepot.com.mx) SKU price scraper.

Queries prices for a list of SKUs across multiple store locations.

Home Depot Mexico is built on VTEX, which exposes a public catalog API that
supports per-store pricing through the `sc` (sales channel) query parameter.
Each physical store / region is typically mapped to a distinct sales channel.

Usage:
    python homedepot_scraper.py --skus 123456 789012 --stores 1 2 3
    python homedepot_scraper.py --skus-file skus.txt --stores-file stores.txt \
        --output prices.csv

SKU file format: one SKU per line.
Stores file format: one entry per line, either `sales_channel` or
`sales_channel,label` (label is optional and used for readability).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from typing import Iterable, Iterator

import requests

BASE_URL = "https://www.homedepot.com.mx"
SEARCH_ENDPOINT = "/api/catalog_system/pub/products/search"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

log = logging.getLogger("homedepot_scraper")


@dataclass
class PriceResult:
    sku: str
    store: str
    store_label: str
    product_id: str | None
    product_name: str | None
    available: bool
    price: float | None
    list_price: float | None
    currency: str | None
    seller: str | None
    url: str | None
    error: str | None = None

    @classmethod
    def error_row(cls, sku: str, store: str, label: str, msg: str) -> "PriceResult":
        return cls(
            sku=sku,
            store=store,
            store_label=label,
            product_id=None,
            product_name=None,
            available=False,
            price=None,
            list_price=None,
            currency=None,
            seller=None,
            url=None,
            error=msg,
        )


class HomeDepotMXClient:
    """Thin wrapper around the VTEX public catalog search API."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 20.0,
        max_retries: int = 3,
        backoff: float = 1.5,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _get(self, path: str, params: dict) -> list | dict:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 404:
                    return []
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"retryable status {resp.status_code}")
                resp.raise_for_status()
                # API returns JSON; empty body means "no match"
                if not resp.content:
                    return []
                return resp.json()
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_exc = exc
                sleep_for = self.backoff ** attempt
                log.warning(
                    "Request failed (attempt %d/%d) for %s params=%s: %s. Sleeping %.1fs",
                    attempt, self.max_retries, url, params, exc, sleep_for,
                )
                time.sleep(sleep_for)
        raise RuntimeError(f"Giving up on {url} params={params}: {last_exc}")

    def lookup_sku(self, sku: str, sales_channel: str) -> dict | None:
        """Return the first product matching `sku` in the given sales channel.

        Returns None when the SKU is unknown / unavailable in that channel.
        """
        params = {"fq": f"skuId:{sku}", "sc": sales_channel}
        payload = self._get(SEARCH_ENDPOINT, params)
        if not isinstance(payload, list) or not payload:
            return None
        return payload[0]


def extract_price(product: dict, sku: str) -> PriceResult:
    """Pick the matching SKU item out of a VTEX product payload."""
    product_id = str(product.get("productId") or "") or None
    product_name = product.get("productName")
    link = product.get("link")
    url = f"{BASE_URL}{link}" if link and link.startswith("/") else link

    items = product.get("items") or []
    # Find the exact SKU; fall back to the first item if only one exists.
    match = next((it for it in items if str(it.get("itemId")) == str(sku)), None)
    if match is None and len(items) == 1:
        match = items[0]

    if match is None:
        return PriceResult(
            sku=sku,
            store="",
            store_label="",
            product_id=product_id,
            product_name=product_name,
            available=False,
            price=None,
            list_price=None,
            currency=None,
            seller=None,
            url=url,
            error="sku not found in product items",
        )

    sellers = match.get("sellers") or []
    offer = None
    for s in sellers:
        co = (s.get("commertialOffer") or {})
        if co.get("AvailableQuantity", 0) > 0:
            offer = s
            break
    if offer is None and sellers:
        offer = sellers[0]

    if offer is None:
        return PriceResult(
            sku=sku,
            store="",
            store_label="",
            product_id=product_id,
            product_name=product_name,
            available=False,
            price=None,
            list_price=None,
            currency=None,
            seller=None,
            url=url,
            error="no sellers in response",
        )

    co = offer.get("commertialOffer") or {}
    price = co.get("Price")
    list_price = co.get("ListPrice")
    available = (co.get("AvailableQuantity", 0) or 0) > 0
    currency = co.get("CurrencyCode") or "MXN"

    return PriceResult(
        sku=sku,
        store="",
        store_label="",
        product_id=product_id,
        product_name=product_name,
        available=available,
        price=float(price) if price is not None else None,
        list_price=float(list_price) if list_price is not None else None,
        currency=currency,
        seller=offer.get("sellerName") or offer.get("sellerId"),
        url=url,
    )


def scrape(
    client: HomeDepotMXClient,
    skus: Iterable[str],
    stores: Iterable[tuple[str, str]],
    delay: float = 0.5,
) -> Iterator[PriceResult]:
    """Yield a PriceResult per (sku, store) combination."""
    for sku in skus:
        for sales_channel, label in stores:
            log.info("Fetching sku=%s store=%s (%s)", sku, sales_channel, label)
            try:
                product = client.lookup_sku(sku, sales_channel)
            except Exception as exc:  # network / parsing blew up after retries
                yield PriceResult.error_row(sku, sales_channel, label, str(exc))
                continue

            if product is None:
                yield PriceResult.error_row(
                    sku, sales_channel, label, "sku not returned by api",
                )
                continue

            row = extract_price(product, sku)
            row.store = sales_channel
            row.store_label = label
            yield row

            if delay:
                time.sleep(delay)


def read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]


def parse_stores(raw: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for entry in raw:
        if "," in entry:
            sc, label = entry.split(",", 1)
            out.append((sc.strip(), label.strip()))
        else:
            out.append((entry.strip(), entry.strip()))
    return out


def write_csv(rows: Iterable[PriceResult], path: str) -> int:
    fields = list(PriceResult.__dataclass_fields__.keys())
    count = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
            count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrape Home Depot Mexico SKU prices across store locations.",
    )
    p.add_argument("--skus", nargs="+", help="SKU ids to look up")
    p.add_argument("--skus-file", help="File with one SKU per line")
    p.add_argument(
        "--stores",
        nargs="+",
        help="Store sales-channel ids (e.g. 1 2 3) or 'id,label' pairs",
    )
    p.add_argument(
        "--stores-file",
        help="File with one store per line (sales_channel or sales_channel,label)",
    )
    p.add_argument("--output", "-o", default="prices.csv", help="Output CSV path")
    p.add_argument("--delay", type=float, default=0.5, help="Seconds between requests")
    p.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds")
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--base-url", default=BASE_URL)
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    skus: list[str] = []
    if args.skus:
        skus.extend(args.skus)
    if args.skus_file:
        skus.extend(read_lines(args.skus_file))
    if not skus:
        print("error: provide --skus or --skus-file", file=sys.stderr)
        return 2

    raw_stores: list[str] = []
    if args.stores:
        raw_stores.extend(args.stores)
    if args.stores_file:
        raw_stores.extend(read_lines(args.stores_file))
    if not raw_stores:
        print("error: provide --stores or --stores-file", file=sys.stderr)
        return 2
    stores = parse_stores(raw_stores)

    client = HomeDepotMXClient(
        base_url=args.base_url,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )

    rows = list(scrape(client, skus, stores, delay=args.delay))
    n = write_csv(rows, args.output)
    log.info("Wrote %d rows to %s", n, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
