# `demo/vendor/wheels/` — the committed wheelhouse (B20)

Every wheel `pip install --no-index --find-links demo/vendor/wheels -r demo/requirements.txt`
needs, for CPython 3.12 on manylinux x86-64. Pure-Python packages carry a `py3-none-any` wheel;
`psycopg-binary` and `pydantic-core` carry compiled `cp312-cp312-manylinux2014_x86_64` wheels.

**Populated once, at build time, with the network** (this is the one and only step in the whole
demo that is allowed to touch it):

```
pip download -d demo/vendor/wheels \
  --only-binary=:all: \
  --python-version 3.12 --implementation cp --abi cp312 \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
  -r <the 20 top-level packages B20 names>
```

`--only-binary=:all:` refuses source distributions — nothing in this wheelhouse compiles at
install time, on this machine or on a fresh clone.

`demo/requirements.txt` was then generated from the resulting wheel filenames: for each wheel,
its canonical PyPI project name, its exact version, and its sha256. That file is what
`./run-demo up` actually installs from; this directory is never read except through it.

**Never re-run `pip download` as part of `up`, `test`, or any other verb.** The wheelhouse is
regenerated only when `demo/requirements.txt` changes on purpose, by hand, at build time.
