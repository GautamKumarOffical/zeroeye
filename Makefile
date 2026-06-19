.PHONY: install-hooks

install-hooks:
	mkdir -p .git/hooks
	cp tools/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Installed diagnostic pre-commit hook"
