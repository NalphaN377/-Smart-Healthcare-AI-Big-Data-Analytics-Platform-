PYTHON ?= .venv/bin/python

.PHONY: setup inspect clean db-up db-init import backend test spark \
	bigdata-start bigdata-upload bigdata-hive bigdata-verify bigdata-stop \
	frontend-install frontend-build

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

bigdata-start:
	scripts/bigdata/start_bigdata.sh

bigdata-upload:
	scripts/bigdata/upload_to_hdfs.sh

bigdata-hive:
	scripts/bigdata/init_hive.sh

bigdata-verify:
	scripts/bigdata/verify_bigdata.sh

bigdata-stop:
	scripts/bigdata/stop_bigdata.sh

frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build
