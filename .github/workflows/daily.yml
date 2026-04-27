name: Daily Soccer Value Run

on:
  schedule:
    # 09:00 UTC = 19:00 Melbourne (winter) / 20:00 (summer)
    # Hits late afternoon European fixtures + evening South American
    - cron: '0 9 * * *'
    # 21:00 UTC = 07:00 Melbourne — covers overnight US/JP fixtures
    - cron: '0 21 * * *'
  workflow_dispatch:  # let us trigger manually too

jobs:
  run:
    runs-on: ubuntu-latest
    permissions:
      contents: write   # needs to commit results back
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4 lxml

      - name: Run tests
        run: python -m src.tests

      - name: Run daily pipeline
        env:
          ODDS_API_KEY: ${{ secrets.ODDS_API_KEY }}
        run: python -m src.run_daily

      - name: Commit results
        run: |
          git config user.name "soccer-value-bot"
          git config user.email "bot@users.noreply.github.com"
          git add results/ data/ docs/ || true
          git diff --staged --quiet || git commit -m "daily run $(date -u +%Y-%m-%d_%H-%M)"
          git push
