# GitHub Tech Radar — pipeline orchestration
#
# Stages:
#   scrape   -> data/raw/<date>.json        (no LLM, network only)
#   extract  -> data/tech_signals.duckdb     (LLM enrichment)
#   dashboard-> Streamlit UI over the DuckDB dataset
#
# Usage examples:
#   make install      # install Python dependencies
#   make pipeline     # scrape + extract (end-to-end data refresh)
#   make dashboard    # serve the Streamlit dashboard
#   make all          # pipeline, then serve the dashboard
#   make help         # list every target

# Use `python` by default; override with `make PYTHON=python3 ...` if needed.
PYTHON ?= python
STREAMLIT_PORT ?= 8501
# Pass extra flags through, e.g. `make extract ARGS="--force"`.
ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help install scrape extract pipeline dashboard serve all run clean clean-db clean-raw

help: ## Show this help
	@echo "GitHub Tech Radar — available commands:"
	@echo ""
	@echo "  make install      Install Python dependencies from requirements.txt"
	@echo "  make scrape       Scrape GitHub trending into data/raw/<date>.json"
	@echo "  make extract      LLM-enrich raw repos into the DuckDB dataset"
	@echo "  make pipeline     Run scrape + extract end-to-end"
	@echo "  make dashboard    Serve the Streamlit dashboard"
	@echo "  make all          Run the full pipeline, then serve the dashboard"
	@echo "  make clean        Remove generated data (raw JSON + DuckDB)"
	@echo ""
	@echo "  Variables: PYTHON=$(PYTHON)  STREAMLIT_PORT=$(STREAMLIT_PORT)"
	@echo "  Pass flags with ARGS, e.g.  make extract ARGS=\"--force\""

install: ## Install Python dependencies
	$(PYTHON) -m pip install -r requirements.txt

scrape: ## Scrape GitHub trending -> data/raw/<date>.json
	$(PYTHON) -m src.scraper $(ARGS)

extract: ## LLM-enrich raw repos -> DuckDB
	$(PYTHON) -m src.extractor $(ARGS)

pipeline: scrape extract ## Run the full data pipeline (scrape + extract)
	@echo "[make] pipeline complete — DuckDB dataset refreshed."

dashboard: ## Serve the Streamlit dashboard
	$(PYTHON) -m streamlit run dashboard/app.py --server.port $(STREAMLIT_PORT)

serve: dashboard ## Alias for `dashboard`

all: pipeline dashboard ## Refresh data, then serve the dashboard

run: all ## Alias for `all`

clean-raw: ## Delete scraped raw JSON files
	-rm -f data/raw/*.json

clean-db: ## Delete the DuckDB dataset
	-rm -f data/tech_signals.duckdb

clean: clean-raw clean-db ## Delete all generated data
	@echo "[make] removed generated data (raw JSON + DuckDB)."
