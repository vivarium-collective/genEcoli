# from plum import dispatch
# from bigraph_schema.methods import infer

# from unum import Unum
# from scipy.sparse._csr import csr_matrix
# from process_bigraph import Process, Step, Composite


# def unum_dimension(value):
#     dimension = {}
#     for unit, scale in value._unit.items():
#         entry = value._unitTable[unit]
#         base_unit = {
#             unit: scale}
#         if entry[0]:
#             dimension_unit = entry[0]._unit
#             base_key = list(dimension_unit.keys())[0]
#             base_unit = {base_key: scale}

#         dimension.update(
#             base_unit)

#     return dimension


# def default_unum(schema, core):
#     return Unum(
#         schema['_dimension'],
#         0)


# def serialize_unum(schema, state, core):
#     return {
#         '_type': 'unum',
#         '_dimension': unum_dimension(
#             state),
#         'units': state._unit,
#         'magnitude': state.asNumber()}


# def deserialize_unum(schema, state, core):
#     if isinstance(state, Unum):
#         return state
#     else:
#         return Unum(
#             state['units'],
#             state['magnitude'])


# def check_unum(schema, state, core):
#     return isinstance(state, Unum)


# def serialize_csr_matrix(schema, state, core):
#     return {
#         k: schema[k]
#         for k in ['_type', '_shape', '_data']
#     } | {
#         k: core.serialize(schema[k], getattr(state, f))
#         for (k, f) in
#         [('data',) * 2, ('indices',) * 2, ('pointers', 'indptr')]
#     }


# def deserialize_csr_matrix(schema, state, core):
#     match state:
#         case csr_matrix():
#             return state
#         case _:
#             return csr_matrix(
#                 tuple(core.deserialize(schema[k], state[k])
#                       for k in ['data', 'indices', 'pointers']),
#                 shape=state.get(
#                     '_shape',
#                     schema['_shape']))


# @dataclass(kw_only=True)
# class UnumUnits(Node):
#     _dimension: typing.Dict = field(default_factory=dict)
#     magnitude: Node = field(default_factory=Node)


# @infer.dispatch
# def infer(core, value: Unum, path: tuple = ()):
#     dimension = unum_dimension(value)
#     magnitude = infer(
#         core,
#         value.asNumber(),
#         path+(value.strUnit(),))

#     unum_data = {
#         '_type': 'unum',
#         '_dimension': dimension,
#         'magnitude': magnitude}

#     schema = UnumUnits(**unum_data)

#     return schema


# @infer.dispatch
# def infer(core, value: csr_matrix, path: tuple = ()):
#     return {
#         '_type': 'csr_matrix',
#         '_shape': value.shape,
#         '_data': infer(value.dtype, ()),
#         'data': {
#             '_type': 'array',
#             '_shape': value.data.shape,
#             '_data': infer(value.dtype, ())},
#         'indices': {
#             '_type': 'array',
#             '_shape': value.indices.shape,
#             '_data': 'integer'},
#         'pointers': {
#             '_type': 'array',
#             '_shape': value.indptr.shape,
#             '_data': 'integer'}}

# @infer.dispatch
# def infer(core, value: Process, path: tuple = ()):
    
