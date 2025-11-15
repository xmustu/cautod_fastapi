import os
import asyncio
import json

import pytest

import database.models as db_models


def test_upload_and_download_file(app_client, monkeypatch, tmp_path):
    client = app_client

    # Prepare upload: create an in-memory file
    file_content = b"hello world"
    files = {"file": ("test.txt", file_content, "text/plain")}
    data = {"conversation_id": "conv1", "task_id": 1}

    # Post upload
    r = client.post("/api/upload_file", files=files, data=data)
    assert r.status_code == 200
    resp = r.json()
    assert resp["file_name"] == "test.txt"
    assert resp["content_type"] == "text/plain"
    assert os.path.exists(resp["path"]) is True

    # Now prepare download: ensure a Tasks.get_or_none exists and file is present
    class DummyTask:
        def __init__(self):
            self.task_id = 1
            self.user_id = 1

    async def fake_get_or_none(*args, **kwargs):
        return DummyTask()

    monkeypatch.setattr(db_models.Tasks, "get_or_none", fake_get_or_none)

    # create the file on expected path (settings.DIRECTORY defaults to None so uses files/ conv/task)
    download_path = os.path.join("files", "conv1", "1")
    os.makedirs(download_path, exist_ok=True)
    file_path = os.path.join(download_path, "test.txt")
    with open(file_path, "wb") as f:
        f.write(file_content)

    # request download
    payload = {"task_id": 1, "conversation_id": "conv1", "file_name": "test.txt"}
    r2 = client.post("/api/download_file", json=payload)
    assert r2.status_code == 200
    assert r2.content == file_content


def test_get_task_status(app_client, monkeypatch):
    client = app_client

    async def fake_get(task_id=None):
        return {"task_id": task_id, "status": "done"}

    monkeypatch.setattr(db_models.Tasks, "get", fake_get)

    r = client.post("/api/result_status/123")
    assert r.status_code == 200
    # since our fake returns a dict, FastAPI will encode it as JSON
    assert r.json().get("status") == "done"
