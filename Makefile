VERSION ?= 10.0.3
WORKFLOW_FOLDER := .github/workflows
VERSION_REF_FILES := $(WORKFLOW_FOLDER)/*.y*ml README.md
ifneq (,$(findstring xterm,${TERM}))
	RED          := $(shell tput -Txterm setaf 1)
	GREEN        := $(shell tput -Txterm setaf 2)
	YELLOW       := $(shell tput -Txterm setaf 3)
	LIGHTPURPLE  := $(shell tput -Txterm setaf 4)
	RESET := $(shell tput -Txterm sgr0)
else
	RED          := ""
	GREEN        := ""
	YELLOW       := ""
	LIGHTPURPLE  := ""
	RESET        := ""
endif

.PHONY: release-version
release-version:
	@echo -e "${LIGHTPURPLE}+ make target: $@${RESET}"
	sed -i -E \
		-e "s%(getdevopspro/github-actions[^[:space:]\`\"'<>]*)@v[0-9A-Za-z._-]+%\1@v$(VERSION)%g" \
		$(VERSION_REF_FILES)
	git add $(VERSION_REF_FILES)

promote: release-version
	@echo -e "${LIGHTPURPLE}+ make target: $@${RESET}"
	git add Makefile
	git commit -m "chore: bump version to v$(VERSION)" -m "[skip ci]"
	git tag v$(VERSION)
	git push origin HEAD v$(VERSION)

release: release-version promote

.PHONY: test-version
test-version:
	python3 -B -m unittest discover -s tests -p 'test_release_version.py' -v

.PHONY: test-changelog
test-changelog:
	python3 -B -m unittest discover -s tests -p 'test_release_changelog.py' -v

.PHONY: test-report
test-report:
	python3 -B -m unittest discover -s tests -p 'test_build_report.py' -v
	node --test tests/test_build_report_comment.js tests/test_build_baseline.js

.PHONY: test-build-steps
test-build-steps:
	python3 -B -m unittest discover -s tests -p 'test_build_steps.py' -v
