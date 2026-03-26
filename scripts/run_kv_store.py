#!/usr/bin/env python3

import argparse
import threading
from dakv.store.manifest_service import create_manifest_service
from dakv.store.local_disk_backend import LocalDiskBackend
from dakv.transport.data_server import DataServer
from dakv.config import DeadlineKVConfig
from dakv.logging import get_logger


logger = get_logger()


def main():
    parser = argparse.ArgumentParser(description="Run KV Store (Manifest + Data Server)")
    parser.add_argument("--config", type=str, default="configs/deadline_kv_local.yaml",
                        help="Path to config file")
    parser.add_argument("--manifest-port", type=int, default=None,
                        help="Manifest service port (overrides config)")
    parser.add_argument("--data-port", type=int, default=None,
                        help="Data server port (overrides config)")
    
    args = parser.parse_args()
    
    config = DeadlineKVConfig.from_yaml(args.config)
    
    manifest_port = args.manifest_port or config.manifest.port
    data_port = args.data_port or config.data.port
    
    manifest_service = create_manifest_service(config.storage.root_dir)
    
    object_store = LocalDiskBackend(config.storage.root_dir)
    data_server = DataServer(
        host=config.data.host,
        port=data_port,
        object_store=object_store
    )
    
    data_thread = threading.Thread(target=data_server.start, daemon=True)
    data_thread.start()
    
    logger.info("=" * 60)
    logger.info("KV Store Started")
    logger.info(f"Manifest Service: {config.manifest.host}:{manifest_port}")
    logger.info(f"Data Server: {config.data.host}:{data_port}")
    logger.info(f"Storage Root: {config.storage.root_dir}")
    logger.info("=" * 60)
    
    manifest_service.run(host=config.manifest.host, port=manifest_port)


if __name__ == "__main__":
    main()
