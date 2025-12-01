import xarray as xr
from process_bigraph import Process as PbgProcess, Composite, ProcessTypes
import numpy as np
from vivarium.core.engine import Engine
from vivarium.core.composer import deep_merge
from vivarium.core.process import Process
from vivarium.core.serialize import deserialize_value, serialize_value
from vivarium.library.dict_utils import deep_merge_check
from vivarium.library.topology import inverse_topology
from vivarium.library.topology import assoc_path

from ecoli.library.logging_tools import write_json
from ecoli.experiments.ecoli_master_sim import EcoliSim, report_profiling, TimeLimitError, SimConfig

# Environment composer for spatial environment sim
import ecoli.composites.environment.lattice
from ecoli.library.schema import not_a_process
import datetime
import gc
import json
import warnings
from functools import partial
from typing import Any
from urllib import parse
import pickle
from vivarium.core.engine import Engine

from pathlib import Path


class EcoliDataManager:
    @classmethod
    def query(cls, sim: EcoliSim):
        return sim.ecoli_experiment.state.get_value(condition=not_a_process)

    @classmethod
    def query_engine(cls, sim: EcoliSim):
        return sim.ecoli_experiment.state.get_value(condition=not_a_process)

    @classmethod
    def initialize_ecoli(cls, config_path: str | None = None, sim_config: SimConfig | None = None) -> EcoliSim:
        self: EcoliSim = cls.new_simulation(config_path=config_path, config=sim_config)

        # validate initialization
        if self.ecoli is None:
            raise RuntimeError(
                "Build the composite by calling build_ecoli() \
                before calling run()."
            )

        # initialize experiment config
        metadata = self.get_metadata()
        metadata["output_metadata"] = self.output_metadata()
        # make the experiment
        if isinstance(self.emitter, str):
            self.emitter_config = {"type": self.emitter}
            if self.emitter_arg is not None:
                for key, value in self.emitter_arg.items():
                    self.emitter_config[key] = value
            if self.emitter == "parquet":
                raise RuntimeError(
                    "You cannot specify a parquet emitter for now..."
                )
        experiment_config = {
            "description": self.description,
            "metadata": metadata,
            "processes": self.ecoli.processes,
            "steps": self.ecoli.steps,
            "flow": self.ecoli.flow,
            "topology": self.ecoli.topology,
            "initial_state": self.generated_initial_state,
            "progress_bar": self.progress_bar,
            "emit_topology": self.emit_topology,
            "emit_processes": self.emit_processes,
            "emit_config": self.emit_config,
            "emitter": self.emitter_config,
            "initial_global_time": self.initial_global_time,
        }
        if self.experiment_id:
            # Store backup of base experiment ID,
            # in case multiple experiments are run in a row
            # with suffix_time = True.
            if not self.experiment_id_base:
                self.experiment_id_base = self.experiment_id
            if self.suffix_time:
                self.experiment_id = datetime.now().strftime(
                    f"{self.experiment_id_base}_%Y%m%d-%H%M%S"
                )
            # Special characters can break Hive partitioning so do not allow them
            if self.experiment_id != parse.quote_plus(self.experiment_id):
                raise TypeError(
                    "Experiment ID cannot contain special characters"
                    f"that change the string when URL quoted: {self.experiment_id}"
                    f" != {parse.quote_plus(self.experiment_id)}"
                )
            experiment_config["experiment_id"] = self.experiment_id
        experiment_config["profile"] = self.profile

        # configure Engine
        # Since unique numpy updater is an class method, internal
        # deepcopying in vivarium-core causes this warning to appear
        warnings.filterwarnings(
            "ignore",
            message="Incompatible schema "
                    "assignment at .+ Trying to assign the value <bound method "
                    r"UniqueNumpyUpdater\.updater .+ to key updater, which already "
                    r"has the value <bound method UniqueNumpyUpdater\.updater",
        )
        self.ecoli_experiment = Engine(**experiment_config)
        # Only emit designated stores if specified
        if self.config["emit_paths"]:
            self.ecoli_experiment.state.set_emit_values([tuple()], False)
            self.ecoli_experiment.state.set_emit_values(
                self.config["emit_paths"],
                True,
            )
        # Clean up unnecessary references
        # self.generated_initial_state = None
        # self.ecoli_experiment.initial_state = None
        # del metadata, experiment_config
        # self.ecoli = None
        return self

    @classmethod
    def new_simulation(cls, config_path: str | None = None, config: SimConfig | None = None, **config_overrides) -> EcoliSim:
        def getsim(config, config_path):
            if config_path is not None:
                if not Path(config_path).exists():
                    raise ValueError(f'You must pass a valid config path, not: {config_path}')
                return EcoliSim.from_file(filepath=config_path)
            if config is not None:
                return EcoliSim(config.to_dict())
            return None

        sim: EcoliSim | None = getsim(config=config, config_path=config_path)
        if sim is None:
            raise RuntimeError("You must pass either a valid config path or config instance")

        # parameterize sim config
        if len(config_overrides):
            sim.config.update(config_overrides)

        # build vivarium ecoli
        sim.build_ecoli()
        print('Ecoli has been built!')
        return sim