"""Export E. coli state as JSON, with and without partitioning.

These exports are for documentation/inspection only and do not
produce functional simulation state.
"""

import os
import json

import numpy as np

from genEcoli.plot import ALWAYS_SKIP


class _StateEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy arrays, tuples-as-keys, and other non-JSON types."""

    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return str(obj)

    def encode(self, obj):
        return super().encode(self._convert(obj))

    def _convert(self, obj):
        if isinstance(obj, dict):
            return {str(k): self._convert(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._convert(i) for i in obj]
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        return str(obj)


SKIP_PORTS = {'allocate', 'process', 'next_update_time', 'process_state'}


def _clean_wires(wires):
    """Remove partitioning infrastructure wires from a wire dict."""
    if not isinstance(wires, dict):
        return wires
    return {
        port: wire for port, wire in wires.items()
        if '_flow' not in port
        and port not in SKIP_PORTS
        and not (isinstance(wire, list) and wire and wire[0] in ('request', 'allocate'))
    }


def _is_step(v):
    """Check if a value is a step/process entry (has address and config)."""
    return isinstance(v, dict) and 'address' in v and 'config' in v


def _strip_partitioning(agent):
    """Return a copy of the agent state with partitioning removed.

    Merges requesters/evolvers into single process names, removes
    allocators, the ``process`` store, and internal infrastructure steps.
    Strips allocate/request/flow wires from remaining step entries.
    """
    result = {}
    for k, v in agent.items():
        if any(s in k for s in ALWAYS_SKIP):
            continue
        if 'allocator' in k:
            continue
        if '_requester' in k:
            continue
        if k == 'process':
            continue

        if '_evolver' in k:
            name = k.replace('_evolver', '')
        else:
            name = k

        if _is_step(v):
            entry = dict(v)
            for field in ('inputs', '_inputs', 'outputs', '_outputs'):
                if field in entry:
                    entry[field] = _clean_wires(entry[field])
            result[name] = entry
        else:
            result[name] = v

    return result


def export_state_json(document, outdir='doc'):
    """Export the E. coli state as JSON, with and without partitioning.

    Args:
        document: A document dict with 'schema' and 'state' keys
            (as produced by generate_ecoli_document or loaded from pickle).
        outdir: Directory to write JSON files into.

    Returns:
        Tuple of (with_partitioning_path, wcm_path).
    """
    os.makedirs(outdir, exist_ok=True)
    schema = document.get('schema', {})
    agent = document['state']['agents']['0']

    encoder = _StateEncoder(indent=2)

    # With partitioning — full state as-is
    with_path = os.path.join(outdir, 'ecoli_with_partitioning.json')
    with open(with_path, 'w') as f:
        f.write(encoder.encode({'schema': schema, 'state': document['state']}))

    # Without partitioning — cleaned (wcm = whole-cell model view)
    without_path = os.path.join(outdir, 'ecoli_wcm.json')
    cleaned_agent = _strip_partitioning(agent)
    with open(without_path, 'w') as f:
        f.write(encoder.encode({'schema': schema, 'state': {'agents': {'0': cleaned_agent}}}))

    print(f"Exported {with_path} ({len(agent)} keys)")
    print(f"Exported {without_path} ({len(cleaned_agent)} keys)")
    return with_path, without_path
