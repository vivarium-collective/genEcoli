from genEcoli.types.unum import UnumUnits
from genEcoli.types.quantity import Quantity
from genEcoli.types.csr_matrix import CSRMatrix
from genEcoli.types.units_array import UnitsArray
from genEcoli.types.process import StepInstance, ProcessInstance
from genEcoli.types.method import Method

from bigraph_schema import BASE_TYPES

ECOLI_TYPES = {
    'unum': UnumUnits,
    'quantity': Quantity,
    'csr_matrix': CSRMatrix,
    'units_array': UnitsArray,
    'step_instance': StepInstance,
    'process_instance': ProcessInstance,
    'method': Method}

ECOLI_TYPES.update(BASE_TYPES)
