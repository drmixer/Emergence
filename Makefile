.PHONY: sim-status sim-start sim-stop

RUN_MODE ?= real
RUN_ID ?=

sim-status:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py status

sim-stop:
	@cd backend && railway run -s backend -- venv/bin/python scripts/simulation_control.py stop

sim-start:
	@cd backend && \
	if [ -n "$(RUN_ID)" ]; then \
		railway run -s backend -- venv/bin/python scripts/simulation_control.py start --run-mode "$(RUN_MODE)" --run-id "$(RUN_ID)"; \
	else \
		railway run -s backend -- venv/bin/python scripts/simulation_control.py start --run-mode "$(RUN_MODE)"; \
	fi
