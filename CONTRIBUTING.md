# Contributing and reproducing a change

Use a disposable image; never test a mutation on a reference disk. The Python runtime needs no third-party packages. Run the standard-library test suite before and after a change:

```sh
python -m unittest discover -s tests -v
```

For a filesystem behavior change, first add a failing behavioral test, then implement it. Cover byte preservation and failed writes where relevant. Keep format bounds explicit. Optional independent interoperability and actual browser checks are described in `docs/testing.md`.

Build the frontend with the locked dependencies in `web/`. Do not hand-edit minified assets. Build wheels from a fresh stage using `tools/build_wheel.py`, and check the installed package outside the source checkout.

Do not add credentials, personal paths, work images, course books or inherited archives. `tools/public_release.py` uses an explicit allowlist and rejects common credential/private-path patterns. Keep claims about authorship, CI environments, correctness and performance tied to evidence.
