from abc import abstractmethod
import inspect
import copy

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep

from bigraph_schema import deep_merge, Edge as BigraphEdge
from bigraph_schema.methods import infer, render
from bigraph_schema.protocols import local_lookup_module
from process_bigraph import ProcessTypes, Process as BigraphProcess, Step as BigraphStep

from genEcoli.infer_representation import translate_ports, collapse_defaults # , infer_schema


__all__ = [
    'OmniStep',
    'OmniProcess',
    'Resolver'
]

class Revert:
    pass 


class Resolver(BigraphStep):
    """Takes PartitionedProcess updates and somehow emits 
    a single update that is a resolution of their demands.

    TODO: look at Allocator for Resolver
    """
    pass


# class OmniStep(VivariumStep, BigraphStep):
class OmniStep(BigraphStep):
    """This class allows v1 steps to run as v2 steps"""

    config_schema = {} 
    _ports = {
        "inputs": [],
        "outputs": []
    }

    def __init__(self, parameters=None, config=None, core=None) -> None:
        parameters = parameters or config
        config = config or parameters

        super().__init__(
            config=config,
            core=core)

    def inputs(self):
        """Expects:
        self.input_port_data = {port_name: {_default: ...}}
        """
        return translate_ports(
            self.ports_schema(),
            name=self.name)

    def outputs(self):
        """Use specific ports if defined, otherwise return bidirectional ports"""
        return translate_ports(
            self.ports_schema(),
            name=self.name)
    
    def initial_state(self):
        return collapse_defaults(self.input_port_data)
    
    @abstractmethod
    def update(self, state):
        return {}


class OmniProcess(BigraphProcess):
    # This class allows v1 processes to run as v2 processes
    config_schema = {}
    _ports = {
        "inputs": [],
        "outputs": []
    }

    def __init__(self, parameters=None, config=None, core=None) -> None:
        parameters = parameters or config
        config = config or parameters

        super().__init__(
            config=config,
            core=core)

    def inputs(self):
        return translate_ports(
            self.ports_schema(),
            name=self.name)

    def outputs(self):
        """Use specific ports if defined, otherwise return bidirectional ports"""
        return translate_ports(
            self.ports_schema(),
            name=self.name)
    
    def initial_state(self):
        return collapse_defaults(self.input_port_data)
    
    def update(self, state, interval):
        return self.next_update(interval, state)


def update_inheritance(cls, new_base, library, core):
    if new_base in cls.__bases__:
        return

    # replace the base class with the new base
    cls.__bases__ = cls.__bases__ + (new_base,)

    # store the existing init
    init = cls.__init__

    core = core
    library = library

    # wrap the existing init with an init that accepts arguments
    # specific to process-bigraph
    def new_init(self, config=None, parameters=None, core=core):
        config = config or parameters
        parameters = parameters or config
        core = core

        try:
            init(self, parameters=parameters)
        except Exception as e:
            import ipdb; ipdb.set_trace()

        self._config = config

        new_base.__init__(
            self,
            config,
            parameters,
            core=core)

    # replace the existing init with the new init
    cls.__init__ = new_init


def find_instances(module, visited=None):
    steps = {}
    processes = {}
    visited = visited or set([])

    for key in dir(module):
        value = getattr(module, key)
        if isinstance(value, type) and issubclass(value, VivariumStep) and not value == VivariumStep:
            steps[key] = value
        elif isinstance(value, type) and issubclass(value, VivariumProcess) and not value == VivariumProcess:
            processes[key] = value
        elif inspect.ismodule(value) and value.__name__.startswith('ecoli') and value not in visited:
            visited.add(value)
            substeps, subprocesses = find_instances(
                value,
                visited)

            steps.update(substeps)
            processes.update(subprocesses)

    return steps, processes


def scan_processes(path):
    module = local_lookup_module(path)
    steps, processes = find_instances(module)
    scan = {
        'processes': processes,
        'steps': steps}

    return scan


def update_processes(library, core, processes):
    for process_name, process in processes.get('processes', {}).items():
        update_inheritance(process, OmniProcess, library, core)
        process.core = core
        core.register_process(process_name, process)

    for step_name, step in processes.get('steps', {}).items():
        update_inheritance(step, OmniStep, library, core)
        step.core = core
        core.register_process(step_name, step)

    return core


def list_paths(path):
    if isinstance(path, tuple):
        return list(path)
    elif isinstance(path, dict):
        result = {}
        for key, subpath in path.items():
            result[key] = list_paths(subpath)
        return result


# TODO: ask Sean where the units are?
#   ie cell density?

def translate_processes(library, core, tree, topology=None):
    if isinstance(tree, BigraphEdge):
        cls = type(tree)

        if not hasattr(cls, 'config_schema') or not cls.config_schema:
            inferred_schema = library.infer(tree.parameters)
            cls.config_schema = library.render(inferred_schema)

        if not hasattr(tree, '_config'):
            tree._config = tree.parameters

        type_name = 'step'
        state = {}
        if isinstance(tree, BigraphProcess):
            type_name = 'process'
            state['interval'] = 1.0

        if topology is None:
            topology = tree.topology

        wires = list_paths(topology)

        # tree.__init__(
        #     parameters=config,
        #     config=config,
        #     core=core)

        process_class = cls.__name__

        # config_schema = infer(tree.parameters)

        config = translate_processes(
            library,
            core,
            tree.parameters)

        state.update({
            '_type': type_name,
            'address': f'local:{process_class}',
            'config': config,
            '_inputs': tree.inputs(),
            '_outputs': tree.outputs(),
            'inputs': wires,
            'outputs': wires})

            # 'outputs': wires,
            # 'instance': tree})

        return state

    elif isinstance(tree, dict):
        result = {}
        for key, subtree in tree.items():
            result[key] = translate_processes(
                library,
                core,
                subtree,
                topology[key] if topology else None)

        return result

    else:
        return tree


def migrate_composite(library, core, sim):
    processes = translate_processes(
        library,
        core,
        sim.ecoli.processes,
        sim.ecoli.topology)

    steps = translate_processes(
        library,
        core,
        sim.ecoli.steps,
        sim.ecoli.topology)

    state = deep_merge(
        processes,
        steps)

    state = deep_merge(
        state,
        sim.generated_initial_state)

    return state
