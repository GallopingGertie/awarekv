import os
import time
import threading
import pytest
from dakv.store.manifest_service import create_manifest_service
from dakv.store.local_disk_backend import LocalDiskBackend
from dakv.transport.data_server import DataServer
from dakv.transport.data_client import DataClient


@pytest.fixture
def temp_storage(tmp_path):
    return str(tmp_path / "dakv_test")


@pytest.fixture
def manifest_service(temp_storage):
    service = create_manifest_service(temp_storage)
    
    thread = threading.Thread(target=lambda: service.run(host="127.0.0.1", port=18081), daemon=True)
    thread.start()
    
    time.sleep(1)
    
    return service


@pytest.fixture
def data_server(temp_storage):
    object_store = LocalDiskBackend(temp_storage)
    server = DataServer(host="127.0.0.1", port=19001, object_store=object_store)
    
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    
    time.sleep(1)
    
    yield server
    
    server.stop()


def test_end_to_end_put_get(manifest_service, data_server):
    client = DataClient(host="127.0.0.1", port=19001, timeout_ms=5000)
    
    object_id = "test_object_123"
    test_data = b"Hello, DAKV!"
    
    success = client.put_critical(object_id, test_data, codec="fp16_raw", request_id="req_1")
    assert success
    
    retrieved_data = client.get_critical(object_id, request_id="req_2")
    assert retrieved_data == test_data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
