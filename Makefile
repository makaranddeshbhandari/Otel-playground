.DEFAULT_GOAL := help
.PHONY: help up down restart rebuild logs logs-collector logs-gui ps traffic urls health clean

COMPOSE := docker compose

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Build (if needed) and start the whole stack
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory urls

down: ## Stop everything
	$(COMPOSE) down

restart: ## Restart all services
	$(COMPOSE) restart

rebuild: ## Force a full rebuild (use after editing requirements.txt or a Dockerfile)
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

logs: ## Tail logs from every service
	$(COMPOSE) logs -f

logs-collector: ## Tail the collector — YOUR SPANS PRINTED AS TEXT
	$(COMPOSE) logs -f otel-collector

logs-gui: ## Tail the Streamlit GUI
	$(COMPOSE) logs -f gui

ps: ## Show container status
	$(COMPOSE) ps

health: ## Check that every service is answering
	@for probe in "collector|http://localhost:13133" \
	              "jaeger|http://localhost:16686/api/services" \
	              "orders|http://localhost:8001/health" \
	              "payments|http://localhost:8002/health"; do \
		name=$${probe%%|*}; url=$${probe#*|}; \
		code=$$(curl -s -o /dev/null -w "%{http_code}" "$$url" 2>/dev/null || true); \
		if [ "$$code" = "200" ]; then printf "%-9s : %s\n" "$$name" "$$code"; \
		else printf "%-9s : DOWN\n" "$$name"; fi; \
	done

traffic: ## Generate background load (Ctrl-C to stop)
	$(COMPOSE) exec gui python /scripts/traffic.py --url http://orders-api:8001 --rps 2

urls: ## Print the links you need
	@echo ""
	@echo "  🔭  Playground GUI   http://localhost:8501"
	@echo "  🔍  Jaeger UI        http://localhost:16686"
	@echo "  🩺  Collector health http://localhost:13133"
	@echo "  🧾  orders-api docs  http://localhost:8001/docs"
	@echo "  💳  payments-api docs http://localhost:8002/docs"
	@echo ""

clean: ## Stop everything and remove volumes + built images
	$(COMPOSE) down -v --rmi local
