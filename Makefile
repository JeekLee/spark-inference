# spark-inference/Makefile
#
# Developer-facing wrapper around `deployment/_run.sh`. Lets you bring
# up / tear down / inspect the entire stack with one command instead of
# cd-ing into each component.
#
# Usage:
#   make local-up                 # start everything in _manifest.local.env
#   make local-down               # stop everything
#   make local-restart            # restart everything
#   make local-ps                 # `docker compose ps` for every component
#   make local-logs               # tail logs for all components
#   make local-logs-c C=gateway   # tail logs for a single component
#                                 # (matches a directory under deployment/)
#
# `dev` and `prod` variants follow the same pattern and read
# `_manifest.dev.env` / `_manifest.prod.env`. Anything you can run via
# `_run.sh <target> <cmd>` is reachable as `make <target>-<cmd>`.
# Add a copy-paste block below to introduce more targets (e.g. staging).

SHELL := /usr/bin/env bash

DEPLOYMENT_DIR := deployment
RUN_SH         := $(DEPLOYMENT_DIR)/_run.sh

# Optional component selector for *-logs-c targets. Pass with `C=<name>`.
C ?=

# Resolve a single component path under deployment/ from its name.
define _find_component
$(shell for cat in inferences audio networks; do \
    [ -d "$(DEPLOYMENT_DIR)/$$cat/$(C)" ] && echo "$$cat/$(C)" && break; \
  done)
endef

.PHONY: help \
        local-up local-down local-restart local-ps local-logs local-logs-c \
        dev-up dev-down dev-restart dev-ps dev-logs dev-logs-c \
        prod-up prod-down prod-restart prod-ps prod-logs prod-logs-c

help:  ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── local ───────────────────────────────────────────────────────────
local-up:       ## Start every component listed in _manifest.local.env
	@$(RUN_SH) local up
local-down:     ## Stop every component listed in _manifest.local.env
	@$(RUN_SH) local down
local-restart:  ## Restart every component listed in _manifest.local.env
	@$(RUN_SH) local restart
local-ps:       ## docker compose ps for every component (local manifest)
	@$(RUN_SH) local ps
local-logs:     ## Tail logs for every component (local manifest)
	@$(RUN_SH) local logs
local-logs-c:   ## Tail logs for one component — make local-logs-c C=<name>
	@test -n "$(C)" || (echo "error: pass a component name as C=<name>" >&2; exit 1)
	@comp="$(call _find_component)"; \
	  test -n "$$comp" || (echo "error: component '$(C)' not found under $(DEPLOYMENT_DIR)/" >&2; exit 1); \
	  cd "$(DEPLOYMENT_DIR)/$$comp" && ./run.sh local logs

# ── dev ─────────────────────────────────────────────────────────────
dev-up:         ## Start every component listed in _manifest.dev.env
	@$(RUN_SH) dev up
dev-down:       ## Stop every component listed in _manifest.dev.env
	@$(RUN_SH) dev down
dev-restart:    ## Restart every component listed in _manifest.dev.env
	@$(RUN_SH) dev restart
dev-ps:         ## docker compose ps for every component (dev manifest)
	@$(RUN_SH) dev ps
dev-logs:       ## Tail logs for every component (dev manifest)
	@$(RUN_SH) dev logs
dev-logs-c:     ## Tail logs for one component — make dev-logs-c C=<name>
	@test -n "$(C)" || (echo "error: pass a component name as C=<name>" >&2; exit 1)
	@comp="$(call _find_component)"; \
	  test -n "$$comp" || (echo "error: component '$(C)' not found under $(DEPLOYMENT_DIR)/" >&2; exit 1); \
	  cd "$(DEPLOYMENT_DIR)/$$comp" && ./run.sh dev logs

# ── prod ────────────────────────────────────────────────────────────
prod-up:        ## Start every component listed in _manifest.prod.env
	@$(RUN_SH) prod up
prod-down:      ## Stop every component listed in _manifest.prod.env
	@$(RUN_SH) prod down
prod-restart:   ## Restart every component listed in _manifest.prod.env
	@$(RUN_SH) prod restart
prod-ps:        ## docker compose ps for every component (prod manifest)
	@$(RUN_SH) prod ps
prod-logs:      ## Tail logs for every component (prod manifest)
	@$(RUN_SH) prod logs
prod-logs-c:    ## Tail logs for one component — make prod-logs-c C=<name>
	@test -n "$(C)" || (echo "error: pass a component name as C=<name>" >&2; exit 1)
	@comp="$(call _find_component)"; \
	  test -n "$$comp" || (echo "error: component '$(C)' not found under $(DEPLOYMENT_DIR)/" >&2; exit 1); \
	  cd "$(DEPLOYMENT_DIR)/$$comp" && ./run.sh prod logs
