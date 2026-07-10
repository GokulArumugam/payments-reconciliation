.PHONY: demo test clean

demo:
	python3 -m recon generate --seed 42 --count 1000000
	python3 -m recon run
	python3 -m recon verify
	cat data/output/summary.json

test:
	python3 -m pytest -q

clean:
	rm -rf data/input data/output data/oracle .pytest_cache recon/__pycache__ tests/__pycache__
