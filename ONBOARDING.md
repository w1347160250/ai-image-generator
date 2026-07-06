# 新开发者 Onboarding 指南

> 面向第一次接触本仓库的工程师。目标：**读完这一页就能理解项目、把它跑起来、并知道从哪里改代码。**

## 1. 项目用途

一个 **AI 文生图 / 图生图 Web 应用**。用户输入访问口令 + 文字描述（可选上传参考图），后端 Flask 调用 **Azure OpenAI 图像模型**（部署名默认 `gpt-image-2`）生成图片，图片存入 **Azure Blob Storage** 并返回带 SAS 的下载链接。整个应用由**一个 Flask 进程同时托管前端静态页和后��� API**，便于一键部署到 Azure App Service。

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端语言 | Python 3.11 |
| 框架 / 运行时 | Flask + Gunicorn（生产 WSGI） |
| 前端 | 原生 HTML/CSS/JS（无框架、无构建步骤） |
| 核心依赖 | `flask`、`flask-cors`、`openai`、`requests`、`gunicorn`、`azure-storage-blob`、`Pillow` |

## 3. 目录结构

```
backend/
  app.py              核心：Flask 应用 + 所有 API + 生成/上传/回退逻辑（约 550 行，业务全部集中于此）
  requirements.txt    后端真实依赖清单
frontend/
  index.html          单页 UI（口令、描述、参考图、尺寸、质量、生成/下载）
  app.js              调用 /api/generate，轮询 /api/task/<id>，下载图片
  style.css           样式
wsgi.py               生产入口：把根目录加入 sys.path 后 import backend.app:app
requirements.txt      顶层入口，内容仅为 `-r backend/requirements.txt`（⚠️ 含一行脏数据 `- temp`）
deploy_azure_appservice.sh   一键创建 Azure 资源组/计划/WebApp 并 zip 部署
AZURE_DEPLOY.md       部署说明文档
.github/workflows/
  main_tepmimages.yml          GitHub Actions：部署到 Azure Web App
  azure-deploy.yml             另一份 Azure 部署 workflow
misc/
  generate.py         独立的命令行试验脚本（用 reference.png 做参考图，非应用组成部分）
  reference.png       示例参考图
```

**请求流程（概览）：** 浏览器 `index.html` → `app.js` 发 `POST /api/generate` → 后端校验口令/参数、参考图归一化为 PNG 并上传 Blob → 创建后台线程异步生成，立即返回 `202 + task_id` → 前端 `pollTask()` 每 5 秒轮询 `GET /api/task/<id>` 直到 `completed/failed` → 成功后返回带 30 天 SAS 的图片 URL。

**API 端点**（均定义在 `backend/app.py`）：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/` | 返回前端 `index.html` |
| GET | `/api/health` | 健康检查，返回 `{"status":"ok","deployment":...}` |
| POST | `/api/generate` | 提交生成任务，返回 `202` + `task_id` |
| GET | `/api/task/<task_id>` | 查询任务状态 |

## 4. 运行方式

### 环境变量（定义在 `backend/app.py`）

| 变量 | 说明 |
|---|---|
| `AZURE_OPENAI_API_KEY` | **必填**，缺失则启动时 `raise RuntimeError` |
| `AZURE_OPENAI_ENDPOINT` | **必填**，缺失则启动时 `raise RuntimeError` |
| `AZURE_OPENAI_DEPLOYMENT` | 模型部署名，默认 `gpt-image-2` |
| `AZURE_STORAGE_CONNECTION_STRING` | 图片落地 Blob 所需 |
| `AZURE_STORAGE_CONTAINER` | 图片落地 Blob 所需（`_GENERATED` / `_REFERENCE` 未设置时回退到它） |
| `ACCESS_CODE` | 访问口令，硬编码兜底默认值为 `ai2026` |

### 本地开发（端口 5001）

```bash
# 建议直接用 backend 依赖清单（顶层 requirements.txt 含 "- temp" 脏行，可能导致 pip 报错）
pip install -r backend/requirements.txt

export AZURE_OPENAI_API_KEY="<你的 key>"
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/openai/v1"
export AZURE_OPENAI_DEPLOYMENT="gpt-image-2"
export AZURE_STORAGE_CONNECTION_STRING="<连接串>"
export AZURE_STORAGE_CONTAINER="<容器名>"

python backend/app.py   # 访问 http://localhost:5001/
```

### 生产 / 部署

```bash
# Gunicorn 启动命令（与 deploy_azure_appservice.sh 中的 startup command 一致）
gunicorn --chdir backend --bind=0.0.0.0 --timeout 600 app:app
```

```bash
# 一键部署到 Azure（详见 AZURE_DEPLOY.md）
export AZURE_OPENAI_API_KEY="<key>"
./deploy_azure_appservice.sh
```

## 5. 测试方式

- **当前仓库没有任何自动化测试**：没有 `tests/` 目录，没有 pytest/unittest，CI workflow 中也没有测试步骤。**目前没有可运行的测试命令。**
- **没有前端构建步骤**（纯静态文件）。CI 依赖 Azure 的 `SCM_DO_BUILD_DURING_DEPLOYMENT=true` 在云端安装依赖。
- **手动验证：** 启动后访问 `http://localhost:5001/`，或调用 `GET /api/health` 检查服务是否正常。
- `misc/generate.py` 是一个手动验证脚本（可用于快速确认 API key 是否可用），**不是测试**。

## 6. 常见修改入口

| 我想改… | 去看这里 |
|---|---|
| 生成逻辑 / 参考图回退策略 | `backend/app.py` → `_generate_with_uploaded_images`、`_generate_with_optional_reference` |
| 新增 / 修改 API 端点 | `backend/app.py` → `@app.route(...)` |
| 任务状态 / 轮询机制 | `backend/app.py` → `_tasks`、`_run_generate_task`、`get_task_status`；前端 `frontend/app.js` → `pollTask` |
| 前端界面 / 交互 | `frontend/index.html`、`frontend/app.js` |
| 样式 | `frontend/style.css` |
| 依赖 | `backend/requirements.txt` |
| 访问口令逻辑 | `backend/app.py` → `ACCESS_CODE` |
| Blob 存储 / SAS 逻辑 | `backend/app.py` → `_upload_to_blob`、`_upload_reference_to_blob` |
| 部署配置 | `deploy_azure_appservice.sh`、`.github/workflows/main_tepmimages.yml`、`.github/workflows/azure-deploy.yml` |

## 7. 给新人的避坑提示

1. **装依赖用 `backend/requirements.txt`**，不要用根目录的 `requirements.txt`（其中含一行 `- temp`，会导致 `pip install` 报错）。
2. **任务状态存在内��字典 `_tasks` 中**（带 `threading.Lock`）：进程重启或使用多个 Gunicorn worker 时任务会丢失，会出现“任务不存在”。
3. **访问口令默认兜底值 `ai2026` 硬编码在 `backend/app.py` 中**，生产环境务必用环境变量 `ACCESS_CODE` 覆盖。
4. **缺少 `AZURE_OPENAI_API_KEY` 或 `AZURE_OPENAI_ENDPOINT` 时应用启动即失败**（`raise RuntimeError`）。
