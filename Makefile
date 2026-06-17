.PHONY: install-hooks

install-hooks:
	@echo "Installing pre-commit hook..."
	@mkdir -p .git/hooks
	@cp tools/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed successfully."
	@echo "The hook will run build.py and stage diagnostic artifacts before each commit."
