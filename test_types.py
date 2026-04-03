"""Unit tests for the genEcoli type system (unum, csr_matrix, etc.)."""

import numpy as np

from unum import Unum
from scipy.sparse import csr_matrix, diags

from bigraph_schema import allocate_core
from genEcoli.types import ECOLI_TYPES


def make_core():
    core = allocate_core()
    core.register_types(ECOLI_TYPES)
    return core


def test_unum():
    core = make_core()
    umol = Unum({'umol': -1}, 383.3)

    schema = core.infer(umol, ())
    serialized = core.serialize(schema, umol)
    realize_schema, realize_state = core.realize(schema, serialized)

    assert umol == realize_state

    uarray = Unum({'umol': -1}, np.array([3.3, 4.4, 5.5]))
    core.infer(umol)
    core.infer(uarray)


def test_csr():
    core = make_core()
    for tp in [int, float]:
        tri = diags(
            list(map(range, range(4, 0, -1))), range(4),
            dtype=tp, format="csr")

        schema = core.infer(tri, ())
        serialized = core.serialize(schema, tri)
        realize_schema, realize_state = core.realize(schema, serialized)

        assert not (tri != realize_state).nnz


if __name__ == '__main__':
    test_unum()
    print('test_unum PASSED')
    test_csr()
    print('test_csr PASSED')
