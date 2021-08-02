checks: mypy test

mypy:
	mypy adjust-exif.py

test:
	pytest -v

pre-commit-all:
	pre-commit run -a -v
