COMPOSE = docker compose -f deploy/standalone-docker-compose.yml --env-file deploy/.env
PY ?= python3
AGENTS_ENV = set -a; . deploy/agents.env; set +a;

.PHONY: env compose up down ps logs rule-log test register senders smoke rehearse ask tape lekhak pothi s8 security check ledger doctor

env:            ## fresh secrets in deploy/.env (asks for the admin password)
	deploy/init-env.sh

compose:        ## Switch's own 0.31.0 Compose file, fetched from GHCR by digest (sha256 checked)
	deploy/fetch-compose.sh

up: compose     ## start Switch (Gateway on http://localhost:3200)
	$(COMPOSE) up -d
	@echo "waiting for the API..."; for i in $$(seq 60); do curl -fsS http://127.0.0.1:8100/health >/dev/null 2>&1 && { echo "Switch is up"; exit 0; }; sleep 1; done; echo "Switch didn't come up in 60 s"; exit 1

down:           ## stop Switch, keep its data
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail 80

rule-log:       ## who set each agent's rule, from Switch's own log (read-only): make rule-log [AGENT=pothi BY=Mom]
	AGENT=$(AGENT) BY=$(BY) PY=$(PY) deploy/rule-log.sh

test:           ## every test, no network (the security tests are in tests/test_agents.py)
	JAISA_COOK=Mom $(PY) -m unittest discover -s tests -t . -v

security:       ## before every push: names, secrets, family data, SQL, ports
	deploy/security.sh

check: test security

doctor:         ## what's still missing before the agents can go live (read-only)
	PY=$(PY) deploy/doctor.sh

ledger:         ## every tape × prompt × model (paid, once each), then ledger.md
	$(AGENTS_ENV) $(PY) -m jaisa.ledger run
	$(AGENTS_ENV) $(PY) -m jaisa.ledger report

register:       ## make register NAME=Tape|Lekhak|Pothi (asks for the registration key)
	$(PY) -m jaisa.register $(NAME)

senders:        ## the agents' Switch sender ids, for deploy/agents.env (read-only)
	deploy/senders.sh

smoke:          ## live: as Tape (stop make tape first), send a TEST transcript to the real Lekhak and check its draft
	$(AGENTS_ENV) $(PY) -m jaisa.probe smoke

rehearse:       ## live: make smoke, then hand the TEST draft to the real Pothi, so Mom can practise in #dev
	$(AGENTS_ENV) $(PY) -m jaisa.probe rehearse

ask:            ## live: make ask AS=Lekhak TO=pothi SAY='ghee 1 cup' (stop that agent first); prints Switch's verdict
	$(AGENTS_ENV) $(PY) -m jaisa.probe ask $(AS) $(TO) $(SAY)

tape lekhak pothi:  ## run one agent in this terminal (Ctrl-C stops it)
	$(AGENTS_ENV) $(PY) -m jaisa.agents $(shell echo $@ | sed 's/./\U&/')

s8:             ## make s8 FILE=audio/s8-quiet.m4a: Transcribe with and without the vocabulary
	@mkdir -p data
	$(AGENTS_ENV) $(PY) -m jaisa.s8 $(FILE) jaisa-mr-v1 > data/$(basename $(notdir $(FILE))).md
	@echo "wrote data/$(basename $(notdir $(FILE))).md"
