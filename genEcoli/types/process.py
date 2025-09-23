import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node, String, Float, Edge
from bigraph_schema.methods import infer, set_default, serialize, deserialize, render, wrap_default

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep
from process_bigraph import Step as BigraphStep, Process as BigraphProcess


@dataclass(kw_only=True)
class FunctionInstance(Node):
    _inputs: Node = field(default_factory=Node)
    _outputs: Node = field(default_factory=Node)
    address: String = field(default_factory=String)
    config: Node = field(default_factory=Node)

@dataclass(kw_only=True)
class StepInstance(FunctionInstance):
    pass

@dataclass(kw_only=True)
class ProcessInstance(FunctionInstance):
    interval: Float = field(default_factory=Float)


def function_instance_data(core, value, path):
    if not hasattr(value, 'library'):
        value.library = core

    config = value.parameters
    config_schema = value.config_schema or core.infer(config, path=path+('config',))
    ports_schema = core.infer(value.ports_schema(), path=path+('ports',))

    data = {
        '_inputs': ports_schema,
        '_outputs': ports_schema,
        'address': String(_default=f'local:{value.name}'),
        'config': config_schema}

    return data


@infer.dispatch
def infer(core, value: VivariumStep, path: tuple=()):
    data = function_instance_data(core, value, path)
    instance = StepInstance(**data)

    return set_default(instance, value)
    

@infer.dispatch
def infer(core, value: VivariumProcess, path: tuple=()):
    data = function_instance_data(core, value, path)
    data['interval'] = Float(_default=value.parameters['timestep'])
    instance = ProcessInstance(**data)

    return set_default(instance, value)
