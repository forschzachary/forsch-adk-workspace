# Hubert ADK workspace — one command per service. Ends the "which python?" guessing.
#
# THE TWO LANES (this is the whole point):
#   * bridge / leads / chat surfaces  -> run IN their container (py3.13, deps baked in the image).
#                                        Tests + python ALWAYS via `docker exec <container> ...`.
#   * Builder + per-agent `adk run`   -> HOST per-agent venvs (py3.12) under agents/<lead>/.venv.
#   Never cross them: a host py3.12 venv will NOT work inside a py3.13 container, and vice-versa.
#
# `make help` lists targets.

.DEFAULT_GOAL := help
.PHONY: help test-bridge test-agents test-chat restart-bridge restart-chat restart-cockpit leads-up

help:  ## list targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

# ---- container lane (py3.13, baked image) -------------------------------------
test-bridge:  ## adk-bridge gateway tests (IN the adk-bridge container)
	docker exec adk-bridge sh -c "cd /workspace/bridge && python -m pytest tests -q"

# ---- host lane (py3.12, per-agent venvs) --------------------------------------
test-agents:  ## per-agent import smoke (host venvs)
	@for a in stability ops social brand website assistant build; do \
	  printf "== %-10s " "$$a"; \
	  agents/$$a/.venv/bin/python -c "import google.adk, forsch.agent_$$a; print('imports OK')" || echo "FAIL"; \
	done

test-chat:  ## flip-chat (adk-chat) tests (host venv, uv-managed py3.12)
	cd chat && .venv/bin/python -m pytest tests -q

# ---- service controls ---------------------------------------------------------
restart-bridge:   ## restart the adk-bridge chat container (:8800)
	docker restart adk-bridge
restart-chat:     ## restart the flip-chat systemd service (:8801)
	systemctl restart adk-chat
restart-cockpit:  ## restart the ADK Builder cockpit (:8780)
	systemctl restart adk-cockpit

# NOTE: adk-leads is STOOD DOWN (compose `future-leads` profile) — rowboatx owns the Memory Lead
# Discord token. When you build the real ADK leads, give adk-leads its OWN token, then:
leads-up:  ## (future) bring up the leads bot — REQUIRES its own DISCORD token, not the Memory Lead one
	cd bridge && docker compose --profile future-leads up -d adk-leads
