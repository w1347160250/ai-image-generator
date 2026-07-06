"""现有『访问口令码』行为的回归测试（第 1 步：锁住现状）。

本文件在引入 AAD SSO 之前编写，用于确保后续改动不会破坏口令码这条鉴权路径。
所有外部依赖已在 conftest.py 中处理，测试不联网。
"""

from tests.conftest import VALID_ACCESS_CODE


def test_health_is_public(client):
    """/api/health 无需鉴权即可访问，返回 status ok。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"


def test_generate_with_valid_access_code_returns_202(client):
    """带正确口令的 JSON 请求应被接受，返回 202 + task_id。"""
    resp = client.post(
        "/api/generate",
        json={"access_code": VALID_ACCESS_CODE, "prompt": "a cat"},
    )
    assert resp.status_code == 202
    body = resp.get_json()
    assert "task_id" in body
    assert body["status"] == "processing"


def test_generate_with_wrong_access_code_returns_403(client):
    """口令错误应返回 403。"""
    resp = client.post(
        "/api/generate",
        json={"access_code": "wrong-code", "prompt": "a cat"},
    )
    assert resp.status_code == 403


def test_generate_without_access_code_returns_403(client):
    """缺少口令应返回 403。"""
    resp = client.post(
        "/api/generate",
        json={"prompt": "a cat"},
    )
    assert resp.status_code == 403


def test_generate_without_prompt_returns_400(client):
    """口令正确但缺少 prompt 应返回 400。"""
    resp = client.post(
        "/api/generate",
        json={"access_code": VALID_ACCESS_CODE},
    )
    assert resp.status_code == 400


def test_task_status_not_found_returns_404(client):
    """查询不存在的任务应返回 404。"""
    resp = client.get("/api/task/nonexistent-task-id")
    assert resp.status_code == 404
