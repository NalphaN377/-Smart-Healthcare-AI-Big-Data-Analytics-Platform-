PYTHON ?= .venv/bin/python

.PHONY: setup inspect clean db-up db-init import backend test spark frontend-install frontend-build

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r backend/requirements.txt

inspect:
	$(PYTHON) backend/scripts/inspect_data.py

clean:
	$(PYTHON) backend/scripts/clean_data.py

db-up:
	docker compose up -d mysql

db-init:
	$(PYTHON) backend/scripts/init_database.py

import:
	$(PYTHON) backend/scripts/import_data.py

backend:
	$(PYTHON) backend/run.py

test:
	$(PYTHON) -m pytest backend/tests -q

spark:
	spark-submit --master 'local[*]' spark/jobs/medical_analytics.py

frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build
