.PHONY: dev start restart status health stop logs api web worker observability observability-down

dev:
	@HEALTH_RETRIES="$(HEALTH_RETRIES)" HEALTH_INTERVAL="$(HEALTH_INTERVAL)" SHOW_LOGS="$(SHOW_LOGS)" LINES="$(LINES)" FOLLOW="$(FOLLOW)" SERVICE="$(SERVICE)" bash scripts/run/dev_services.sh

start:
	@bash scripts/run/start_services.sh

restart:
	@bash scripts/run/restart_services.sh

status:
	@bash scripts/run/status_services.sh

health:
	@bash scripts/run/health_services.sh

stop:
	@bash scripts/run/stop_services.sh

logs:
	@SERVICE="$(SERVICE)" LINES="$(LINES)" FOLLOW="$(FOLLOW)" bash scripts/run/logs_services.sh

api:
	cd apps/api && uvicorn src.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd apps/web && npm run dev

worker:
	cd apps/worker && python -m src.entrypoints.main

observability:
	docker compose --profile observability up -d prometheus grafana

observability-down:
	docker compose --profile observability stop prometheus grafana
