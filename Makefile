PYTHON ?= python
export PYTHONPATH := src

RAW    := data/raw/criteo_attribution_dataset.tsv.gz
SAMPLE := data/sample/criteo_sample.tsv.gz
DB     := data/warehouse/ad_auction.db

.PHONY: all etl analyze sample-run test lint clean

## Full dataset: build the warehouse, then run the analyses
all: etl analyze

etl:
	$(PYTHON) -m adauction etl --source $(RAW) --db $(DB)

analyze:
	$(PYTHON) -m adauction analyze --db $(DB) --out reports

## Same pipeline on the 1% sample that ships with the repo (used by CI)
sample-run:
	$(PYTHON) -m adauction etl --source $(SAMPLE) --db data/warehouse/sample.db
	$(PYTHON) -m adauction analyze --db data/warehouse/sample.db --out data/warehouse/sample_reports

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check src tests

clean:
	rm -rf data/warehouse .pytest_cache .ruff_cache
