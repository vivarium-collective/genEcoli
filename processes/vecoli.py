import uuid
from typing import Any

import xarray as xr
from process_bigraph import Process, Composite, ProcessTypes

from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH
from utils.ecoli_tfba_steps import export_metabolism, simulate


def get_agent_id(config: dict[str, Any]) -> str:
    return config.get("agent_id", "0")


class VEcoliProcess(Process):
    config_schema = {
        "config_path": "maybe[string]",
        "sim_data_path": "maybe[string]",
        "out_dir": "maybe[string]",
        "agent_id": "maybe[string]"
    }

    def initialize(self, config) -> None:
        # config path
        config_path = config.get("config_path")
        self.sim: EcoliSim = EcoliSim.from_file(filepath=config_path)
        self.sim.experiment_id = f"sms_{config.get('agent_id', str(uuid.uuid4()))}"

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
        print(f'Built ecoli!')

    def initial_state(self) -> dict[str, Any]:
        return {"environment": self.sim.generated_initial_state}

    def inputs(self) -> dict[str, Any]:
        # return {
        #     "environment": {
        #         "agents": {
        #              f"{self.agent_id}": "tree[any]"
        #         }
        #     }
        # }
        return {"environment": "tree[any]"}

    def outputs(self) -> dict[str, Any]:
        # return {
        #     "environment": {
        #         "agents": {
        #              f"{self.agent_id}": "tree[any]"
        #         }
        #     }
        # }
        return {"environment": "tree[any]"}

    def update(self, state, interval) -> dict[str, Any]:
        # each agent outputs keys: 'bulk', 'unique', 'environment', 'boundary', 'process'
        new_state = self.sim.ecoli_experiment.next_update(interval, state)
        # self.sim.update_experiment(interval)
        # state = self.sim.ecoli_experiment.state.get_value(condition=not_a_process)
        cell_data: xr.DataTree = export_metabolism(self.sim)
        return {
            "environment": {
                "agents": {
                    f"{self.agent_id}": cell_data.to_dict()
                }
            }
        }


def get_ecolisim_state(sim: EcoliSim):
    from ecoli.library.schema import not_a_process
    state = sim.ecoli_experiment.state.get_value(condition=not_a_process)
    return state


def test_vecoli_process() -> None:
    core = ProcessTypes()
    core.process_registry.register('vecoli-process', VEcoliProcess)

    composite = Composite(
        config={
            'state': {
                "ecoli_0": {
                    "config": {
                        "config_path": "/Users/alex/sms/genEcoli/ecoli_configs/sms_single.json"
                    },
                    "_type": "process",
                    "address": "local:vecoli-process",
                    "inputs": {
                        "environment": ["environment_store"]
                    },
                    "outputs": {
                        "environment": ["environment_store"]
                    }

                },
                "emitter": {
                    "config": {
                        "emit": {
                            "environment": "tree[any]"
                        }
                    },
                    "inputs": {
                        "environment": ["environment_store"]
                    }
                }
            }
        },
        core=core
    )
    composite.run(1)
    ecolisim = composite.state.get('ecoli_0').get('instance').sim