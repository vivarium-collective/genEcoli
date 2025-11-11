.PHONY: install
install:
	@rm -rf .venv; \
	rm -f uv.lock; \
	uv cache clean; \
	uv sync --no-cache --refresh --all-groups