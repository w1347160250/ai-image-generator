"""Pytest 夹具。

目标：在不联网、不调用真实 Azure 服务的前提下，为 backend.app 提供可测试的 Flask
test client。

注意：backend/app.py 在 import 时会：
  - 读取 AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY，缺失则 raise RuntimeError；
  - 构造 openai.OpenAI 客户端。
因此这里必须在 import 之前注入环境变量，并对网络型调用做 mock。
"""

import os
import importlib

import pytest

# --- 在导入 backend.app 之前注入必需环境变量 ---
# 这些值仅用于让模块顺利完成 import，测试中不会真正发起网络请求。
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/openai/v1")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT", "gpt-image-2")
# 固定访问口令，便于断言。
os.environ.setdefault("ACCESS_CODE", "test-code")

# 访问口令常量（与上面注入值保持一致），供测试引用。
VALID_ACCESS_CODE = os.environ["ACCESS_CODE"]


@pytest.fixture
def app_module():
    """导入（或重新导入）backend.app 并返回该模块。"""
    import backend.app as app_module

    importlib.reload(app_module)
    return app_module


@pytest.fixture
def client(app_module, monkeypatch):
    """提供 Flask test client。

    对 /api/generate 背后的后台生成任务做 mock：直接把任务标记为完成，
    避免真正调用 Azure OpenAI / Blob，也避免依赖后台线程时序。
    """

    def _fake_run_generate_task(task_id, prompt, size, quality, uploaded_image_bytes_list):
        # 直接把任务置为完成，写入一个假的图片地址。
        with app_module._tasks_lock:
            app_module._tasks[task_id]["status"] = "completed"
            app_module._tasks[task_id]["image_url"] = "https://example.com/fake.png"
            app_module._tasks[task_id]["image_name"] = "fake.png"

    # 用假的后台任务替换真实实现，避免联网。
    monkeypatch.setattr(app_module, "_run_generate_task", _fake_run_generate_task)

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client
