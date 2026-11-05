COMPOSE = docker compose -f deploy/standalone-docker-compose.yml --env-file deploy/.env
PY ?= python3
AGENTS_ENV = set -a; . deploy/agents.env; set +a;

.PHONY: env up down ps logs test register tape lekhak pothi s8 security check ledger doctor

env:            ## fresh secrets in deploy/.env (asks for the admin password)
	deploy/init-env.sh

up:             ## start Switch (Gateway on http://localhost:3200)
	$(COMPOSE) up -d
	@echo "waiting for the API..."; for i in $$(seq 60); do curl -fsS http://127.0.0.1:8100/health >/dev/null 2>&1 && { echo "Switch is up"; exit 0; }; sleep 1; done; echo "Switch didn't come up in 60 s"; exit 1

down:           ## stop Switch, keep its data
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail 80

test:           ## every test, no network (the security tests are in tests/test_agents.py)
	$(PY) -m unittest discover -s tests -t . -v

security:       ## before every push: names, secrets, family data, SQL, ports
	deploy/security.sh

check: test security

doctor:         ## what's still missing before the agents can go live (read-only)
	PY=$(PY) deploy/doctor.sh

ledger:         ## every tape × prompt × model (paid, once each), then ledger.md
	$(PY) -m jaisa.ledger run
	$(PY) -m jaisa.ledger report

register:       ## make register NAME=Tape|Lekhak|Pothi (asks for the registration key)
	$(PY) -m jaisa.register $(NAME)

tape lekhak pothi:  ## run one agent in this terminal (Ctrl-C stops it)
	$(AGENTS_ENV) $(PY) -m jaisa.agents $(shell echo $@ | sed 's/./\U&/')

s8:             ## make s8 FILE=audio/s8-quiet.m4a: Transcribe with and without the vocabulary
	@mkdir -p data
	$(AGENTS_ENV) $(PY) -m jaisa.s8 $(FILE) jaisa-mr-v1 > data/$(basename $(notdir $(FILE))).md
	@echo "wrote data/$(basename $(notdir $(FILE))).md"
