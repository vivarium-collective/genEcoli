import os
import numpy as np

import json
import pickle

from pathlib import Path
from contextlib import chdir

from unum import Unum
from scipy.sparse import csr_matrix, diags

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep

from bigraph_schema import Core, allocate_core
from process_bigraph import Composite, Process as BigraphProcess, Step as BigraphStep

from wholecell.utils.filepath import ROOT_PATH
from ecoli.composites.ecoli_master import run_ecoli
from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH

from genEcoli import update_inheritance, scan_processes, update_processes, migrate_composite, OmniStep, OmniProcess, scan_update, run_ecoli_sim, EcoliComposite, generate_ecoli_document, load_ecoli_composite
from genEcoli.types import find_units, ECOLI_TYPES

class TestStep(VivariumStep):
    defaults = {
        'm': 0.994}


class TestProcess(VivariumProcess):
    defaults = {
        'k': 0.11}


    def __init__(self, parameters=None):
        super().__init__(parameters)


    def ports_schema(self):
        return {
            'x': {'_default': 11.11},
            'y': {'_default': 2.22},
            'z': {'_default': 3}
        }


    def next_update(self, timestep, states):
        return {
            'z': states['x']**states['y'] / timestep*2
        }


class TestBigraph(BigraphProcess):
    config_schema = {
        'k': 'float{0.11}'}


    def initialize(self, config):
        pass


    def inputs(self):
        return {
            'x': 'float{11.11}',
            'y': 'float{2.22}'}


    def outputs(self):
        return {
            'z': 'float{3}'}


    def update(self, state, interval):
        return {
            'z': state['x']**state['y'] / interval*2}


def test_migrate_process(core):
    state = {
        'process': {
            '_type': 'process',
            'address': 'local:test-process',
            'config': {
                'k': 2.222},
            'interval': 1.0,
            'inputs': {
                'x': ['a'],
                'y': ['b']},
            'outputs': {
                'z': ['c']}}}

    omni = Composite({
        'state': state}, core=core)

    # assert omni.state['a'] == 11.11


def test_unum(core):
    umol = Unum(
        {'umol': -1},
        383.3)

    schema = core.infer(umol, ())

    serialized = core.serialize(
        schema,
        umol)

    realize_schema, realize_state = core.realize(
        schema,
        serialized)

    assert umol == realize_state

    uarray = Unum(
        {'umol': -1},
        np.array([3.3, 4.4, 5.5]))

    unum_schema = core.infer(umol)
    uarray_schema = core.infer(uarray)


def test_csr(core):
    for tp in [int, float]:

        tri = diags(
            list(map(range, range(4, 0, -1))), range(4),
            dtype=tp, format="csr")

        schema = core.infer(tri, ())

        serialized = core.serialize(
            schema,
            tri)

        realize_schema, realize_state = core.realize(
            schema,
            serialized)

        assert not (tri != realize_state).nnz


from json import JSONEncoder
class Encoder(JSONEncoder):
    def default(self, o):
        return str(o)


def test_scan_processes(core):
    processes = scan_processes('ecoli.processes')
    core = update_processes(
        core,
        processes)

    assert processes['processes'] and processes['steps']

    return core


def test_generate_migration(core):
    with chdir(ROOT_PATH):
        filename = 'default'
        sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + ".json")
        sim.build_ecoli()

    core = test_scan_processes(core)
    migrate = migrate_composite(core, sim)

    os.makedirs('out', exist_ok=True)
    with open("out/migrate.pickle", 'wb') as migrate_file:
        pickle.dump(
            migrate,
            migrate_file)

    return migrate, sim

def test_run_ecoli(core, migrate=None, sim=None):
    os.makedirs('out', exist_ok=True)

    if migrate is None:
        with open("out/migrate.pickle", 'rb') as migrate_file:
            migrate = pickle.load(migrate_file)

    if sim is None:
        with chdir(ROOT_PATH):
            filename = 'default'
            sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + ".json")
            sim.build_ecoli()

    inferred = core.infer(migrate)

    composite_config = {
        'schema': inferred,
        'state': migrate}

    original_run_steps = Composite.run_steps
    Composite.run_steps = lambda self, x: None
    ecoli = Composite(
        composite_config,
        core=core)
    Composite.run_steps = original_run_steps

    bulk_before = ecoli.state['agents']['0']['bulk']['count'].copy()

    run_ecoli_sim(ecoli, sim.ecoli.flow, 10.0)

    bulk_after = ecoli.state['agents']['0']['bulk']['count']
    changed = (bulk_before != bulk_after).sum()
    print(f"global_time: {ecoli.state['global_time']}")
    print(f"bulk molecules changed: {changed} / {len(bulk_before)}")
    assert ecoli.state['global_time'] == 10.0, f"Expected global_time=10.0, got {ecoli.state['global_time']}"
    assert changed > 0, "No bulk molecule counts changed — simulation did not produce results"


def initialize_tests():
    core = allocate_core()
    core.register_types(ECOLI_TYPES)
    core = scan_update(
        core,
        'ecoli.processes')

    # update_inheritance(TestStep, OmniStep, core)
    # update_inheritance(TestProcess, OmniProcess, core)

    # core.register_links({
    #     'test-step': TestStep,
    #     'test-process': TestProcess})

    return core


if __name__ == '__main__':
    core = initialize_tests()

    # test_migrate_process(core)

    test_unum(core)
    test_csr(core)

    # migrate = test_generate_migration(core)
    # test_run_ecoli(core, migrate=migrate)

    # test_run_ecoli(core)

    migrate, sim = test_generate_migration(core)
    test_run_ecoli(core, migrate=migrate, sim=sim)

    # Test EcoliComposite.run() — uses native Composite execution
    print("\n=== Test EcoliComposite.run() ===")
    inferred = core.infer(migrate)
    ecoli = EcoliComposite({'schema': inferred, 'state': migrate}, core=core)
    bulk_before = ecoli.state['agents']['0']['bulk']['count'].copy()
    ecoli.run(10.0)
    bulk_after = ecoli.state['agents']['0']['bulk']['count']
    changed = (bulk_before != bulk_after).sum()
    print(f"EcoliComposite.run: {changed} / {len(bulk_before)} molecules changed")
    assert changed > 0, "EcoliComposite.run produced no changes"

    # Test save/load round-trip
    print("\n=== Test save/load round-trip ===")
    generate_ecoli_document('out/ecoli.pickle')
    core2 = initialize_tests()
    ecoli2 = load_ecoli_composite('out/ecoli.pickle', core=core2)
    bulk_before2 = ecoli2.state['agents']['0']['bulk']['count'].copy()
    ecoli2.run(10.0)
    bulk_after2 = ecoli2.state['agents']['0']['bulk']['count']
    changed2 = (bulk_before2 != bulk_after2).sum()
    print(f"From pickle: {changed2} / {len(bulk_before2)} molecules changed")
    assert changed2 > 0, "Loaded composite produced no changes"
