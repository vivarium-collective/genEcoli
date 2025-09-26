import numpy as np

import json
import pickle

from contextlib import chdir

from unum import Unum
from scipy.sparse import csr_matrix, diags

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep

from bigraph_schema import default, Library
from process_bigraph import Composite, Process as BigraphProcess, Step as BigraphStep, ProcessTypes

from wholecell.utils.filepath import ROOT_PATH
from ecoli.composites.ecoli_master import run_ecoli
from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH

from genEcoli import update_inheritance, register_types, scan_processes, update_processes, migrate_composite, OmniStep, OmniProcess, infer_representation, MISSING_TYPES, ECOLI_TYPES
from genEcoli.types import find_units

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
        'k': default('float', 0.11)}


    def initialize(self, config):
        pass


    def inputs(self):
        return {
            'x': default('float', 11.11),
            'y': default('float', 2.22)}


    def outputs(self):
        return {
            'z': default('float', 3)}


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

    schema = infer_representation(umol, ())

    serialized = core.serialize(
        schema,
        umol)

    deserialized = core.deserialize(
        schema,
        serialized)

    assert umol == deserialized

    uarray = Unum(
        {'umol': -1},
        np.array([3.3, 4.4, 5.5]))

    unum_schema = library.infer(umol)
    uarray_schema = library.infer(uarray)


def test_csr(core):
    for tp in [int, float]:

        tri = diags(
            list(map(range, range(4, 0, -1))), range(4),
            dtype=tp, format="csr")

        schema = infer_representation(tri, ())

        serialized = core.serialize(
            schema,
            tri)

        deserialized = core.deserialize(
            schema,
            serialized)

        assert not (tri != deserialized).nnz


from json import JSONEncoder
class Encoder(JSONEncoder):
    def default(self, o):
        return str(o)


def test_scan_processes(library, core):
    processes = scan_processes('ecoli.processes')

    core = update_processes(
        library,
        core,
        processes)

    assert processes['processes'] and processes['steps']

    return core


def test_generate_migration(library, core):
    with chdir(ROOT_PATH):
        # timeseries = run_ecoli()
        filename = 'default'
        sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + ".json")
        sim.build_ecoli()

    core = test_scan_processes(library, core)
    migrate = migrate_composite(library, core, sim)

    with open("out/migrate.pickle", 'wb') as migrate_file:
        pickle.dump(
            migrate,
            migrate_file)

    return migrate

def test_run_ecoli(library, core, migrate=None):
    if migrate is None:
        with open("out/migrate.pickle", 'rb') as migrate_file:
            migrate = pickle.load(migrate_file)

    import ipdb; ipdb.set_trace()

    composition = library.infer(migrate)

    import ipdb; ipdb.set_trace()

    units = find_units(composition)

    import ipdb; ipdb.set_trace()

    state = library.default(composition)

    import ipdb; ipdb.set_trace()

    composition, state = library.generate({}, migrate)
    document = {
        'composition': composition,
        'state': state}

    with open('out/ecoli-composite.json', 'w') as document_file:
        json.dump(
            document,
            document_file,
            indent=2,
            cls=Encoder,
            skipkeys=True)

    import ipdb; ipdb.set_trace()

    ecoli = Composite(document, core=core)

    import ipdb; ipdb.set_trace()

    ecoli.run(
        10.0)

    import ipdb; ipdb.set_trace()


def initialize_tests():
    library = Library(
        ECOLI_TYPES)

    core = ProcessTypes()
    core = register_types(core)

    update_inheritance(TestStep, OmniStep, library, core)
    update_inheritance(TestProcess, OmniProcess, library, core)

    core.register_processes({
        'test-step': TestStep,
        'test-process': TestProcess})

    return library, core


if __name__ == '__main__':
    library, core = initialize_tests()

    test_migrate_process(core)
    test_unum(core)
    test_csr(core)
    # migrate = test_generate_migration(library, core)
    # test_run_ecoli(library, core, migrate=migrate)
    test_run_ecoli(library, core)
