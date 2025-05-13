from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep
from process_bigraph import Composite, Process as BigraphProcess, Step as BigraphStep, ProcessTypes

from genEcoli import update_inheritance, register_types, OmniStep, OmniProcess


class TestStep(VivariumStep):
    defaults = {
        'm': 0.994}


class TestProcess(VivariumProcess):
    defaults = {
        'k': 0.11}


    def __init__(self, parameters=None):
        super().__init__(parameters)

        # self.input_ports = ['x', 'y']
        # self.output_ports = ['z']
        

    def ports_schema(self):
        return {
            'x': {'_default': 11.11},
            'y': {'_default': 2.22},
            'z': {'_default': 3}
        }


    def next_update(self, timestep, states):
        state = states
        return {
            'z': state['x']**state['y'] / timestep*2
        }


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

    assert omni.state['a'] == 11.11


if __name__ == '__main__':
    core = ProcessTypes()
    core = register_types(core)

    update_inheritance(TestStep, OmniStep)
    update_inheritance(TestProcess, OmniProcess)

    core.register_processes({
        'test-step': TestStep,
        'test-process': TestProcess})

    test_migrate_process(core)
