"""Integration tests for genEcoli.

Tests the core workflow: generate a document from EcoliSim,
load it into an EcoliComposite, run the simulation, and verify
results match the original vEcoli.
"""

import numpy as np
from contextlib import chdir

from wholecell.utils.filepath import ROOT_PATH
from ecoli.experiments.ecoli_master_sim import EcoliSim
from ecoli.library.schema import not_a_process

from genEcoli import generate_ecoli_document, load_ecoli_composite


DOCUMENT_PATH = 'out/ecoli.pickle'


def test_generate():
    """Generate an E. coli document from EcoliSim."""
    generate_ecoli_document(DOCUMENT_PATH)
    print('test_generate PASSED')


def test_run():
    """Load document and run simulation for 10 seconds."""
    ecoli = load_ecoli_composite(DOCUMENT_PATH)
    bulk_before = ecoli.state['agents']['0']['bulk']['count'].copy()

    ecoli.run(10.0)

    bulk_after = ecoli.state['agents']['0']['bulk']['count']
    changed = (bulk_before != bulk_after).sum()

    print(f"  global_time: {ecoli.state['global_time']}")
    print(f"  bulk molecules changed: {changed} / {len(bulk_before)}")

    assert ecoli.state['global_time'] == 10.0
    assert changed > 0, "No bulk molecules changed"
    print('test_run PASSED')


def test_compare_v1():
    """Compare v2 results against original vEcoli v1 simulation."""
    # Run v1
    with chdir(ROOT_PATH):
        sim = EcoliSim.from_file()
        sim.max_duration = 10
        sim.emitter = 'null'
        sim.divide = False
        sim.build_ecoli()
        v1_initial = sim.generated_initial_state['bulk']['count'].copy()
        sim.run()

    v1_state = sim.ecoli_experiment.state.get_value(condition=not_a_process)
    v1_bulk = v1_state['bulk']['count'].copy()

    # Run v2 from document
    ecoli = load_ecoli_composite(DOCUMENT_PATH)
    v2_initial = ecoli.state['agents']['0']['bulk']['count'].copy()
    ecoli.run(10.0)
    v2_bulk = ecoli.state['agents']['0']['bulk']['count'].copy()

    # Compare
    assert np.array_equal(v1_initial, v2_initial), "Initial states differ"

    v1_changed = (v1_initial != v1_bulk).sum()
    v2_changed = (v2_initial != v2_bulk).sum()
    both = (v1_initial != v1_bulk) & (v2_initial != v2_bulk)

    if both.sum() > 0:
        d1 = v1_bulk[both] - v1_initial[both]
        d2 = v2_bulk[both] - v2_initial[both]
        corr = np.corrcoef(d1.astype(float), d2.astype(float))[0, 1]
    else:
        corr = 0.0

    print(f"  v1 changed: {v1_changed}, v2 changed: {v2_changed}")
    print(f"  both changed: {both.sum()}, correlation: {corr:.4f}")

    assert corr > 0.90, f"Correlation too low: {corr:.4f}"
    print('test_compare_v1 PASSED')


if __name__ == '__main__':
    test_generate()
    test_run()
    test_compare_v1()
