import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ManifestConfig:
    host: str = "127.0.0.1"
    port: int = 8081
    url: str = "http://127.0.0.1:8081"


@dataclass
class DataConfig:
    host: str = "127.0.0.1"
    port: int = 9001


@dataclass
class StorageConfig:
    root_dir: str = "/tmp/dakv_store"
    max_objects: int = 1000
    ttl_seconds: int = 3600


@dataclass
class NetworkConfig:
    timeout_ms: int = 1000
    refine_timeout_ms: int = 150
    enable_simulation: bool = False
    bandwidth_mbps: int = 1000
    rtt_ms: int = 10
    loss_percent: float = 0.0


@dataclass
class HostCacheConfig:
    max_bytes: int = 4 * 1024 * 1024 * 1024
    eviction_policy: str = "lru"


@dataclass
class PlannerConfig:
    policy: str = "rule_based"
    alpha: float = 0.8
    min_prefix_tokens: int = 128


@dataclass
class MetricsConfig:
    enable_prometheus: bool = True
    prometheus_port: int = 9090
    log_level: str = "INFO"


@dataclass
class DeadlineKVConfig:
    model_id: str = "meta-llama/Llama-2-7b-hf"
    tokenizer_id: str = "meta-llama/Llama-2-7b-hf"
    kv_layout_version: str = "v1-block-first"
    block_size: int = 16
    cache_dtype: str = "float16"
    num_layers: int = 32
    ttft_slo_ms: int = 500
    tp_size: int = 1
    enable_tier1_host_cache: bool = True
    enable_refinement: bool = True
    critical_codec: str = "int8_symm"
    refinement_codec: str = "fp16_raw"
    
    manifest: ManifestConfig = field(default_factory=ManifestConfig)
    data: DataConfig = field(default_factory=DataConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    host_cache: HostCacheConfig = field(default_factory=HostCacheConfig)
    planner: PlannerConfig = field(default_factory=PlannerConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "DeadlineKVConfig":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        
        config = cls()
        
        for key, value in data.items():
            if key == "manifest":
                config.manifest = ManifestConfig(**value)
            elif key == "data":
                config.data = DataConfig(**value)
            elif key == "storage":
                config.storage = StorageConfig(**value)
            elif key == "network":
                config.network = NetworkConfig(**value)
            elif key == "host_cache":
                config.host_cache = HostCacheConfig(**value)
            elif key == "planner":
                config.planner = PlannerConfig(**value)
            elif key == "metrics":
                config.metrics = MetricsConfig(**value)
            elif hasattr(config, key):
                setattr(config, key, value)
        
        return config

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeadlineKVConfig":
        config = cls()
        
        for key, value in data.items():
            if key == "manifest":
                config.manifest = ManifestConfig(**value) if isinstance(value, dict) else value
            elif key == "data":
                config.data = DataConfig(**value) if isinstance(value, dict) else value
            elif key == "storage":
                config.storage = StorageConfig(**value) if isinstance(value, dict) else value
            elif key == "network":
                config.network = NetworkConfig(**value) if isinstance(value, dict) else value
            elif key == "host_cache":
                config.host_cache = HostCacheConfig(**value) if isinstance(value, dict) else value
            elif key == "planner":
                config.planner = PlannerConfig(**value) if isinstance(value, dict) else value
            elif key == "metrics":
                config.metrics = MetricsConfig(**value) if isinstance(value, dict) else value
            elif hasattr(config, key):
                setattr(config, key, value)
        
        return config

    @property
    def manifest_url(self) -> str:
        return self.manifest.url

    @property
    def data_host(self) -> str:
        return self.data.host

    @property
    def data_port(self) -> int:
        return self.data.port

    @property
    def network_timeout_ms(self) -> int:
        return self.network.timeout_ms

    @property
    def refine_timeout_ms(self) -> int:
        return self.network.refine_timeout_ms

    @property
    def max_host_cache_bytes(self) -> int:
        return self.host_cache.max_bytes

    @property
    def planner_policy(self) -> str:
        return self.planner.policy
