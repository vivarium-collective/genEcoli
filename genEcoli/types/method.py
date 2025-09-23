import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node, String, Float, Edge
from bigraph_schema.methods import infer, set_default, serialize, deserialize, render, wrap_default


@dataclass(kw_only=True)
class Method(Node):
    instance: object = field(default_factory=object)
    attribute: String = field(default_factory=String)


@infer.dispatch
def infer(core, value: typing.Callable, path: tuple=()):
    data = {
        'instance': value.__self__,
        'attribute': value.__func__.__name__}

    method = Method(**data)

    return set_default(method, value)


@serialize.dispatch
def serialize(schema: Method, state):
    if isinstance(state, dict):
        return state
    else:
        return {
            'instance': str(schema.instance),
            'attribute': schema.attribute}

@deserialize.dispatch
def deserialize(schema: Method, encode):
    if isinstance(encode, typing.Callable):
        return encode
    else:
        import ipdb; ipdb.set_trace()

@render.dispatch
def render(schema: Method):
    data = {
        '_type': 'method',
        'instance': str(schema.instance),
        'attribute': schema.attribute}

    return wrap_default(schema, data)
