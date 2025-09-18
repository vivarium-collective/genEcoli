import typing
from plum import dispatch
from dataclasses import dataclass, is_dataclass, field

from bigraph_schema.schema import Node, Integer, Dtype, Array
from bigraph_schema.methods import infer, set_default, serialize, deserialize

from scipy.sparse._csr import csr_matrix


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


@dataclass(kw_only=True)
class CSRMatrix(Node):
    _shape: typing.Tuple[int] = field(default_factory=tuple)
    _data: Dtype = field(default_factory=Dtype)
    data: Array = field(default_factory=Array)
    indices: Array = field(default_factory=Array)
    pointers: Array = field(default_factory=Array)


@infer.dispatch
def infer(core, value: csr_matrix, path: tuple = ()):
    data = {
        '_shape': value.shape,
        '_data': infer(core, value.dtype, ()),
        'data': Array(**{
            '_shape': value.data.shape,
            '_data': infer(core, value.data.dtype, ())}),
        'indices': Array(**{
            '_shape': value.indices.shape,
            '_data': Integer()}),
        'pointers': Array(**{
            '_shape': value.indptr.shape,
            '_data': Integer()})}

    schema = CSRMatrix(**data)
    schema = set_default(schema, value)

    return schema


@serialize.dispatch
def serialize(schema: CSRMatrix, state):
    encode = {
        'data': serialize(schema.data, state.data),
        'indices': serialize(schema.indices, state.indices),
        'pointers': serialize(schema.pointers, state.indptr)}

    return encode


@deserialize.dispatch
def deserialize(schema: CSRMatrix, encode):
    if isinstance(encode, csr_matrix):
        return encode
    else:
        inner = tuple(
            deserialize(
                getattr(schema, key),
                encode[key])
            for key in ['data', 'indices', 'pointers']),

        return csr_matrix(
            *inner,
            shape=schema._shape)
