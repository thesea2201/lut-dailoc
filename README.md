# Hydroelectric Discharge Plotter

This repository provides a small Python utility for downloading hydroelectric discharge reports from Đà Nẵng's PCTT API and visualising the timeline of `qvevugia` and `qvethubon` values.

## Requirements

- Python 3.9+
- `uv` (https://github.com/astral-sh/uv)
- `matplotlib`

Install dependencies with pip (optional alternative):

```bash
python -m pip install matplotlib
```

## Environment setup with uv

If you prefer managing dependencies with `uv`, initialise a virtual environment and install the requirements file:

```bash
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -r requirements.txt
```

You can then run the script via `uv` without manual activation:

```bash
uv run plot_baocaothuydien.py \
    --start 2025-10-28T00:00:00.000Z \
    --end 2025-10-29T23:59:59.000Z \
    --plant-ids 1,2,3,4 \
    --output baocaothuydien_plot.png
```

## Usage

Run the script with optional query overrides:

```bash
python plot_baocaothuydien.py \
    --start 2025-10-28T00:00:00.000Z \
    --end 2025-10-29T23:59:59.000Z \
    --plant-ids 1,2,3,4 \
    --output baocaothuydien_plot.png
```

### Outputs and caching

The script produces two images:

1. `baocaothuydien_plot.png` – the chronological hourly trend.
2. `baocaothuydien_plot_overlay.png` – hourly overlays of each day for Vu Gia and Thu Bồn.

Both images and the raw payload are cached in `.cache/` (configurable via `--cache-dir`). Cached entries stay valid for one hour by default (`--cache-ttl` in minutes).

- To skip the cache intentionally, pass `--force-refresh`.
- When cached data is reused, the plot image is copied directly from the previous run to avoid regenerating it.

Cache metadata stores the last fetch timestamp and the most recent execution time so the service does not need to be queried more than once per hour.

Arguments:

- `--start`: `ngaybatdau` parameter in ISO8601 format (default `2025-10-28T00:00:00.000Z`).
- `--end`: `ngayketthuc` parameter (default `2025-10-29T23:59:59.000Z`).
- `--plant-ids`: Comma-separated `lst_thuydien_id` list (default `1,2,3,4`).
- `--output`: Output PNG path for the hourly chart (default `baocaothuydien_plot.png`). The overlay image is generated alongside it using the same stem.
- `--show`: Display the chart window after saving.
- `--cache-dir`: Directory to store cached JSON/plots (default `.cache`).
- `--cache-ttl`: Cache freshness window in minutes (default 60).
- `--force-refresh`: Bypass the cache and always fetch new data.

The script saves both images and optionally displays them. Duplicate timestamps in the API response are deduplicated using the last occurrence.

## Deploying on a VPS

1. **Clone and prepare the project**

   ```bash
   git clone <repo-url>
   cd lut-dailoc
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   chmod +x run_report.sh
   ```

2. **Generate the first report manually**

   ```bash
   ./run_report.sh --start 2025-10-28T00:00:00.000Z --end 2025-10-29T23:59:59.000Z --plant-ids 1,2,3,4
   ```

   This produces `public/baocaothuydien_plot.png` and `public/baocaothuydien_plot_overlay.png` alongside `public/index.html`.

3. **Schedule automatic refresh every 15 minutes**

   Edit the crontab (`crontab -e`) and add:

   ```cron
   */15 * * * * /path/to/lut-dailoc/run_report.sh >> /path/to/lut-dailoc/run_report.log 2>&1
   ```

   The script forces a fresh fetch each run, so the images always reflect the latest data.

4. **Serve the reports**

   Point your web server (e.g. Nginx) to the `public/` directory:

   ```nginx
   server {
       listen 80;
       server_name your-domain.example;
       root /path/to/lut-dailoc/public;

       location / {
           try_files $uri $uri/ =404;
       }
   }
   ```

   The bundled `index.html` page references both PNG files and shows the last-modified time of the hourly plot.

5. **Monitoring (optional)**

   Check `run_report.log` periodically or add alerting to ensure the cron job is running without errors.
