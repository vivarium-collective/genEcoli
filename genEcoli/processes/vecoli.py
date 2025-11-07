from typing import Any

import xarray as xr
from process_bigraph import Process, Composite, ProcessTypes
from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH

from genEcoli.ecoli_tfba_steps import export_metabolism


def get_agent_id(config: dict[str, Any]) -> str:
    return config.get("agent_id", "0")


class VEcoliProcess(Process):
    config_schema = {
        "config_path": "maybe[string]",
        "sim_data_path": "maybe[string]",
        "out_dir": "maybe[string]",
        "agent_id": {
            "_type": "string",
            "_default": "0"
        }
    }

    def initialize(self, config) -> None:
        # config path
        config_path = config.get("config_path")
        self.sim: EcoliSim = EcoliSim.from_file(filepath=config_path)

        # parameterize sim config
        max_duration = config.get("duration", None)
        if max_duration is not None:
            self.sim.max_duration = round(max_duration, 0)

        # build vivarium ecoli
        self.sim.build_ecoli()

        # reference any data needed during update methods or interface methods
        agent_id_spec = config.get("agent_id")
        if agent_id_spec is not None:
            self.sim.agent_id = agent_id_spec

        self.agent_id: str = self.sim.agent_id

    def inputs(self) -> dict[str, Any]:
        return {}

    def outputs(self) -> dict[str, Any]:
        return {"env": {"cells": "tree[any]"}}

    def update(self, state, interval) -> dict[str, Any]:
        _state = self.sim.ecoli_experiment.next_update(interval)
        cell_datatree: xr.DataTree = export_metabolism(self.sim)
        return {
            "env": {
                "cells": {
                    f"{self.agent_id}": cell_datatree.to_dict()
                }
            }
        }


def test_vecoli_process() -> None:
    core = ProcessTypes()
    core.process_registry.register('vecoli-process', VEcoliProcess)

    composite = Composite()