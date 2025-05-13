
from abc import abstractmethod
import copy

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep
from process_bigraph import Process as BigraphProcess, Step as BigraphStep

from genEcoli.schemas import collapse_defaults, get_config_schema, get_defaults_schema


__all__ = [
    'MigrateStep',
    'MigrateProcess',
    'Resolver'
]

class Revert:
    pass 


class Resolver(BigraphStep):
    """Takes PartitionedProcess updates and somehow emits 
    a single update that is a resolution of their demands.

    TODO: look at Allocator for Resolver
    """
    pass


class OmniStep(VivariumStep, BigraphStep):
    """This class allows v1 steps to run as v2 steps"""

    config_schema = {} 
    _ports = {
        "inputs": [],
        "outputs": []
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._port_data = self.ports_schema()
        self.input_port_data = self._set_ports("input")
        self.output_port_data = self._set_ports("output")

    def __init_subclass__(cls, **kwargs): 
        cls.config_schema = {
            **get_config_schema(cls.defaults),
            "time_step": {"_default": 1.0, "_type": "float"}
        }
    
    def _set_ports(self, port_type: str):
        """Separates inputs from outputs and defines defaults. If there are no port_names in either input_ports or output ports, then 
        assume bidirectional.
        """
        port_type_name = f"{port_type}_ports"
        port_names = getattr(self, port_type_name)
        ports = copy.deepcopy(self._port_data[port_names])
        if len(port_names):
            ports = {
                port: self._port_data[port]
                for port in port_names
            }
        return ports

    @property 
    def input_ports(self):
        return self._ports["inputs"]
    
    @input_ports.setter
    def input_ports(self, v):
        self._ports["inputs"] = v
    
    @property 
    def output_ports(self):
        return self._ports["outputs"]
    
    @output_ports.setter
    def output_ports(self, v):
        self._ports["outputs"] = v
    
    def inputs(self):
        """Expects:
        self.input_port_data = {port_name: {_default: ...}}
        """
        return get_defaults_schema(self.input_port_data)

    def outputs(self):
        """Use specific ports if defined, otherwise return bidirectional ports"""
        return get_defaults_schema(self.output_port_data)
    
    def initial_state(self):
        return collapse_defaults(self.input_port_data)
    
    @abstractmethod
    def update(self, state):
        return {}


class OmniProcess(VivariumProcess, BigraphProcess):
    # This class allows v1 processes to run as v2 processes
    config_schema = {} 
    _ports = {
        "inputs": [],
        "outputs": []
    }

    def __init__(self, config=None, parameters=None, core=None) -> None:
        if core is None:
            return

        parameters = parameters or config
        config = config or parameters

        VivariumProcess.__init__(
            self,
            parameters=parameters)

        BigraphProcess.__init__(
            self,
            config=config,
            core=core)

        self._port_data = self.ports_schema()
        self.input_port_data = self._set_ports("input")
        self.output_port_data = self._set_ports("output")

    def __init_subclass__(cls, **kwargs): 
        cls.config_schema = {
            **get_config_schema(cls.defaults),
            "time_step": {"_default": 1.0, "_type": "float"}
        }
    
    def _set_ports(self, port_type: str):
        """Separates inputs from outputs and defines defaults"""
        port_names = getattr(self, f"{port_type}_ports")
        ports = copy.deepcopy(self._port_data)
        if len(port_names):
            ports = {
                port: self._port_data[port]
                for port in port_names
            }
        return ports

    @property 
    def input_ports(self):
        return self._ports["inputs"]
    
    @input_ports.setter
    def input_ports(self, v):
        self._ports["inputs"] = v
    
    @property 
    def output_ports(self):
        return self._ports["outputs"]
    
    @output_ports.setter
    def output_ports(self, v):
        self._ports["outputs"] = v
    
    def inputs(self):
        # extract from ports schema
        return get_defaults_schema(self.input_port_data)

    def outputs(self):
        """Use specific ports if defined, otherwise return bidirectional ports"""
        return get_defaults_schema(self.output_port_data)
    
    def initial_state(self):
        return collapse_defaults(self.input_port_data)
    
    def update(self, state, interval):
        return self.next_update(interval, state)


def update_inheritance(cls, new_base):
    # replace the base class with the new base
    cls.__bases__ = (new_base,)

    # store the existing init
    init = cls.__init__

    # wrap the existing init with an init that accepts arguments
    # specific to process-bigraph
    def new_init(self, config=None, parameters=None, core=None):
        parameters = parameters or config
        init(self, parameters=parameters)
        new_base.__init__(
            self,
            config,
            parameters,
            core)

    # replace the existing init with the new init
    cls.__init__ = new_init
