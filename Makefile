SHELL := /bin/bash
.PHONY: setup ngspice tools rtl rtl-smoke analog analog-corners dll-clocks layout digital-physical extract fast-rc compare-rc link regression characterize openpll test test-full release release-current release-library
setup:
	./scripts/setup.sh
ngspice:
	python3 scripts/setup_ngspice.py
tools:
	./scripts/env.sh --tools python3 scripts/tool_versions.py
rtl:
	./scripts/env.sh python3 scripts/verify_rtl.py
rtl-smoke:
	./scripts/env.sh python3 scripts/verify_rtl.py --smoke
analog:
	./scripts/env.sh python3 scripts/verify_analog.py --settled-start --resume
analog-corners:
	./scripts/env.sh python3 scripts/verify_analog.py --corners --settled-start --resume
dll-clocks:
	./scripts/env.sh python3 scripts/verify_analog.py --extracted --test dll --clock-corners --settled-start --resume
layout:
	./scripts/env.sh --tools python3 scripts/layout.py
digital-physical:
	./scripts/env.sh --tools python3 scripts/harden.py
	./scripts/env.sh --tools python3 scripts/harden.py --design pfd
extract:
	./scripts/env.sh --tools python3 scripts/extract.py
	./scripts/env.sh --tools python3 scripts/extract.py --digital
fast-rc:
	./scripts/env.sh python3 scripts/rc_fast.py --max-tau-ps 0.1
compare-rc:
	./scripts/env.sh python3 scripts/validate_fast.py
link:
	./scripts/env.sh python3 scripts/simulate_link.py --settled-start --dll-phase
regression:
	./scripts/env.sh python3 scripts/regression.py
characterize:
	./scripts/env.sh python3 scripts/characterize.py
openpll:
	./scripts/env.sh python3 scripts/openpll_clock.py
test:
	./scripts/env.sh python3 -m unittest discover -s tests
test-full:
	@test -x build/tools/exact-rc-venv/bin/python || { echo 'Prepare build/tools/exact-rc-venv using scripts/exact_rc_requirements.txt; see docs/dll-experiments.md.' >&2; exit 1; }
	./scripts/env.sh --ngspice build/tools/exact-rc-venv/bin/python -c 'from importlib.metadata import version; from pathlib import Path; pins=[line.split("==") for line in Path("scripts/exact_rc_requirements.txt").read_text().splitlines() if line.strip()]; assert all(version(name)==expected for name,expected in pins), "Install the pinned scripts/exact_rc_requirements.txt in build/tools/exact-rc-venv"'
	./scripts/env.sh --ngspice build/tools/exact-rc-venv/bin/python -m unittest discover -s tests
release:
	./scripts/env.sh python3 scripts/check_release.py
release-current:
	./scripts/env.sh --ngspice python3 scripts/released_phy.py check
release-library:
	./scripts/env.sh --ngspice python3 scripts/released_phy.py inspect

.PHONY: qualify-300 signoff-300 release-300
qualify-300:
	python3 scripts/check_release_300.py --inventory
signoff-300:
	python3 scripts/check_release_300.py
release-300: signoff-300
	@echo '300 MHz published-view gates passed; host/foundry acceptance remains external.'

.PHONY: qualify-io-300 signoff-io-300 release-io-300
qualify-io-300:
	python3 scripts/check_release_300.py --policy qualification_io_300.json --inventory
signoff-io-300:
	python3 scripts/check_release_300.py --policy qualification_io_300.json
release-io-300: signoff-io-300
	@echo 'Asynchronous LVDS I/O macro gates passed; host/foundry acceptance remains external.'

.PHONY: io-layout io-extract io-signoff io-analog io-analog-extracted io-mismatch io-compare io-publish io-ref-top io-fresh-rc io-receipts
io-layout:
	./scripts/env.sh --tools python3 scripts/layout.py --design openlvds_io_tx,openlvds_io_rx
io-extract:
	./scripts/env.sh --tools python3 scripts/extract.py --design openlvds_io_tx,openlvds_io_rx
io-signoff:
	./scripts/env.sh --tools python3 scripts/layout.py --signoff
io-analog:
	./scripts/env.sh python3 scripts/verify_analog.py --contract io_300.json --corners --resume
io-analog-extracted:
	./scripts/env.sh python3 scripts/verify_analog.py --contract io_300.json --extracted --corners --resume
# Mismatch decks are short, so they start from a solved DC point (ngspice).
io-mismatch:
	./scripts/env.sh --ngspice python3 scripts/verify_analog.py --contract io_300.json --corners --settled-start --resume --test receiver-mc
	./scripts/env.sh --ngspice python3 scripts/verify_analog.py --contract io_300.json --corners --settled-start --resume --test driver-mc
# Nominal comparison runs behind the model, numerical and RC-equivalence gates.
io-compare:
	./scripts/env.sh python3 scripts/verify_analog.py --contract io_300.json --resume
	for t in driver receiver receiver-rate; do ./scripts/env.sh python3 scripts/verify_analog.py --contract io_300.json --resume --raw-rc --test $$t || exit 1; done
	for t in driver receiver receiver-rate; do ./scripts/env.sh --ngspice python3 scripts/verify_analog.py --contract io_300.json --resume --test $$t || exit 1; done
	for t in driver receiver receiver-rate; do ./scripts/env.sh python3 scripts/verify_analog.py --contract io_300.json --resume --profile refined --test $$t || exit 1; done
io-publish:
	./scripts/env.sh python3 scripts/release_io_300.py publish
io-ref-top:
	./scripts/env.sh --tools python3 scripts/harden.py --design io-ref --tag release
io-fresh-rc:
	./scripts/env.sh --tools python3 scripts/release_io_300.py fresh-rc
io-receipts:
	./scripts/env.sh python3 scripts/release_io_300.py receipts
