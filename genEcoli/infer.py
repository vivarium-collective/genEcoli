from abc import ABCMeta
import numpy as np
import unum
from pint import Quantity
from functools import wraps
from plum import dispatch
from scipy.sparse._csr import csr_matrix

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep

from bigraph_schema import deep_merge
from bigraph_schema.type_functions import deserialize_array

NONETYPE = type(None)


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
    return unum.Unum(
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
    return unum.Unum(
        state['units'],
        state['magnitude'])


def check_unum(schema, state, core):
    return isinstance(state, unum.Unum)


def serialize_csr_matrix(schema, state, core):
    return {
        k: schema[k]
        for k in ['_type', '_shape', '_data']
    } | {
        k: core.serialize(schema[k], getattr(state, f))
        for (k, f) in
        [('data',) * 2, ('indices',) * 2, ('pointers', 'indptr')]
    }


def deserialize_csr_matrix(schema, state, core):
    match state:
        case csr_matrix():
            return state
        case _:
            return csr_matrix(
                tuple(core.deserialize(schema[k], state[k])
                      for k in ['data', 'indices', 'pointers']),
                shape=state.get(
                    '_shape',
                    schema['_shape']))


ECOLI_TYPES = {
    'unum': {
        '_inherit': ['number'],
        '_type_parameters': ['dimension'],
        '_default': default_unum,
        '_serialize': serialize_unum,
        '_deserialize': deserialize_unum,
        # '_generate': generate_unum,
        # '_resolve': resolve_unum,
        # '_dataclass': dataclass_unum,
        '_check': check_unum,
        'units': 'map[float]',
        'magnitude': 'float'},

    'csr_matrix': {
        '_inherit': ['array'],
        '_serialize': serialize_csr_matrix,
        '_deserialize': deserialize_csr_matrix,
        'indices': {
            '_type': 'array',
            '_data': 'integer'},
        'pointers': {
            '_type': 'array',
            '_data': 'integer'}}}


MISSING_TYPES = {}


@dispatch
def infer(value: (int | np.int32 | np.int64 |
                  np.dtypes.Int32DType | np.dtypes.Int64DType),
          path: tuple):
    return 'integer'

@dispatch
def infer(value: bool, path: tuple):
    return 'boolean'

@dispatch
def infer(value: (float | np.float32 | np.float64 |
                  np.dtypes.Float32DType | np.dtypes.Float64DType),
          path: tuple):
    return 'float'

@dispatch
def infer(value: str, path: tuple):
    return 'string'

@dispatch
def infer(value: np.ndarray, path: tuple):
    import ipdb; ipdb.set_trace()

    shape = '|'.join([str(dimension) for dimension in value.shape])
    data = infer(
        dtype_schema(value.dtype),
        path+('_data',))

    return f'array[({shape}),{data}]'

@dispatch
def infer(value: list, path: tuple):
    element = 'any'
    if len(value) > 0:
        element = infer(
            value[0],
            path+('_element',))

    return f'list[{element}]'

def dict_schema(schema):
    parts = []
    for key, subschema in schema.items():
        if isinstance(subschema, dict):
            part = f'({dict_schema(subschema)})'
        else:
            part = subschema
        entry = f'{key}:{part}'
        parts.append(
            entry)

    return '|'.join(
        parts)

@dispatch
def infer(value: tuple, path: tuple):
    result = []
    for index, item in enumerate(value):
        key = f'_{index}'
        schema = infer(
            item,
            path+(key,))
        if isinstance(schema, dict):
            schema = dict_schema(schema)
        result.append(schema)

    inner = '|'.join(result)
    return f'({inner})'

@dispatch
def infer(value: NONETYPE, path: tuple):
    return 'maybe[any]'

@dispatch
def infer(value: set, path: tuple):
    return infer(
        list(value),
        path)

@dispatch
def infer(value: unum.Unum, path: tuple):
    dimension = unum_dimension(value)
    
    return {
        '_type': 'unum',
        '_dimension': dimension,
        'magnitude': infer(
            value.asNumber(),
            path+(value.strUnit(),))}

class Empty():
    def method(self):
        pass

FUNCTION_TYPE = type(default_unum)
METHOD_TYPE = type(Empty().method)

@dispatch
def infer(value: FUNCTION_TYPE, path: tuple):
    return 'function'

@dispatch
def infer(value: METHOD_TYPE, path: tuple):
    # TODO: add serialize/deserialize for method
    #   by storing where in the state the method is located
    return 'method'

@dispatch
def infer(value: ABCMeta, path: tuple):
    return 'meta'

@dispatch
def infer(value: csr_matrix, path: tuple):
    return {
        '_type': 'csr_matrix',
        '_shape': value.shape,
        '_data': infer(value.dtype, ()),
        'data': {
            '_type': 'array',
            '_shape': value.data.shape,
            '_data': infer(value.dtype, ())},
        'indices': {
            '_type': 'array',
            '_shape': value.indices.shape,
            '_data': 'integer'},
        'pointers': {
            '_type': 'array',
            '_shape': value.indptr.shape,
            '_data': 'integer'}}


@dispatch
def infer(value: dict, path: tuple):
    subvalues = {}
    distinct_subvalues = []
    for key, subvalue in value.items():
        subvalues[key] = infer(
            subvalue,
            path+(key,))

        if subvalues[key] not in distinct_subvalues:
            distinct_subvalues.append(
                subvalues[key])

    if len(distinct_subvalues) == 1:
        map_value = distinct_subvalues[0]
        if isinstance(map_value, dict):
            map_value = dict_schema(
                map_value)
        if not map_value:
            map_value = 'any'

        return f'map[{map_value}]'

    else:
        return subvalues

@dispatch
def infer(value: VivariumProcess, path: tuple):
    return 'process'


@dispatch
def infer(value: VivariumStep, path: tuple):
    return 'step'


@dispatch
def infer(value: object, path: object):
    type_name = str(type(value))

    value_keys = value.__dict__.keys()
    value_schema = {}

    for key in value_keys:
        if not key.startswith('_'):
            try:
                value_schema[key] = infer(
                    getattr(value, key),
                    path + (key,))
            except Exception as e:
                traceback.print_exc()
                print(e)

                if type_name not in MISSING_TYPES:
                    MISSING_TYPES[type_name] = set([])

                MISSING_TYPES[type_name].add(
                    path)

                value_schema[key] = 'any'

    return value_schema


def infer_schema(config, path=()) -> dict:
    '''Translate default values into corresponding bigraph-schema type declarations.'''
    ports = {}

    for key, value in config.items():
        ports[key] = infer(
            value,
            path+(key,))

    return ports


def find_defaults(params: dict) -> dict:
    '''Extract inner dict _default values from an arbitrarily-nested `params` input.'''
    result = {}
    for key, value in params.items():
        if isinstance(value, dict):
            nested_result = find_defaults(value)
            if '_default' in value and not nested_result:
                val = value['_default']
                # if isinstance(val, Quantity):
                #     val = val.to_tuple()[0]
                result[key] = val
            elif nested_result:
                result[key] = nested_result

    return result


def collapse_defaults(d):
    '''Returns a dict whose keys match that of d, except replacing innermost values (v) with their corresponding _default declarations.
    Used for migration.
    '''
    if isinstance(d, dict):
        if '_default' in d:
            return d['_default'] 
        else:
            return {k: collapse_defaults(v) for k, v in d.items()}
    else:
        return d


def translate_ports(ports_schema, name='top'):
    '''Translates vivarium.core.Process.defaults into bigraph-schema types to be consumed by pbg.Composite.'''
    defaults = find_defaults(
        ports_schema)

    types_found = infer_schema(
        defaults,
        path=(name,))

    return types_found
