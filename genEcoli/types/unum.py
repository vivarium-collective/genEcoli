import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node
from bigraph_schema.methods import infer, set_default, default, serialize, deserialize, render, wrap_default

from unum import Unum


def unum_dimension(value):
    dimension = {}
    for unit, scale in value._unit.items():
        entry = value._unitTable[unit]
        base_unit = {
            unit: scale}
        if entry[0]:
            dimension_unit = entry[0]._unit
            base_key = list(dimension_unit.keys())[0]
            base_unit = {base_key: scale}

        dimension.update(
            base_unit)

    return dimension


def default_unum(schema, core):
    return Unum(
        schema['_dimension'],
        0)


def serialize_unum(schema, state, core):
    return {
        '_type': 'unum',
        '_dimension': unum_dimension(
            state),
        'units': state._unit,
        'magnitude': state.asNumber()}


def deserialize_unum(schema, state, core):
    if isinstance(state, Unum):
        return state
    else:
        return Unum(
            state['units'],
            state['magnitude'])


def check_unum(schema, state, core):
    return isinstance(state, Unum)


@dataclass(kw_only=True)
class UnumUnits(Node):
    _dimension: typing.Dict = field(default_factory=dict)
    units: typing.Dict = field(default_factory=dict)
    magnitude: Node = field(default_factory=Node)


@infer.dispatch
def infer(core, value: Unum, path: tuple = ()):
    dimension = unum_dimension(value)
    magnitude = infer(
        core,
        value.asNumber(),
        path+(value.strUnit(),))

    unum_data = {
        '_dimension': dimension,
        'units': value._unit,
        'magnitude': magnitude}

    schema = UnumUnits(**unum_data)
    schema = set_default(schema, value)

    return schema

@default.dispatch
def default(schema: UnumUnits):
    if schema._default:
        return schema._default
    else:
        return Unum(
            schema.units,
            default(schema.magnitude))

@serialize.dispatch
def serialize(schema: UnumUnits, state):
    if isinstance(state, dict):
        return state
    else:
        magnitude = serialize(
            schema.magnitude,
            state.asNumber())

        return {
            'units': state._unit,
            'magnitude': magnitude}

@deserialize.dispatch
def deserialize(schema: UnumUnits, encode):
    if isinstance(encode, Unum):
        return encode
    else:
        magnitude = deserialize(
            schema.magnitude,
            encode['magnitude'])

        return Unum(
            encode['units'],
            magnitude)

@render.dispatch
def render(schema: UnumUnits):
    data = {
        '_type': 'unum',
        '_dimension': schema._dimension,
        'units': schema.units,
        'magnitude': render(schema.magnitude)}

    return wrap_default(schema, data)
    
