# genEcoli

Migrates the [vEcoli](https://github.com/CovertLab/vEcoli) whole-cell *E. coli* model to run on [process-bigraph](https://github.com/vivarium-collective/process-bigraph).

## Quick Start

```bash
# Generate the E. coli document (one-time, requires vEcoli + simData)
uv run python -c "from genEcoli import generate_ecoli_document; generate_ecoli_document()"

# Load and run
uv run python -c "
from genEcoli import load_ecoli_composite
ecoli = load_ecoli_composite()
ecoli.run(10.0)
print(f'global_time: {ecoli.state[\"global_time\"]}')
"
```

## API

### `generate_ecoli_document(outpath='out/ecoli.pickle')`

Builds the E. coli composite from vEcoli's `EcoliSim`, migrates all 54 biological steps to process-bigraph format, and saves the result as a standalone document.

Requires vEcoli and `simData.cPickle` to be available.

### `load_ecoli_composite(path='out/ecoli.pickle', core=None)`

Loads a saved document and returns an `EcoliComposite` ready to run.

```python
ecoli = load_ecoli_composite('out/ecoli.pickle')
ecoli.run(10.0)

# Access results
bulk = ecoli.state['agents']['0']['bulk']
print(f"Molecules: {len(bulk['count'])}")
```

### `EcoliComposite`

A `process_bigraph.Composite` subclass that executes v1 biological steps using their native updaters while using the Composite's time advancement and step dependency system.

## Tests

```bash
# Full integration test: generate, load, run, compare with v1
uv run python tests.py

# Type system unit tests
uv run python test_types.py
```

## How It Works

The migration pipeline:

1. **Scan** — Finds all vivarium v1 Process/Step classes in `ecoli.processes` and patches them with v2-compatible interfaces (`OmniStep`, `OmniProcess`).

2. **Build** — Uses `EcoliSim` to load simulation data, instantiate processes, and generate initial cell state (16,321 bulk molecules, unique molecules, environment).

3. **Translate** — Converts the v1 composite into a v2 state dict with process instances, port schemas, wire mappings, and execution ordering (flow dependencies encoded as synthetic wire tokens).

4. **Run** — `EcoliComposite.run()` advances time via the Composite's process scheduler. Each timestep, all 54 steps execute in v1 flow order, applying updates in-place using v1 updaters (`bulk_numpy_updater`, `UniqueNumpyUpdater`, etc.).

## Prerequisites

- Python 3.12.9
- [uv](https://docs.astral.sh/uv/) package manager
- Local editable installs of [vEcoli](https://github.com/CovertLab/vEcoli), [process-bigraph](https://github.com/vivarium-collective/process-bigraph), and [bigraph-schema](https://github.com/vivarium-collective/bigraph-schema)
- `simData.cPickle` at `<vEcoli>/out/kb/simData.cPickle`

## Verification

After 10 simulated seconds, the migrated simulation matches vEcoli with >0.95 Pearson correlation across all bulk molecule count changes.
