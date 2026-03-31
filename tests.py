"""Integration tests for genEcoli.

Tests the core workflow: generate a document from EcoliSim,
load it into an EcoliComposite, run the simulation, and verify
results match the original vEcoli. Produces comparison plots.
"""

import time
import numpy as np
from contextlib import chdir

from wholecell.utils.filepath import ROOT_PATH
from ecoli.experiments.ecoli_master_sim import EcoliSim
from ecoli.library.schema import not_a_process

from genEcoli import (
    generate_ecoli_document,
    load_ecoli_composite,
    plot_mass_fractions,
    emitter_to_mass_timeseries,
    v1_query_to_mass_timeseries,
    generate_comparison_report,
)


DOCUMENT_PATH = 'out/ecoli.pickle'
DURATION = 10.0


def test_generate():
    """Generate an E. coli document from EcoliSim."""
    generate_ecoli_document(DOCUMENT_PATH)
    print('test_generate PASSED')


def test_run():
    """Load document and run simulation for 10 seconds."""
    ecoli = load_ecoli_composite(DOCUMENT_PATH)
    bulk_before = ecoli.state['agents']['0']['bulk']['count'].copy()

    ecoli.run(DURATION)

    bulk_after = ecoli.state['agents']['0']['bulk']['count']
    changed = (bulk_before != bulk_after).sum()

    print(f"  global_time: {ecoli.state['global_time']}")
    print(f"  bulk molecules changed: {changed} / {len(bulk_before)}")

    assert ecoli.state['global_time'] == DURATION
    assert changed > 0, "No bulk molecules changed"
    print('test_run PASSED')


def test_compare_v1():
    """Compare v2 results against original vEcoli v1 simulation.
    Produces mass fraction summary plots and reports emitter differences."""

    # Run v1 with timeseries emitter
    with chdir(ROOT_PATH):
        sim = EcoliSim.from_file()
        sim.max_duration = int(DURATION)
        sim.emitter = 'timeseries'
        sim.divide = False
        sim.build_ecoli()
        v1_initial = sim.generated_initial_state['bulk']['count'].copy()
        t0 = time.time()
        sim.run()
        v1_runtime = time.time() - t0

    v1_state = sim.ecoli_experiment.state.get_value(condition=not_a_process)
    v1_bulk = v1_state['bulk']['count'].copy()
    v1_timeseries = sim.query()
    v1_mass = v1_query_to_mass_timeseries(v1_timeseries)

    # Run v2 from document
    ecoli = load_ecoli_composite(DOCUMENT_PATH)
    v2_initial = ecoli.state['agents']['0']['bulk']['count'].copy()
    t0 = time.time()
    ecoli.run(DURATION)
    v2_runtime = time.time() - t0
    v2_bulk = ecoli.state['agents']['0']['bulk']['count'].copy()
    v2_mass = emitter_to_mass_timeseries(ecoli.emitter)

    # --- Compare bulk counts ---
    assert np.array_equal(v1_initial, v2_initial), "Initial states differ"

    both = (v1_initial != v1_bulk) & (v2_initial != v2_bulk)
    if both.sum() > 0:
        d1 = v1_bulk[both] - v1_initial[both]
        d2 = v2_bulk[both] - v2_initial[both]
        bulk_corr = np.corrcoef(d1.astype(float), d2.astype(float))[0, 1]
    else:
        bulk_corr = 0.0

    v1_changed = (v1_initial != v1_bulk).sum()
    v2_changed = (v2_initial != v2_bulk).sum()

    print(f"  v1: {v1_runtime:.2f}s, v2: {v2_runtime:.2f}s ({v2_runtime/v1_runtime:.1f}x)")
    print(f"  v1 changed: {v1_changed}, v2 changed: {v2_changed}, correlation: {bulk_corr:.4f}")

    assert bulk_corr > 0.90, f"Bulk correlation too low: {bulk_corr:.4f}"

    # Mass fraction comparison plot
    plot_mass_fractions(
        {'vEcoli (v1)': v1_mass, 'genEcoli (v2)': v2_mass},
        outpath='out/mass_fraction_summary.png')

    # HTML comparison report
    generate_comparison_report(
        v1_mass=v1_mass,
        v2_mass=v2_mass,
        v1_runtime=v1_runtime,
        v2_runtime=v2_runtime,
        v1_changed=v1_changed,
        v2_changed=v2_changed,
        both_changed=both.sum(),
        bulk_corr=bulk_corr,
        duration=DURATION,
        outdir='out')

    print('test_compare_v1 PASSED')


if __name__ == '__main__':
    test_generate()
    test_run()
    test_compare_v1()
