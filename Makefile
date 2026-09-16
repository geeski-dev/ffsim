.PHONY: dev test test-open

dev:
	@./dev

# The default suite: everything that passes on a fresh clone.
#
# Excluded from both targets: test_hypotheses.py, test_h2_separation.py and
# test_h3_knee_recovery.py. They read data/raw/, which is gitignored and absent
# from a fresh clone.
test:
	python3 test_pool_columns.py
	python3 test_next_pick.py
	python3 test_model_influence.py
	python3 test_variance_and_influence.py

# test_backtest.py. Local use only: it requires data/raw/, which is gitignored
# and absent from a fresh clone. Its first three test functions hold 7 checks,
# all of which pass. The fourth function's single check (Chubb 2023 not top-3)
# is a known unsatisfied regression, documented in docs/CHANGE_LEDGER.md, and
# kept failing on purpose -- do not weaken it.
test-open:
	python3 test_backtest.py
