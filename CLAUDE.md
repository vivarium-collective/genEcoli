# genEcoli

Migrates the [vEcoli](https://github.com/CovertLab/vEcoli) whole-cell *E. coli* model to run on [process-bigraph](https://github.com/vivarium-collective/process-bigraph).

## Project Structure

```
genEcoli/
  __init__.py          # Public API re-exports
  interface.py         # Core: EcoliComposite, generate_ecoli_document(), load_ecoli_composite()
  plot.py              # Visualization: plot_ecoli_bigraph(), comparison reports
  types/               # Custom bigraph types (units, quantities, CSR matrices, process wrappers)
    process.py         # OmniStep/OmniProcess wrappers, port translation
    __init__.py        # ECOLI_TYPES registry
out/                   # Generated artifacts (not in git)
  ecoli.pickle         # Full document (schema + state, ~239MB, dill format)
  ecoli.json           # JSON export of document (~16MB)
doc/                   # Documentation artifacts
  ecoli_state_with_partitioning.json
  ecoli_state_without_partitioning.json
tests.py              # Integration tests: generate, load, run 10s, compare with v1
test_types.py          # Unit tests for custom type system
```

## Key Concepts

### State Hierarchy
The ecoli state lives at `state['agents']['0']` and contains:
- **`bulk`** — list of 16,321 molecules, each with `[name, count, ...]`
- **`unique`** — dict with 11 molecule types (`full_chromosome`, `oriC`, `promoter`, `gene`, `active_RNAP`, `RNA`, etc.)
- **`environment`** — `exchange`, `exchange_data`, `media_id`
- **`listeners`** — derived metrics (e.g., `listeners['mass']` has `cell_mass`, `dry_mass`, `protein_mass`, etc.)
- **`boundary`** — cell boundary info
- **`process`** — dict of process instances for partitioned processes
- **`global_time`**, **`timestep`** — simulation time tracking

### Partitioning
12 biological processes use a 3-phase partitioning pattern:
1. **Requester** (`*_requester`) — reads state, writes allocation request
2. **Allocator** (`allocator_1-3`) — coordinates resource availability across all processes
3. **Evolver** (`*_evolver`) — executes with allocated resources, writes final state updates

Partitioned processes: chromosome-replication, complexation, equilibrium, polypeptide-elongation, polypeptide-initiation, protein-degradation, rna-degradation, rna-maturation, transcript-elongation, transcript-initiation, two-component-system.

Non-partitioned processes (run directly): tf-binding, tf-unbinding, metabolism, chromosome-structure.

Total: 54 biological steps.

### Without vs With Partitioning
- **Without partitioning** (32 keys): requesters/evolvers merged into single process names, allocators removed, internal infra steps removed
- **With partitioning** (64 keys): full state including all requesters, evolvers, allocators, unique_updates, global_clock, etc.

The `plot.py` `_build_viz_cell(cell, show_partitioning=False)` controls this in visualizations.

## Commands

```bash
# Run tests
uv run python tests.py
uv run python test_types.py

# Generate ecoli document (requires vEcoli + simData)
uv run python -c "from genEcoli import generate_ecoli_document; generate_ecoli_document()"

# Load and run
uv run python -c "from genEcoli import load_ecoli_composite; e = load_ecoli_composite(); e.run(10.0)"
```

## Dependencies
- Local editable installs: `../vEcoli`, `../process-bigraph`, `../bigraph-schema`
- Python 3.12.9, managed with `uv`
- Saved state uses `dill` (not pickle) for serialization
