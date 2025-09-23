import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node, Integer, Dtype, Array
from bigraph_schema.methods import infer, set_default, serialize, deserialize, render, wrap_default

from genEcoli.types.unum import Unum

from wholecell.utils.unit_struct_array import UnitStructArray


@dataclass(kw_only=True)
class UnitsArray(Node):
    struct: Array = field(default_factory=Array)
    units: Unum = field(default_factory=Unum)


@infer.dispatch
def infer(core, value: UnitStructArray, path: tuple = ()):
    data = {
        'struct': infer(core, value.struct_array, path=path + ('struct',)),
        'units': infer(core, value.units, path=path + ('units',))}

    schema = UnitsArray(**data)
    schema = set_default(schema, value)

    return schema


@serialize.dispatch
def serialize(schema: UnitsArray, state):
    if isinstance(state, dict):
        encode = state
    else:
        encode = {
            'struct': serialize(schema.struct, state.struct_array),
            'units': serialize(schema.units, state.units)}

    return encode


@deserialize.dispatch
def deserialize(schema: UnitsArray, encode):
    if isinstance(encode, UnitStructArray):
        return encode
    else:
        inner = tuple(
            deserialize(
                getattr(schema, key),
                encode[key])
            for key in ['struct', 'units']),

        return UnitStructArray(
            *inner)

@render.dispatch
def render(schema: UnitsArray):
    data = {
        'struct': render(schema.struct),
        'units': render(schema.units)}

    return wrap_default(schema, data)
    
