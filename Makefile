.PHONY: test lint find-demo

test:
	pytest -q

lint:
	ruff check src tests
	ruff format --check src tests
	mypy src tests

# Find the fictional demo saves bundled under examples/demo.
find-demo:
	remnant2-saves find --user-profile examples/demo --packages-dir examples/demo/Packages
