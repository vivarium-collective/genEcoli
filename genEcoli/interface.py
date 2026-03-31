import inspect
import copy

from vivarium.core.process import Process as VivariumProcess, Step as VivariumStep

from bigraph_schema import deep_merge, Edge as BigraphEdge
from bigraph_schema.schema import Node, Overwrite
from bigraph_schema.methods import infer, render
from bigraph_schema.protocols import local_lookup_module
from process_bigraph import Composite, Process as BigraphProcess, Step as BigraphStep

from genEcoli.types.process import translate_ports


__all__ = [
    'OmniStep',
    'OmniProcess',
    'Resolver'
]

class Revert:
    pass


def apply_v1_update_in_place(process, state, delta):
    """Apply v1 updates directly to the state dict (which references composite state).

    The state dict from core.view() contains references to the actual composite
    state objects (numpy arrays etc). We modify them in place and return empty
    update so v2's apply is a no-op."""
    import numpy as np

    if not delta:
        return

    try:
        ports = process.ports_schema()
    except Exception:
        return

    for key, update_value in delta.items():
        port = ports.get(key, {})
        updater = port.get('_updater') if isinstance(port, dict) else None

        current = state.get(key)

        if updater == 'set' or key in ('next_update_time', 'process'):
            state[key] = update_value
        elif callable(updater):
            if current is not None:
                try:
                    updater(current, update_value)
                except Exception:
                    state[key] = update_value
        elif isinstance(update_value, dict) and isinstance(current, dict):
            _deep_update(current, update_value)
        elif isinstance(update_value, (int, float)) and isinstance(current, (int, float)):
            state[key] = current + update_value
        elif update_value is not None:
            state[key] = update_value


def _deep_update(target, source):
    """Recursively update target dict with source dict."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def apply_step_update(cell_state, edge, instance, delta, unique_updaters=None):
    """Apply a step's delta update to cell_state by following output wire paths.

    Unlike apply_v1_update_in_place (which modifies a view dict), this writes
    directly into cell_state via output wires, so scalar replacements propagate.

    unique_updaters: shared registry of UniqueNumpyUpdater instances keyed
    by wire path tuple, so all steps accessing the same unique molecule
    accumulate into the same updater."""
    import numpy as np
    from ecoli.library.schema import UniqueNumpyUpdater

    try:
        ports = instance.ports_schema()
    except Exception:
        return

    output_wires = edge.get('outputs', {})

    for port_name, update_value in delta.items():
        if port_name.startswith('_flow_'):
            continue

        wire_path = output_wires.get(port_name)
        if wire_path is None:
            continue

        if isinstance(wire_path, dict):
            _apply_nested_wire_update(cell_state, wire_path, update_value)
            continue

        if not isinstance(wire_path, list) or not wire_path:
            continue

        port = ports.get(port_name, {})
        updater = port.get('_updater') if isinstance(port, dict) else None

        target = cell_state
        for segment in wire_path[:-1]:
            if isinstance(target, dict):
                if segment not in target:
                    target[segment] = {}
                target = target[segment]
            else:
                target = None
                break

        if not isinstance(target, dict):
            continue

        key = wire_path[-1]

        if updater == 'set' or port_name in ('next_update_time', 'process'):
            target[key] = update_value
        elif callable(updater):
            current = target.get(key)
            if current is not None:
                import numpy as np
                if isinstance(current, np.ndarray):
                    try:
                        current.flags.writeable = True
                    except ValueError:
                        current = current.copy()
                        current.flags.writeable = True
                        target[key] = current
                wire_key = tuple(wire_path) if isinstance(wire_path, list) else None
                if (unique_updaters and wire_key and wire_key in unique_updaters
                        and hasattr(updater, '__self__')
                        and isinstance(updater.__self__, UniqueNumpyUpdater)):
                    shared_updater = unique_updaters[wire_key]
                    result = shared_updater.updater(current, update_value)
                    if result is not current:
                        target[key] = result
                else:
                    updater(current, update_value)
        elif isinstance(update_value, dict):
            current = target.get(key)
            if isinstance(current, dict):
                _deep_update(current, update_value)
            else:
                target[key] = update_value
        elif isinstance(update_value, (int, float)):
            current = target.get(key)
            if isinstance(current, (int, float)):
                target[key] = current + update_value
            else:
                target[key] = update_value
        elif update_value is not None:
            target[key] = update_value


class EcoliComposite(Composite):
    """Composite subclass with v1-compatible step execution.

    Overrides run_steps to apply v1 updaters in-place (via apply_step_update)
    while returning proper update paths so the Composite's trigger/cascade
    system can order downstream steps correctly.

    This allows using Composite.run() instead of the custom run_ecoli_sim loop.
    """

    def __init__(self, config=None, core=None):
        self._unique_updaters = None
        self._cell_path = None

        # Skip initial run_steps during parent init
        original_run_steps = EcoliComposite.run_steps
        EcoliComposite.run_steps = lambda self, x: None
        super().__init__(config, core=core)
        EcoliComposite.run_steps = original_run_steps

        _make_arrays_writeable(self.state)
        _disable_readonly_arrays()

        # Cache cell state path
        for path_key, substates in self.state.items():
            if isinstance(substates, dict) and path_key != 'global_time':
                for subkey in substates:
                    if isinstance(substates[subkey], dict) and len(substates[subkey]) > 10:
                        self._cell_path = (path_key, subkey)
                        break
            if self._cell_path:
                break

    def _ensure_unique_updaters(self):
        """Lazily initialize the shared UniqueNumpyUpdater registry."""
        if self._unique_updaters is not None:
            return

        if self._cell_path:
            from bigraph_schema import get_path
            cell_state = get_path(self.state, self._cell_path)
            step_names = [k for k, v in cell_state.items()
                          if isinstance(v, dict) and 'instance' in v]
            self._unique_updaters = _share_unique_updaters(cell_state, step_names)
        else:
            self._unique_updaters = {}

    def expire_process_paths(self, update_paths):
        """No-op — process paths don't change during v1 simulation."""
        pass

    def apply_updates(self, updates):
        """Override to skip core.apply/realize which would replace state dicts
        and discard in-place modifications from v1 updaters.

        Returns the global_time path at the cell level so trigger_steps
        can find and trigger steps that depend on time advancement."""
        if self._cell_path:
            return [self._cell_path + ('global_time',)]
        return []

    def run_steps(self, step_paths):
        """Execute steps using v1 updater semantics with proper path tracking.

        Applies v1 updates in-place via apply_step_update, then reports
        the updated wire paths so the Composite's cascade system can
        trigger downstream steps."""
        from bigraph_schema import get_path

        if not step_paths:
            self.steps_run = set()
            return

        self._ensure_unique_updaters()

        update_paths = []
        for step_path in step_paths:
            step = get_path(self.state, step_path)
            if not isinstance(step, dict) or 'instance' not in step:
                continue

            instance = step['instance']
            if not hasattr(instance, 'next_update'):
                continue

            cell_state_path = step_path[:-1]
            cell_state = get_path(self.state, cell_state_path)

            _make_arrays_writeable(cell_state)

            try:
                view = _build_view(cell_state, step, instance)
                view = fill_missing_state(view, instance)
                timestep = instance.parameters.get('timestep', 1.0)
                delta = instance.next_update(timestep, view)
                if delta:
                    apply_step_update(cell_state, step, instance, delta,
                                      unique_updaters=self._unique_updaters)

                # Report all output wire paths (including flow tokens) for triggering
                output_wires = step.get('outputs', {})
                for port_name, wire_path in output_wires.items():
                    if isinstance(wire_path, list) and wire_path:
                        full_path = tuple(list(cell_state_path) + wire_path)
                        update_paths.append(full_path)
                    elif isinstance(wire_path, dict):
                        base = wire_path.get('_path', [])
                        if base:
                            full_path = tuple(list(cell_state_path) + base)
                            update_paths.append(full_path)
            except Exception as e:
                pass

        self.expire_process_paths(update_paths)
        to_run = self.cycle_step_state()

        if to_run:
            self.run_steps(to_run)
        else:
            self.steps_run = set()


def run_ecoli_sim(composite, flow, interval, timestep=1.0):
    """Run the E. coli simulation using the v1 flow execution model.

    Instead of relying on v2's Composite.run() trigger system, this executes
    all steps in v1 flow order every timestep — matching vEcoli's original
    execution model exactly.

    Args:
        composite: A v2 Composite holding the migrated state.
        flow: The v1 flow dict (sim.ecoli.flow) defining step execution order.
        interval: Total simulated time to run.
        timestep: Time per step (default 1.0s, matching v1).
    """
    inner_flow = None
    cell_path = None
    for path_key in flow:
        subflow = flow[path_key]
        if isinstance(subflow, dict):
            for subkey in subflow:
                if isinstance(subflow[subkey], dict) and subflow[subkey]:
                    inner_flow = subflow[subkey]
                    cell_path = (path_key, subkey)
                    break
        if inner_flow:
            break

    if inner_flow is None:
        raise ValueError("Could not find flow order in flow dict")

    step_order = list(inner_flow.keys())
    cell_state = composite.state[cell_path[0]][cell_path[1]]

    _make_arrays_writeable(cell_state)
    _disable_readonly_arrays()
    unique_updaters = _share_unique_updaters(cell_state, step_order)

    num_steps = int(interval / timestep)
    for t in range(num_steps):
        for step_name in step_order:
            _make_arrays_writeable(cell_state)
            edge = cell_state.get(step_name)
            if not isinstance(edge, dict) or 'instance' not in edge:
                continue

            instance = edge['instance']
            if not hasattr(instance, 'next_update'):
                continue

            try:
                view = _build_view(cell_state, edge, instance)
                view = fill_missing_state(view, instance)
                step_ts = instance.parameters.get('timestep', timestep)
                delta = instance.next_update(step_ts, view)
                if delta:
                    apply_step_update(cell_state, edge, instance, delta,
                                      unique_updaters=unique_updaters)
            except Exception as e:
                print(f"Step {step_name} failed at t={t}: {type(e).__name__}: {e}")

        composite.state['global_time'] += timestep
        if 'global_time' in cell_state:
            cell_state['global_time'] = composite.state['global_time']


def _make_arrays_writeable(state):
    """Recursively make all numpy arrays in the state writeable."""
    import numpy as np
    if isinstance(state, dict):
        for key, value in state.items():
            if isinstance(value, np.ndarray):
                if not value.flags.writeable:
                    state[key] = value.copy()
                    state[key].flags.writeable = True
            elif hasattr(value, 'struct_array'):
                arr = value.struct_array
                if isinstance(arr, np.ndarray) and not arr.flags.writeable:
                    value.struct_array = arr.copy()
                    value.struct_array.flags.writeable = True
            elif hasattr(value, 'flags') and hasattr(value.flags, 'writeable'):
                if not value.flags.writeable:
                    try:
                        value.flags.writeable = True
                    except ValueError:
                        state[key] = value.copy()
            elif isinstance(value, dict):
                _make_arrays_writeable(value)


def _share_unique_updaters(cell_state, step_order):
    """Create a shared registry of UniqueNumpyUpdater instances, one per
    unique molecule wire path. Returns the registry for use in apply_step_update.

    In v1, all processes that access the same unique molecule share a single
    updater via the Store. We replicate this by creating one updater per path."""
    from ecoli.library.schema import UniqueNumpyUpdater

    shared = {}

    for step_name in step_order:
        edge = cell_state.get(step_name)
        if not isinstance(edge, dict) or 'instance' not in edge:
            continue
        instance = edge['instance']
        if not hasattr(instance, 'ports_schema'):
            continue
        try:
            ports = instance.ports_schema()
        except Exception:
            continue
        output_wires = edge.get('outputs', {})
        for port_name, port in ports.items():
            if not isinstance(port, dict):
                continue
            updater = port.get('_updater')
            if updater is None or not hasattr(updater, '__self__'):
                continue
            if not isinstance(updater.__self__, UniqueNumpyUpdater):
                continue
            wire_path = output_wires.get(port_name)
            if not isinstance(wire_path, list):
                continue
            wire_key = tuple(wire_path)
            if wire_key not in shared:
                shared[wire_key] = UniqueNumpyUpdater()

    return shared


def _disable_readonly_arrays():
    """Monkey-patch bulk_numpy_updater to not set arrays read-only.

    In v1, arrays are made read-only between steps as a safety measure.
    In our custom loop, this causes failures when the next step tries to
    modify the same array. We patch the updater to skip the read-only flag."""
    from ecoli.library.schema import bulk_numpy_updater
    import functools

    if hasattr(bulk_numpy_updater, '_patched'):
        return

    @functools.wraps(bulk_numpy_updater)
    def writeable_updater(current, update):
        current.flags.writeable = True
        for idx, value in update:
            current["count"][idx] += value
        return current

    writeable_updater._patched = True

    import ecoli.library.schema as schema_mod
    schema_mod.bulk_numpy_updater = writeable_updater

    from ecoli.library import schema as schema_lib
    schema_lib.bulk_numpy_updater = writeable_updater


def fill_missing_state(state, process):
    """Fill in missing state keys with defaults from ports_schema."""
    try:
        ports = process.ports_schema()
    except Exception:
        return state

    for key, port in ports.items():
        if key.startswith('_'):
            continue
        if key not in state and isinstance(port, dict):
            if '_default' in port:
                state[key] = port['_default']
            else:
                defaults = extract_defaults(port)
                if defaults:
                    state[key] = defaults

    return state


def extract_defaults(schema):
    """Recursively extract non-empty _default values from a v1 ports_schema dict."""
    result = {}
    if not isinstance(schema, dict):
        return result
    for key, value in schema.items():
        if key.startswith('_'):
            continue
        if isinstance(value, dict):
            if '_default' in value:
                default = value['_default']
                # Skip empty/falsy defaults that would overwrite real state
                try:
                    is_empty = default is None or (isinstance(default, (list, dict, tuple)) and len(default) == 0)
                except (TypeError, ValueError):
                    is_empty = False
                if not is_empty:
                    result[key] = default
            else:
                sub = extract_defaults(value)
                if sub:
                    result[key] = sub
    return result


class Resolver(BigraphStep):
    """Takes PartitionedProcess updates and somehow emits 
    a single update that is a resolution of their demands.

    TODO: look at Allocator for Resolver
    """
    pass


# class OmniStep(VivariumStep, BigraphStep):
class OmniStep(BigraphStep):
    """This class allows v1 steps to run as v2 steps"""

    config_schema = {}
    _ports = {
        "inputs": [],
        "outputs": []
    }

    def __init__(self, parameters=None, config=None, core=None) -> None:
        parameters = parameters or config
        config = config or parameters

        super().__init__(
            config=config,
            core=core)

    def inputs(self):
        return translate_ports(
            self.core,
            self.ports_schema())

    def outputs(self):
        return translate_ports(
            self.core,
            self.ports_schema())

    def initial_state(self, config=None):
        return {}

    def update(self, state, interval=None):
        if hasattr(self, 'next_update'):
            timestep = interval if interval and interval > 0 else self.parameters.get('timestep', 1.0)
            state = fill_missing_state(state, self)
            delta = self.next_update(timestep, state)
            apply_v1_update_in_place(self, state, delta)
        return {}


class OmniProcess(BigraphProcess):
    """This class allows v1 processes to run as v2 processes"""
    config_schema = {}
    _ports = {
        "inputs": [],
        "outputs": []
    }

    def __init__(self, parameters=None, config=None, core=None) -> None:
        parameters = parameters or config
        config = config or parameters

        super().__init__(
            config=config,
            core=core)

    def inputs(self):
        return translate_ports(
            self.core,
            self.ports_schema())

    def outputs(self):
        return translate_ports(
            self.core,
            self.ports_schema())

    def initial_state(self, config=None):
        return {}

    def update(self, state, interval):
        state = fill_missing_state(state, self)
        delta = self.next_update(interval, state)
        return delta if delta else {}


def update_inheritance(cls, new_base, core):
    if new_base in cls.__bases__:
        return

    cls.__bases__ = cls.__bases__ + (new_base,)

    original_init = cls.__init__
    captured_core = core

    def new_init(self, config=None, core=None, parameters=None):
        config = config or parameters
        parameters = parameters or config
        if core is None:
            core = captured_core

        try:
            original_init(self, parameters=parameters)
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize {cls.__name__}: {e}"
            ) from e

        self._config = config or {}

        new_base.__init__(
            self,
            config=config,
            parameters=parameters,
            core=core)

    cls.__init__ = new_init

    # Override initial_state and update directly on the class so they
    # take precedence over VivariumProcess/VivariumStep methods in MRO
    if not hasattr(cls, '_omni_patched'):
        cls.initial_state = new_base.initial_state
        cls.update = new_base.update
        cls._omni_patched = True


def find_instances(module, visited=None):
    steps = {}
    processes = {}
    visited = visited or set([])

    for key in dir(module):
        value = getattr(module, key)
        if not isinstance(value, type):
            if inspect.ismodule(value) and value.__name__.startswith('ecoli') and value not in visited:
                visited.add(value)
                substeps, subprocesses = find_instances(value, visited)
                steps.update(substeps)
                processes.update(subprocesses)
            continue

        if value in (VivariumStep, VivariumProcess):
            continue

        if issubclass(value, VivariumStep):
            steps[key] = value
        elif issubclass(value, VivariumProcess):
            processes[key] = value

    return steps, processes


def scan_processes(path):
    module = local_lookup_module(path)
    steps, processes = find_instances(module)
    scan = {
        'processes': processes,
        'steps': steps}

    return scan


def update_processes(core, processes):
    for process_name, process in processes.get('processes', {}).items():
        update_inheritance(process, OmniProcess, core)
        process.core = core
        core.register_link(process_name, process)

    for step_name, step in processes.get('steps', {}).items():
        update_inheritance(step, OmniStep, core)
        step.core = core
        core.register_link(step_name, step)

    return core


def scan_update(core, path):
    processes = scan_processes(path)
    core = update_processes(
        core,
        processes)

    return core


def list_paths(path):
    if isinstance(path, tuple):
        return list(path)
    elif isinstance(path, dict):
        result = {}
        for key, subpath in path.items():
            result[key] = list_paths(subpath)
        return result


def translate_processes(core, tree, topology=None, edge_type=None):
    if isinstance(tree, BigraphEdge):
        cls = type(tree)

        tree.core = core

        if not hasattr(tree, '_config'):
            tree._config = tree.parameters

        if not hasattr(cls, 'config_schema'):
            cls.config_schema = {}

        if edge_type == 'process':
            type_name = 'process'
            state = {'interval': 1.0}
        else:
            type_name = 'step'
            state = {'priority': 1.0}

        if topology is None:
            topology = tree.topology

        wires = list_paths(topology)

        process_class = cls.__name__

        state.update({
            '_type': type_name,
            'address': f'local:{process_class}',
            'config': tree.parameters,
            '_inputs': tree.inputs(),
            '_outputs': tree.outputs(),
            'instance': tree,
            'inputs': copy.deepcopy(wires),
            'outputs': copy.deepcopy(wires)})

        return state

    elif isinstance(tree, dict):
        result = {}
        for key, subtree in tree.items():
            result[key] = translate_processes(
                core,
                subtree,
                topology[key] if topology else None,
                edge_type=edge_type)

        return result

    else:
        return tree


def seed_initial_state(state, sim):
    """Run specific listener steps to populate derived values needed by other processes.

    In v1, listeners compute mass/volume from bulk data each timestep.
    We pre-compute these by running listener steps and applying only dict updates."""
    flow = sim.ecoli.flow
    listeners_to_seed = ['post-division-mass-listener', 'ecoli-mass-listener']

    for path_key, substates in state.items():
        if not isinstance(substates, dict):
            continue
        for subkey, cell_state in substates.items():
            if not isinstance(cell_state, dict):
                continue
            for step_name in listeners_to_seed:
                edge = cell_state.get(step_name)
                if not isinstance(edge, dict) or 'instance' not in edge:
                    continue
                instance = edge['instance']
                if not hasattr(instance, 'next_update'):
                    continue
                _ensure_wired_paths(cell_state, edge)
                _populate_port_defaults(cell_state, edge, instance)
                try:
                    view = _build_view(cell_state, edge, instance)
                    timestep = instance.parameters.get('timestep', 1.0)
                    update = instance.next_update(timestep, view)
                    _apply_dict_updates(cell_state, edge.get('outputs', {}), update)
                except Exception:
                    continue
    return state


SCALAR_STATE_KEYS = {'global_time', 'timestep', 'next_update_time'}

def _ensure_wired_paths(cell_state, edge):
    """Ensure output paths that will receive dict updates exist as empty dicts."""
    wires = edge.get('outputs', {})
    for port_name, wire_path in wires.items():
        if isinstance(wire_path, list) and len(wire_path) == 1:
            key = wire_path[0]
            if key in SCALAR_STATE_KEYS:
                continue
            if key not in cell_state or cell_state[key] is None:
                cell_state[key] = {}


def _populate_port_defaults(cell_state, edge, instance):
    """Populate port defaults into the state along wired paths."""
    try:
        ports = instance.ports_schema()
    except Exception:
        return
    wires = edge.get('inputs', {})
    for port_name, wire_path in wires.items():
        if not isinstance(wire_path, list) or not wire_path:
            continue
        port = ports.get(port_name)
        if not isinstance(port, dict):
            continue

        if '_default' in port:
            target = cell_state
            for segment in wire_path[:-1]:
                if isinstance(target, dict):
                    if segment not in target or target[segment] is None:
                        target[segment] = {}
                    target = target[segment]
                else:
                    break
            if isinstance(target, dict):
                last = wire_path[-1]
                if last not in target or target[last] is None:
                    target[last] = port['_default']
        else:
            _inject_nested_defaults(cell_state, wire_path, port)


def _inject_nested_defaults(state, wire_path, port_schema):
    """Inject nested port defaults into state at the given wire path."""
    target = state
    for segment in wire_path:
        if isinstance(target, dict):
            if segment not in target or target[segment] is None:
                target[segment] = {}
            target = target[segment]
        else:
            return

    if not isinstance(target, dict):
        return

    for key, value in port_schema.items():
        if key.startswith('_'):
            continue
        if isinstance(value, dict):
            if '_default' in value and key not in target:
                target[key] = value['_default']
            elif key not in target:
                target[key] = {}
                _inject_nested_defaults(target, [key], value)
            elif isinstance(target[key], dict):
                _inject_nested_defaults(target, [key], value)


def _apply_nested_wire_update(cell_state, wire_dict, update_value):
    """Apply an update through a nested wire dict (v1 nested topology).

    For wire_dict like {'_path': ['environment'], 'exchange': ['exchange']},
    writes update_value's sub-keys to the appropriate state paths."""
    if not isinstance(update_value, dict):
        base_path = wire_dict.get('_path')
        if base_path and isinstance(base_path, list):
            _set_at_path(cell_state, base_path, update_value)
        return

    base_path = wire_dict.get('_path')
    for sub_key, sub_value in update_value.items():
        sub_wire = wire_dict.get(sub_key)
        if sub_wire is not None:
            if isinstance(sub_wire, list):
                _set_at_path(cell_state, sub_wire, sub_value)
            elif isinstance(sub_wire, dict):
                _apply_nested_wire_update(cell_state, sub_wire, sub_value)
        elif base_path and isinstance(base_path, list):
            _set_at_path(cell_state, base_path + [sub_key], sub_value)


def _set_at_path(state, path, value):
    """Set a value at a path in a nested dict, merging dicts."""
    target = state
    for segment in path[:-1]:
        if isinstance(target, dict):
            if segment not in target:
                target[segment] = {}
            target = target[segment]
        else:
            return
    if isinstance(target, dict) and path:
        key = path[-1]
        current = target.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            _deep_update(current, value)
        else:
            target[key] = value


def _resolve_wire(cell_state, wire_path):
    """Resolve a wire path to a value in cell_state. Returns None if not found."""
    if isinstance(wire_path, list) and wire_path:
        current = cell_state
        for segment in wire_path:
            if isinstance(current, dict):
                current = current.get(segment)
            else:
                return None
        return current
    elif isinstance(wire_path, dict):
        import copy
        base_path = wire_path.get('_path')
        if base_path:
            result = _resolve_wire(cell_state, base_path)
            if result is not None and isinstance(result, dict):
                result = copy.copy(result)
            else:
                result = {}
        else:
            result = {}
        for sub_key, sub_path in wire_path.items():
            if sub_key == '_path':
                continue
            sub_val = _resolve_wire(cell_state, sub_path)
            if sub_val is not None:
                result[sub_key] = sub_val
        return result
    return None


def _build_view(cell_state, edge, instance):
    """Build a state view for a step by following its input wires."""
    ports = instance.ports_schema()
    view = {}
    wires = edge.get('inputs', {})
    for port_name, wire_path in wires.items():
        resolved = _resolve_wire(cell_state, wire_path)
        if resolved is not None:
            view[port_name] = resolved
        elif port_name in ports and isinstance(ports[port_name], dict) and '_default' in ports[port_name]:
            view[port_name] = ports[port_name]['_default']
    return view


def _apply_dict_updates(cell_state, output_wires, update):
    """Apply only dict-valued updates from a step back into the state."""
    for port_name, value in update.items():
        if not isinstance(value, dict):
            continue
        wire_path = output_wires.get(port_name)
        if not isinstance(wire_path, list) or not wire_path:
            continue
        target = cell_state
        for segment in wire_path[:-1]:
            if isinstance(target, dict):
                if segment not in target:
                    target[segment] = {}
                target = target[segment]
            else:
                break
        if isinstance(target, dict):
            last = wire_path[-1]
            if last not in target:
                target[last] = {}
            if isinstance(target[last], dict):
                target[last].update(value)


def extract_flow_priorities(flow):
    """Convert a v1 flow dict into priority values. Earlier steps get higher priority."""
    priorities = {}
    order = list(flow.keys())
    n = len(order)
    for i, step_name in enumerate(order):
        priorities[step_name] = float(n - i)
    return priorities


def inject_flow_dependencies(cell_state, flow):
    """Add synthetic wiring to enforce the v1 flow execution order.

    For each consecutive pair (A, B) in the flow, adds a shared
    '_flow_token_{i}' path that A writes to and B reads from.
    This creates exact path matches for the v2 step dependency system.

    Also ensures the first step in the flow wires global_time as input
    so it gets triggered when Composite.run() advances time."""
    order = list(flow.keys())
    for i, step_name in enumerate(order):
        edge = cell_state.get(step_name)
        if not isinstance(edge, dict):
            continue

        if i == 0:
            edge.setdefault('inputs', {}).setdefault('global_time', ['global_time'])

        if i > 0:
            token = f'_flow_token_{i-1}'
            edge.setdefault('inputs', {})[f'_flow_in_{i}'] = [token]

        if i < len(order) - 1:
            token = f'_flow_token_{i}'
            edge.setdefault('outputs', {})[f'_flow_out_{i}'] = [token]


def migrate_composite(core, sim):
    processes = translate_processes(
        core,
        sim.ecoli.processes,
        sim.ecoli.topology,
        edge_type='process')

    steps = translate_processes(
        core,
        sim.ecoli.steps,
        sim.ecoli.topology,
        edge_type='step')

    state = deep_merge(
        processes,
        steps)

    state = deep_merge(
        state,
        sim.generated_initial_state)

    state = seed_initial_state(state, sim)

    flow = sim.ecoli.flow
    for path_key, substates in state.items():
        if isinstance(substates, dict):
            subflow = flow.get(path_key, {})
            for subkey, subsubstates in substates.items():
                if isinstance(subsubstates, dict):
                    inner_flow = subflow.get(subkey, {})
                    if inner_flow:
                        priorities = extract_flow_priorities(inner_flow)
                        for step_name, priority in priorities.items():
                            if isinstance(subsubstates.get(step_name), dict):
                                subsubstates[step_name]['priority'] = priority
                        inject_flow_dependencies(subsubstates, inner_flow)

    return state
