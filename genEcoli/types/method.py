import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node, String, Float
from bigraph_schema.methods import infer, set_default, serialize, realize, render, wrap_default


@dataclass(kw_only=True)
class Method(Node):
    module: String = field(default_factory=String)
    instance: object = field(default_factory=object)
    attribute: String = field(default_factory=String)


@infer.dispatch
def infer(core, value: typing.Callable, path: tuple=()):
    if hasattr(value, '__self__'):
        data = {
            'module': value.__module__,
            'instance': value.__self__.__class__.__name__,
            'attribute': value.__func__.__name__}
    else:
        data = {
            'module': value.__module__,
            'instance': None,
            'attribute': value.__name__}

    method = Method(**data)

    return set_default(method, value), []


@serialize.dispatch
def serialize(schema: Method, state):
    if isinstance(state, dict):
        return state
    else:
        return {
            'module': str(schema.module),
            'instance': str(schema.instance),
            'attribute': schema.attribute}

@realize.dispatch
def realize(core, schema: Method, encode, path=()):
    if isinstance(encode, typing.Callable):
        return schema, encode, []
    else:
        import ipdb; ipdb.set_trace()

@render.dispatch
def render(schema: Method, defaults=False):
    data = {
        '_type': 'method',
        'module': schema.module,
        'instance': str(schema.instance),
        'attribute': schema.attribute}

    return wrap_default(schema, data) if defaults else data
