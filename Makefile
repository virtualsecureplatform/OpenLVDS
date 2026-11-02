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
