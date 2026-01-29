VERSION ?= 0.4.7
WORKFLOW_FILES := .github/workflows/pull-request.yml .github/workflows/promote.yml .github/workflows/release.yml
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
	sed -i \
		-e 's%getdevopspro/github-actions/version-file@v.*%getdevopspro/github-actions/version-file@v$(VERSION)%g' \
		-e 's%getdevopspro/github-actions/command@v.*%getdevopspro/github-actions/command@v$(VERSION)%g' \
		-e 's%getdevopspro/github-actions/buildx-bake@v.*%getdevopspro/github-actions/buildx-bake@v$(VERSION)%g' \
		-e 's%getdevopspro/github-actions/buildx-bake/prepare@v.*%getdevopspro/github-actions/buildx-bake/prepare@v$(VERSION)%g' \
		-e 's%getdevopspro/github-actions/buildx-bake/build@v.*%getdevopspro/github-actions/buildx-bake/build@v$(VERSION)%g' \
		-e 's%getdevopspro/github-actions/buildx-bake/merge@v.*%getdevopspro/github-actions/buildx-bake/merge@v$(VERSION)%g' \
		-e 's%getdevopspro/github-actions/release-version@v.*%getdevopspro/github-actions/release-version@v$(VERSION)%g' \
		-e 's%getdevopspro/github-actions/release-git-push@v.*%getdevopspro/github-actions/release-git-push@v$(VERSION)%g' \
		$(WORKFLOW_FILES)
	git add $(WORKFLOW_FILES)

promote: release-version
	@echo -e "${LIGHTPURPLE}+ make target: $@${RESET}"
	git add Makefile
	git commit -m "chore: bump version to v$(VERSION)" -m "[skip ci]"
	git tag v$(VERSION)
	git push origin HEAD v$(VERSION)

release: release-version promote
