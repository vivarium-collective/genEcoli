from typing import Any

from process_bigraph import Process

from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH


def get_agent_id(config_path: str) -> str:
    pass


class VEcoliProcess(Process):
    config_schema = {
        "config_path": "string"
    }

    def initialize(self, config) -> None:
        config_path = config.get("config_path")
        self.sim: EcoliSim = EcoliSim.from_file(filepath=config_path)
        max_duration = config.get("duration", None)
        if max_duration is not None:
            self.sim.max_duration = round(max_duration, 0)
        self.sim.build_ecoli()

        self.agent_id = get_agent_id(config_path)

    def inputs(self) -> dict[str, Any]:
        return {}

    def outputs(self) -> dict[str, Any]:
        return {"env": {"cells": "tree[any]"}}

    def update(self, state, interval) -> dict[str, Any]:
        self.sim.update_state(state)
        return {
            "env": {
                "cells": {
                    f"{self.agent_id}": self.sim.ecoli_experiment.next_update(interval)
                }
            }
        }

