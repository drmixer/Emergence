.PHONY: sim-status sim-start sim-stop report-rebuild report-tech report-story report-plan report-export compare-condition

RUN_MODE ?= real
RUN_ID ?=
CONDITION ?=
SEASON_NUMBER ?=

sim-status:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py status

sim-stop:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py stop

sim-start:
	@cd backend && \
	CMD="railway run -s backend -- venv/bin/python scripts/simulation_control.py start --run-mode \"$(RUN_MODE)\""; \
	if [ -n "$(RUN_ID)" ]; then CMD="$$CMD --run-id \"$(RUN_ID)\""; fi; \
	if [ -n "$(CONDITION)" ]; then CMD="$$CMD --condition \"$(CONDITION)\""; fi; \
	if [ -n "$(SEASON_NUMBER)" ]; then CMD="$$CMD --season-number \"$(SEASON_NUMBER)\""; fi; \
	eval $$CMD

report-rebuild:
	@cd backend && railway run -s backend -- venv/bin/python scripts/rebuild_run_bundle.py --run-id "$(RUN_ID)" \
		$(if $(CONDITION),--condition "$(CONDITION)",) \
		$(if $(SEASON_NUMBER),--season-number "$(SEASON_NUMBER)",)

report-tech:
	@cd backend && railway run -s backend -- venv/bin/python scripts/generate_run_technical_report.py --run-id "$(RUN_ID)" \
		$(if $(CONDITION),--condition "$(CONDITION)",) \
		$(if $(SEASON_NUMBER),--season-number "$(SEASON_NUMBER)",)

report-story:
	@cd backend && railway run -s backend -- venv/bin/python scripts/generate_run_story_report.py --run-id "$(RUN_ID)" \
		$(if $(CONDITION),--condition "$(CONDITION)",) \
		$(if $(SEASON_NUMBER),--season-number "$(SEASON_NUMBER)",)

report-plan:
	@cd backend && railway run -s backend -- venv/bin/python scripts/generate_next_run_plan.py --run-id "$(RUN_ID)" \
		$(if $(CONDITION),--condition "$(CONDITION)",)

report-export:
	@cd backend && railway run -s backend -- venv/bin/python scripts/export_run_report.py --run-id "$(RUN_ID)" \
		$(if $(CONDITION),--condition "$(CONDITION)",) \
		$(if $(SEASON_NUMBER),--season-number "$(SEASON_NUMBER)",)

compare-condition:
	@cd backend && railway run -s backend -- venv/bin/python scripts/compare_conditions.py --condition "$(CONDITION)" \
		$(if $(SEASON_NUMBER),--season-number "$(SEASON_NUMBER)",)
