# Cart-pricing regression walkthrough

Install the PyPI beta in a virtual environment with
`python -m pip install "olyder==0.5.0b1"`. From the root of the Olyder
checkout, run:

```sh
python examples/demo-app/replay_regression.py
```

The replay copies the checked-in spec, implementation, and tests into a
temporary directory. It disables the discount in the copy and expects
`test_discount` to fail because it receives 100 instead of 75. Then it
restores the calculation and verifies that all three tests pass with the same
spec SHA-256. The HTML and JSON evidence is saved under
`.olyder/pricing-proof/discount-regression/` and
`.olyder/pricing-proof/discount-fixed/`. Use `--output path/to/reports`
to save the evidence elsewhere.

To verify the example directly, change to this directory and run:

```bash
olyder plan
olyder verify --allow-exec
```

The spec checks the pricing file and runs the included standard-library unit
tests. The commands run offline and make zero model calls.
