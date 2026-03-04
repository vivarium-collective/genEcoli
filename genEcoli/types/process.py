import copy
import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node, String, Float, Link, Overwrite, Protocol
from bigraph_schema.methods import infer, set_default, serialize, wrap_default, resolve, merge_update

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep
from process_bigraph import Step as BigraphStep, Process as BigraphProcess, StepLink, ProcessLink


###########################################3
# process instances


def translate_ports(core, ports, path=()):
    if isinstance(ports, dict):
        if not ports:
            return Node()

        if '_default' in ports:
            # we are at a leaf
            state = ports['_default']
            schema = core.infer(state)

            if '_updater' in ports:
                if ports['_updater'] == 'set':
                    schema = Overwrite(_value=schema)

            return schema

        else:
            result = {}
            for key, subports in ports.items():
                result[key] = translate_ports(core, subports)

            return result


@dataclass(kw_only=True)
class FunctionInstance(Node):
    _inputs: Node = field(default_factory=Node)
    _outputs: Node = field(default_factory=Node)
    address: String = field(default_factory=String)
    config: Node = field(default_factory=Node)

@dataclass(kw_only=True)
class StepInstance(FunctionInstance):
    priority: Float = field(default_factory=Float)

@dataclass(kw_only=True)
class ProcessInstance(FunctionInstance):
    interval: Float = field(default_factory=Float)


def function_instance_data(core, value, path):
    if not hasattr(value, 'core'):
        value.core = core

    config = value.parameters
    if hasattr(value, 'config_schema'):
        config_schema = value.config_schema
    else:
        config_schema = core.infer(config, path=path+('config',))

    ports_schema = translate_ports(
        core,
        value.ports_schema(),
        path=path+('ports',))

    data = {
        '_inputs': ports_schema,
        '_outputs': ports_schema,
        'address': Protocol(_default=f'local:{value.name}'),
        'config': config_schema}

    return data


@infer.dispatch
def infer(core, value: VivariumStep, path: tuple=()):
    data = function_instance_data(core, value, path)
    data['priority'] = Float(_default=value.parameters['priority'])
    instance = StepInstance(**data)

    return set_default(instance, value), []
    

@infer.dispatch
def infer(core, value: VivariumProcess, path: tuple=()):
    data = function_instance_data(core, value, path)
    data['interval'] = Float(_default=value.parameters['timestep'])
    instance = ProcessInstance(**data)

    return set_default(instance, value), []




###################################################33
# process classes

# @dataclass(kw_only=True)
# class Protocol(Node):
#     protocol: String = field(default_factory=String)
#     data: Node = field(default_factory=Node)

# @dataclass(kw_only=True)
# class FunctionLink(Link):
#     address: Protocol = field(default_factory=Protocol)
#     config: Node = field(default_factory=Node)

# @resolve.dispatch
# def resolve(current: Protocol, update: String):
#     schema = merge_update(current, current, update)
#     return schema

# @serialize.dispatch
# def serialize(schema: FunctionLink, raw):
#     state = copy.copy(raw)
#     if 'instance' in state:
#         instance = state.pop('instance')
#         state['config'] = serialize(instance.config_schema, state.get('config'))
#     return state

# @realize.dispatch
# def realize(schema: FunctionLink, encode):
#     address = encode.get('address')
#     result = copy.copy(encode)

#     if not address:
#         return encode

#     instantiate = core.parse_protocol(address)

#     config_schema, config = realize(
#         instantiate.config_schema,
#         encode.get('config', {}))

#     instance = encode.get('instance')

#     if not instance:
#         instance = instantiate(config, core=core)
#         result['instance'] = instance

#     result['config'] = config
#     result['_inputs'] = copy.deepcopy(instance.inputs())
#     result['_outputs'] = copy.deepcopy(instance.outputs())

#     return schema, result

