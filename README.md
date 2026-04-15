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
# Excel output (Store / City / Product / Price + a Details sheet)
python homedepot_scraper.py \
    --skus-file skus.txt \
    --stores-file stores.txt \
    --output prices.xlsx

# CSV output (keeps all fields) — pass any non-.xlsx extension
python homedepot_scraper.py \
    --skus-file skus.txt \
    --stores-file stores.txt \
    --output prices.csv

# Inline arguments
python homedepot_scraper.py --skus 123456 789012 --stores 1 2 3 -o prices.xlsx
```

### Input file formats

`skus.txt` — one SKU per line, optionally `sku,description`:

```
457420,Cemex cemento Portland 25kg
754373,Cemex cemento Portland 50kg
```

`stores.txt` — one store per line as `sales_channel,store_label,city`:

```
5,Home Depot Monterrey Valle,Monterrey
7,Home Depot Chihuahua Periferico,Chihuahua
```

For cities with more than one physical store, add one line per store with
its own `sales_channel` id.

### Finding sales channel ids

Open homedepot.com.mx in your browser's DevTools Network tab and look for
requests that include `?sc=` in their query string. Switch the store on the
site and the `sc` value changes — that is the sales-channel id for that
store. Put it in the first column of `stores.txt`.
