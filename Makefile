#!make

VERSION ?= $(shell git describe --tags --exact-match 2>/dev/null || git rev-parse --abbrev-ref HEAD)

.PHONY: compress
compress:
	tar --no-xattrs \
		--exclude='.git*' \
		--exclude="*.tar.gz" \
		--exclude="*__pycache__" \
		--exclude=".pytest_cache*" \
		--exclude="*.sh" \
		--exclude=".idea" \
		--exclude="data" \
		--exclude="LICENSE" \
		--exclude="config/*.y*ml" \
		-zcvf tomodo-$(VERSION).tar.gz .

.PHONY: pip-export
pip-export:
	poetry export  --without-hashes --without-urls --with dev > requirements.txt
