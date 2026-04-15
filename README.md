- Hi, I'm Jorge Perea
- I'm interested in finance, music and data science
- I'm currently learning Python, SQL and iOS Dev

---

## Home Depot MX price scraper

`homedepot_scraper.py` fetches prices for a list of SKUs across multiple
store locations on [homedepot.com.mx](https://www.homedepot.com.mx).

Home Depot Mexico runs on VTEX, which exposes a public catalog API that
returns per-store pricing when you pass the `sc` (sales channel) parameter.
Each physical store / region maps to a distinct sales channel id.

### Install

```bash
pip install -r requirements.txt
```

### Usage

```bash
# Inline arguments
python homedepot_scraper.py --skus 123456 789012 --stores 1 2 3 -o prices.csv

# From files
python homedepot_scraper.py \
    --skus-file skus.example.txt \
    --stores-file stores.example.txt \
    --output prices.csv
```

The CSV output contains one row per (SKU, store) pair with the product name,
price, list price, currency, seller, availability, and the product URL.

### Finding sales channel ids

Open a product page on homedepot.com.mx in your browser's DevTools Network
tab and look for requests that include `?sc=` in their query string. Switch
the store on the site and observe which `sc` value changes — that is the
sales channel id for that store. Add it to `stores.example.txt`.
