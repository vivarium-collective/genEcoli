.PHONY: check
check:
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --no-cache --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@uv run mypy
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry .

.PHONY: build_package
build_package:
	@rm -rf build dist *.egg-info; \
	uv run --no-cache python -m build

.PHONY: upload_package
upload_package:
	@uv publish --no-cache --token $(token)

.PHONY: publish
publish:
	@make sync; \
	make build_package; \
	make upload_package token=$(shell cat ~/.ssh/.pypi-vecoli)

.PHONY: sync
sync:
	@uv cache clean; \
	rm -f uv.lock; \
	uv lock --no-cache; \
	uv sync --no-cache --all-groups

.PHONY:install
install:
	@uv pip install $(package)

.PHONY: uninstall
uninstall:
	@uv run pip-autoremove $(package)