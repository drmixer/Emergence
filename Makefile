.PHONY: sim-status sim-start sim-stop sim-budget sim-stop-schedule sim-stop-unschedule sim-stop-schedule-local sim-stop-unschedule-local sim-preset report-rebuild report-tech report-story report-story-gemini report-plan report-export compare-condition tournament-select

RUN_MODE ?= real
RUN_ID ?=
RUN_CLASS ?=
CONDITION ?=
SEASON_NUMBER ?=
EPOCH_ID ?=
PRESET ?=
ACTOR ?= make-operator
TUNING_RUN ?=
STOP_AT ?=
SOFT ?= 0
HARD ?= 0

sim-status:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py status

sim-stop:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py stop

sim-budget:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py budget --soft "$(SOFT)" --hard "$(HARD)"

sim-stop-schedule:
	@if [ -z "$(RUN_ID)" ]; then echo "RUN_ID is required"; exit 1; fi
	@if [ -z "$(STOP_AT)" ]; then echo "STOP_AT is required"; exit 1; fi
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py schedule-stop --run-id "$(RUN_ID)" --stop-at "$(STOP_AT)"

sim-stop-unschedule:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py clear-stop-schedule

sim-stop-schedule-local:
	@if [ -z "$(RUN_ID)" ]; then echo "RUN_ID is required"; exit 1; fi
	@if [ -z "$(STOP_AT)" ]; then echo "STOP_AT is required"; exit 1; fi
	@python3 backend/scripts/schedule_guarded_stop.py schedule --run-id "$(RUN_ID)" --stop-at "$(STOP_AT)" --project-root "$(CURDIR)"

sim-stop-unschedule-local:
	@if [ -z "$(RUN_ID)" ]; then echo "RUN_ID is required"; exit 1; fi
	@python3 backend/scripts/schedule_guarded_stop.py unschedule --run-id "$(RUN_ID)"

sim-preset:
	@if [ -z "$(PRESET)" ]; then echo "PRESET is required"; exit 1; fi
	@cd backend && railway run -s backend -- env PYTHONPATH=. venv/bin/python scripts/apply_scarcity_preset.py --preset "$(PRESET)" --actor "$(ACTOR)"

sim-start:
	@cd backend && \
	CMD="railway run -s backend -- venv/bin/python scripts/simulation_control.py start --run-mode \"$(RUN_MODE)\""; \
	if [ -n "$(RUN_ID)" ]; then CMD="$$CMD --run-id \"$(RUN_ID)\""; fi; \
	if [ -n "$(RUN_CLASS)" ]; then CMD="$$CMD --run-class \"$(RUN_CLASS)\""; fi; \
	if [ -n "$(CONDITION)" ]; then CMD="$$CMD --condition \"$(CONDITION)\""; fi; \
	if [ -n "$(SEASON_NUMBER)" ]; then CMD="$$CMD --season-number \"$(SEASON_NUMBER)\""; fi; \
	if [ "$(TUNING_RUN)" = "1" ]; then CMD="$$CMD --tuning-run"; fi; \
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

report-story-gemini:
	@cd backend && railway run -s backend -- venv/bin/python scripts/generate_run_story_report.py --run-id "$(RUN_ID)" \
		--generate-with-gemini \
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

tournament-select:
	@cd backend && railway run -s backend -- venv/bin/python scripts/select_epoch_tournament_candidates.py --epoch-id "$(EPOCH_ID)"
