import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    h = hashlib.sha256()
    for item in sorted(Path(path).rglob('*')):
        if item.is_file():
            h.update(str(item.relative_to(path)).encode())
            h.update(item.read_bytes())
    return h.hexdigest()


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    out = root / 'out'
    (out / 'parquet').mkdir(parents=True)
    n = 120
    labels = np.array(['A', 'B', 'C'] * 40)
    rng = np.random.default_rng(123)
    rest = pd.DataFrame({'f1': rng.normal(size=n), 'f2': rng.normal(size=n), 'Label': labels, 'Day': 'rest'})
    hold = pd.DataFrame({'f1': rng.normal(size=30), 'f2': rng.normal(size=30),
                         'Label': np.array(['A', 'B', 'C'] * 10), 'Day': 'Wednesday-28-02-2018'})
    rest.to_parquet(out / 'parquet' / 'rest.parquet', index=False)
    hold.to_parquet(out / 'parquet' / 'hold.parquet', index=False)

    split = load(ROOT / '02_eda_split.py', 'splittrust')
    split.OUT = str(out)
    old_argv = sys.argv
    sys.argv = ['02_eda_split.py']
    try:
        split.main()
    finally:
        sys.argv = old_argv
    first = digest(out)

    for filename in ('train.parquet', 'val.parquet', 'test.parquet', 'unseen_day.parquet'):
        (out / filename).unlink()

    split = load(ROOT / '02_eda_split.py', 'splittrust2')
    split.OUT = str(out)
    old_argv = sys.argv
    sys.argv = ['02_eda_split.py']
    try:
        split.main()
    finally:
        sys.argv = old_argv
    second = digest(out)
    print('reproducibility', 'PASS' if first == second else 'FAIL', first, second)
    assert first == second

    # The split artifacts must preserve the contract used by downstream models.
    train = pd.read_parquet(out / 'train.parquet')
    val = pd.read_parquet(out / 'val.parquet')
    test = pd.read_parquet(out / 'test.parquet')
    unseen = pd.read_parquet(out / 'unseen_day.parquet')
    assert set(train['Day']) == {'rest'}
    assert set(val['Day']) == {'rest'}
    assert set(test['Day']) == {'rest'}
    assert set(unseen['Day']) == {'Wednesday-28-02-2018'}
    assert len(train) == 84 and len(val) == 18 and len(test) == 18
    assert all(pd.api.types.is_float_dtype(train[c]) for c in ('f1', 'f2'))
    assert all(
        np.isfinite(part.drop(columns=['Label', 'Day']).to_numpy()).all()
        for part in (train, val, test, unseen)
    )

    baselines = load(ROOT / '03_baselines.py', 'baselinetrust')
    baselines.OUT = str(out)
    baselines.main()
    results = json.loads((out / 'baseline_results.json').read_text())
    print('baseline_keys', sorted(results))
    assert len(results) == 6 and all(0.0 <= value <= 1.0 for value in results.values())
    print('baseline_synthetic PASS')
