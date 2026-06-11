.PHONY: cli-assets cli-wheelhouse

cli-assets:
	python cli/scripts/prepare_assets.py

cli-wheelhouse: cli-assets
	rm -rf dist/amber-wheelhouse
	rm -rf cli/build cli/amber_runtime.egg-info
	mkdir -p dist/amber-wheelhouse
	uv build --wheel --out-dir dist/amber-wheelhouse sdk
	uv build --wheel --out-dir dist/amber-wheelhouse cli
	@printf '\nCustomer install command:\n'
	@printf 'python -m pip install --find-links %s/dist/amber-wheelhouse amber-runtime\n' "$$(pwd)"
