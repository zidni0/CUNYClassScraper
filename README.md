# Hunter Schedule Finder

Python app for scraping CUNY Global Search, filtering Hunter College sections by subject, modality, and schedule availability, then exporting matching sections to JSON and CSV.

## Browser UI

If you want to use the project without working in the terminal:

```bash
python app.py
```

Then open `http://127.0.0.1:5000` in your browser.

On Windows, you can also double-click [start_ui.bat](C:\Users\xzxzi\Pictures\Screenshots\Cuny data scraper\start_ui.bat) to launch the local UI.

## Usage

```bash
python main.py
python main.py --config my_config.json
python main.py --subject CSCI
python main.py --output ./my_results
```

## Notes

- The PRD listed Hunter's institution code as `HUN01`, but the live CUNY Global Search page currently uses `HTR01` as of April 20, 2026. This tool accepts `HUN01` in config and transparently maps it to `HTR01`.
- The PRD example uses subject code `CSCI`, while the live Hunter search dropdown currently uses `CMSC` for the search step and returns `CSCI` in the displayed course labels. This tool accepts `CSCI` and automatically searches `CMSC`.
- The live criteria page requires at least two search criteria. To avoid missing graduate or doctoral sections, the scraper searches each requested subject across undergraduate, graduate, and doctoral careers and then de-duplicates by class number.
- If the requested term is not present on the live `search.jsp` term dropdown, the tool exits cleanly with a "not yet published" message.

## Output

- `results.json`: array of exported section objects, including both matched sections and `tba_review` sections
- `results.csv`: flat export with one row per exported section, including `result_category`, `time_filter_status`, and any section warnings
- `warnings.log`: parser or scrape warnings encountered during the run
- Terminal output: grouped by subject, plus a separate `TBA / Needs Review` block for sections with unresolved meeting times
- Browser UI: live form, on-page results, and download links for JSON, CSV, and warning logs
