import json
import os

import numpy as np
from process_bigraph import ProcessTypes
from process_bigraph.processes import TOY_PROCESSES
from bigraph_schema.units import units
from bigraph_schema.type_functions import deserialize_array, check_list
from bigraph_schema.type_system import required_schema_keys

from ecoli.library.schema import (
    divide_binomial,
    divide_bulk,
    divide_by_domain,
    divide_ribosomes_by_RNA,
    divide_RNAs_by_domain,
    divide_set_none,
    empty_dict_divider,
    bulk_numpy_updater,
)

from genEcoli.types.register import register
from genEcoli.schemas import infer_state_from_composer
from genEcoli.interface import OmniStep, OmniProcess, update_inheritance, scan_processes, update_processes, migrate_composite


TYPE_MODULES = ["unum", "unit", "bulk"]  # TODO: add more here


def load(fp: str):
    import json
    with open(fp, 'r') as f:
        data = json.load(f)
    return data 

        
def get_bulk_counts(bulk: np.ndarray) -> np.ndarray:
    """
    Args:
        bulk: Numpy structured array with a `count` field
    Returns:
        Contiguous (required by orjson) array of bulk molecule counts
    """
    return np.ascontiguousarray(bulk["count"])


def register_types(core):
    core.register_processes(TOY_PROCESSES)

    # import and register types
    possible_schema_keys = required_schema_keys | {"_divide", "_description", "_value"}
    for modname in TYPE_MODULES:
        ecoli_root = os.path.abspath(
            os.path.dirname(__file__)
        )
        schema_fp = os.path.join(ecoli_root, 'types', 'definitions', f'{modname}.json')
        with open(schema_fp, 'r') as f:
            schema = json.load(f)
            for key in schema:
                if key in possible_schema_keys:
                    try:
                        val = schema[key]
                        schema[key] = eval(val)
                    except:
                        # schema.pop(key, None)
                        pass
                register(core, schema)

    return core
