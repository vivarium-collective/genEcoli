import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node, String, Float, Edge
from bigraph_schema.methods import infer, set_default, default, serialize, deserialize, render, wrap_default

import pint
ureg = pint.UnitRegistry()

@dataclass(kw_only=True)
class Quantity(Node):
    units: typing.Dict = field(default_factory=dict)
    magnitude: Node = field(default_factory=Node)


def units_dict(value):
    return {
        key: subvalue
        for key, subvalue in value.unit_items()}
    

@infer.dispatch
def infer(core, value: pint.Quantity, path: tuple = ()):
    units = units_dict(value)
    magnitude = infer(
        core,
        value.magnitude,
        path+('magnitude',))

    data = {
        'units': units,
        'magnitude': magnitude}

    schema = Quantity(**data)
    schema = set_default(schema, value)

    return schema

@default.dispatch
def default(schema: Quantity):
    if schema._default:
        return schema._default
    else:
        return {
            'units': schema.units,
            'magnitude': default(schema.magnitude)}

@serialize.dispatch
def serialize(schema: Quantity, state):
    if isinstance(state, dict):
        return state
    else:
        magnitude = serialize(
            schema.magnitude,
            state.magnitude)

        return {
            'units': schema.units,
            'magnitude': magnitude}

@deserialize.dispatch
def deserialize(schema: Quantity, encode):
    if isinstance(encode, pint.Quantity):
        return encode
    else:
        magnitude = deserialize(
            schema.magnitude,
            encode['magnitude'])

        decode = (
            magnitude,
            tuple([(key, value)
                for key, value in schema.units.items()]))

        return ureg.Quantity.from_tuple(
            decode)

@render.dispatch
def render(schema: Quantity):
    data = {
        '_type': 'quantity',
        'units': schema.units,
        'magnitude': render(schema.magnitude)}

    return wrap_default(schema, data)
    
