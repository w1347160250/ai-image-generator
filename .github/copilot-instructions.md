# GitHub Copilot Repository Instructions

## 1. 项目背景

本项目是一个部署在 Azure App Service 上的 AI 图片生成 Web 应用。

用户可以：

- 输入提示词生成图片；
- 上传最多 8 张参考图片；
- 选择图片尺寸和生成质量；
- 通过 Microsoft Entra ID 登录；
- 或在未登录时使用原有访问口令；
- 查询异步图片生成任务状态；
- 下载生成的图片。

后端调用 Azure OpenAI 图片模型生成或编辑图片，并使用 Azure Blob Storage 保存参考图片和生成结果。

当前部署信息：

- Azure App Service：`tepmimages`
- 默认部署分支：`main`
- Python 版本：3.11
- 主要部署工作流：`.github/workflows/main_tepmimages.yml`

Microsoft 登录和访问口令是并存的两种鉴权方式。任何改动都不得在没有明确需求的情况下移除访问口令兼容路径。

## 2. 技术栈

### 后端

- Python 3.11
- Flask
- Flask-CORS
- Gunicorn
- MSAL for Python
- OpenAI Python SDK
- Azure OpenAI
- Azure Storage Blob SDK
- Pillow
- Requests
- Python threading

主要文件：

- `backend/app.py`：Flask 应用、图片生成、文件上传、Blob Storage 和异步任务接口
- `backend/auth.py`：Microsoft Entra ID 登录、回调、状态查询和退出登录
- `backend/requirements.txt`：生产依赖

### 前端

- 原生 HTML
- 原生 CSS
- 原生 JavaScript
- Fetch API
- FormData
- Flask 静态文件托管

主要文件：

- `frontend/index.html`
- `frontend/style.css`
- `frontend/app.js`

不要在没有明确需求的情况下引入 React、Vue、Angular、Node.js 构建系统或其他前端框架。

### 测试

- pytest
- Flask test client
- monkeypatch
- 模拟 Azure OpenAI、Blob Storage 和 MSAL 行为

主要文件：

- `pytest.ini`
- `requirements-dev.txt`
- `tests/conftest.py`
- `tests/test_access_code.py`
- `tests/test_auth.py`

### 部署

- GitHub Actions
- Azure App Service
- Azure OIDC 登录
- `azure/login`
- `azure/webapps-deploy`

主要部署工作流为 `.github/workflows/main_tepmimages.yml`。

仓库中可能存在历史或重复部署工作流。修改部署配置前，应先确认哪个工作流实际负责 `tepmimages` 部署，避免同一提交触发重复部署。

## 3. 项目结构与职责

```text
backend/
  app.py                  Flask 主应用和图片生成逻辑
  auth.py                 Microsoft Entra ID 身份验证
  requirements.txt        生产依赖

frontend/
  index.html              页面结构
  app.js                  页面行为和 API 请求
  style.css               页面样式

tests/
  conftest.py             测试环境和公共夹具
  test_access_code.py     访问口令回归测试
  test_auth.py            Microsoft 登录与 Session 测试

.github/workflows/
  main_tepmimages.yml     主要 Azure 构建和部署流程

requirements.txt          引用后端生产依赖
requirements-dev.txt      pytest 等开发依赖
pytest.ini                pytest 配置
```

新增代码时，应优先放到职责相符的现有文件中。当功能明显超出单个文件职责时，可以提取新模块，但不要为了很小的改动进行大规模重构。

## 4. 代码风格

### Python

- 使用 4 个空格缩进；
- 函数和变量使用 `snake_case`；
- 常量使用 `UPPER_SNAKE_CASE`；
- 类使用 `PascalCase`；
- 私有辅助函数使用 `_` 前缀；
- 路由函数保持简短，将复杂处理提取为辅助函数；
- 对外部服务调用设置明确的超时时间；
- 对可能失败的 Azure、OpenAI、HTTP 和图片解析操作进行异常处理；
- 返回给用户的错误信息应清晰、简短，避免泄露内部凭据和完整异常堆栈；
- 服务端详细错误使用 `logger` 记录；
- 新增公共函数或复杂辅助函数时添加简短 docstring；
- 使用已有的 `jsonify` 返回 JSON；
- 保持 API 状态码语义一致；
- 不要使用裸 `except:`；
- 捕获异常时尽可能使用具体异常类型；
- 打开文件、图片或内存流后，确保资源被关闭；
- 修改共享任务状态时继续使用 `_tasks_lock`；
- 后台任务必须避免阻塞 Flask 请求线程。

当前项目没有配置 Black、Ruff、Flake8 或 isort。不要声称这些工具已经启用，也不要仅为了格式化而重写整个文件。

### JavaScript

- 使用 `const` 和 `let`，不要使用 `var`；
- 使用双引号，与现有代码保持一致；
- 使用 `async/await` 处理异步请求；
- Fetch 请求失败时给用户显示明确错误；
- 需要携带 Flask Session 的请求必须保留 `credentials: "same-origin"`；
- 使用现有的 `showError`、`hideError`、`showLoading`、`hideLoading` 等 UI 辅助函数；
- 不要直接把不可信文本拼接为 HTML；
- 用户、文件名或服务端返回值优先通过 `textContent` 写入页面；
- 修改 DOM ID 时必须同步更新 HTML、JavaScript 和测试；
- 保持无前端构建步骤的设计。

### HTML

- 页面语言保持为 `zh-CN`；
- 按钮明确设置 `type="button"`，除非它应提交表单；
- 表单字段必须有对应的 `<label>`；
- 保持基础无障碍属性；
- 动态区域应使用稳定、语义清晰的 ID；
- 不要无故添加第三方 CDN 脚本；
- 不要把密钥、Tenant ID 或 Client Secret 写入 HTML。

### CSS

- 延续当前深色玻璃拟态风格；
- 优先复用现有 class；
- 新样式必须兼容移动端；
- 保持 `max-width: 600px` 附近的响应式行为；
- 不要使用大量内联样式；
- 不要为小改动引入 CSS 框架。

## 5. API 与鉴权约束

### 鉴权模型

`POST /api/generate` 支持两种鉴权方式：

1. Flask Session 中存在有效的 `aad_user`；
2. 请求携带正确的 `access_code`。

修改生成接口时，必须保留这两条路径，除非任务明确要求移除其中一种。推荐继续通过 `is_request_authorized(getf)` 统一检查，不要在多个路由中重复实现不同版本的鉴权判断。

### Microsoft Entra ID

相关路由：

```text
GET  /api/auth/login
GET  /api/auth/callback
GET  /api/auth/status
GET  /api/auth/logout
POST /api/auth/logout
```

必须使用以下环境变量名称，拼写不可变更：

```text
AAD_CLIENT_ID
AAD_CLIENT_SECRET
AAD_TENANT_ID
AAD_REDIRECT_URI
SESSION_SECRET
```

约束：

- 使用 MSAL `ConfidentialClientApplication`；
- 登录应用必须配置为 Entra ID Web 应用，而不是公共客户端；
- 必须通过 MSAL 授权码流程完成登录；
- 不得自行跳过 `state`、nonce 或授权流程校验；
- 不得把 access token、refresh token 或 client secret 返回给前端；
- Session 中只保存应用真正需要的最小用户信息；
- 当前最小用户结构为 `id`、`name` 和 `username`；
- 退出登录时必须清除 `aad_user` 和未完成的 `aad_auth_flow`；
- 不得在日志中输出授权码、令牌、客户端密码或完整回调 URL；
- 不得把 Entra ID 用户登录配置与 GitHub Actions 的 Azure OIDC 部署身份混为一谈。

### Session

- `SESSION_SECRET` 必须来自环境变量；
- 不得在代码中提供生产默认值；
- 不得将 Session Secret 写入仓库；
- 修改 Session 结构时必须同步更新鉴权测试；
- 不得让前端布尔变量成为最终鉴权依据；
- 服务端 Session 始终是权限判断的最终来源。

### 图片上传

必须保持或加强以下限制：

- 最多上传 8 张参考图；
- 单张图片最大 10 MB；
- 仅接受图片 MIME 类型；
- 使用 Pillow 验证并转换为 RGB PNG；
- 不要仅依赖文件扩展名判断文件类型；
- 不要降低上传限制，除非需求明确说明原因；
- 不要把未验证的原始文件直接交给外部模型或永久存储。

### 异步任务

当前任务状态保存在进程内 `_tasks` 字典中。

- 访问 `_tasks` 时使用 `_tasks_lock`；
- 任务状态至少保持 `processing`、`completed`、`failed` 的现有语义；
- API 返回结构变化时同步更新前端轮询逻辑和测试；
- 不要假设内存任务可以跨进程、跨重启或跨实例共享；
- 如需持久化或多实例支持，应明确提出使用外部队列或存储，而不是暗中扩展当前字典实现。

## 6. 环境变量

生产代码不得硬编码以下值：

```text
ACCESS_CODE
SESSION_SECRET
AAD_CLIENT_ID
AAD_CLIENT_SECRET
AAD_TENANT_ID
AAD_REDIRECT_URI
AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT
AZURE_STORAGE_CONNECTION_STRING
AZURE_STORAGE_CONTAINER
AZURE_STORAGE_CONTAINER_GENERATED
AZURE_STORAGE_CONTAINER_REFERENCE
```

新增环境变量时必须：

1. 使用清晰、稳定的 `UPPER_SNAKE_CASE` 名称；
2. 在代码中通过 `os.environ` 读取；
3. 判断它是必需配置还是可选配置；
4. 为缺失的必需配置提供明确错误；
5. 更新相关测试和文档；
6. 不提交真实值；
7. 不在日志中打印真实值。

不要把客户端密码、API Key、Storage Connection String 或 Session Secret 放入 Python、JavaScript、HTML、CSS、测试快照、GitHub Actions 普通变量、错误消息、日志或 PR 描述。

## 7. 测试命令

### 安装生产和测试依赖

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt -r requirements-dev.txt
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

### 运行测试

```bash
pytest
```

或：

```bash
python -m pytest
```

鉴权测试：

```bash
pytest tests/test_auth.py
```

访问口令回归测试：

```bash
pytest tests/test_access_code.py
```

单个测试：

```bash
pytest tests/test_auth.py::test_auth_status_and_generate_with_aad_session
```

基础 Python 语法检查：

```bash
python -m compileall backend tests
```

### 本地启动

启动前必须配置必要的测试环境变量，然后运行：

```bash
python backend/app.py
```

默认地址为 `http://localhost:5001`。

也可以使用与 Azure 类似的 Gunicorn 启动方式：

```bash
gunicorn --chdir backend --bind=0.0.0.0:8000 --timeout 600 app:app
```

测试不得调用真实 Azure OpenAI、Blob Storage 或 Microsoft 登录服务。使用 mock、monkeypatch 或测试替身隔离外部依赖。

## 8. 新增或修改测试时的要求

每次行为变更必须添加或更新对应测试。

### 修改鉴权时至少覆盖

- 未登录状态；
- Microsoft 登录启动；
- 回调成功；
- 回调缺少 flow；
- state 校验失败；
- MSAL 返回错误；
- 登录后的状态查询；
- 登录 Session 可以调用图片生成接口；
- 退出登录清除 Session；
- AAD 未配置时访问口令仍然可用。

### 修改访问口令时至少覆盖

- 正确口令成功；
- 错误口令返回 403；
- 缺少口令且没有登录时返回 403；
- 登录 Session 不要求访问口令；
- 缺少 prompt 返回 400。

### 修改上传功能时至少覆盖

- 合法图片；
- 非图片文件；
- 空文件；
- 超过单文件大小限制；
- 超过图片数量限制；
- Pillow 无法解析的内容；
- 单图和多图请求。

### 修改异步任务时至少覆盖

- 创建任务返回 202；
- 返回 `task_id`；
- processing 状态；
- completed 状态；
- failed 状态；
- 不存在的任务返回 404。

测试中禁止使用真实生产 Secret 或真实 Azure 资源。

## 9. 禁止事项

生成或修改代码时禁止：

1. 将任何真实密钥、令牌、授权码或连接字符串提交到仓库；
2. 在日志中输出 Secret、access token、refresh token 或完整 OAuth 回调参数；
3. 删除访问口令兼容路径而不更新需求、前端和测试；
4. 仅依赖前端变量判断用户是否有权限；
5. 绕过 MSAL 授权码流程或 OAuth state 校验；
6. 将 Entra ID 登录配置成公共客户端后继续发送 Client Secret；
7. 将客户端密码传给浏览器；
8. 在生产代码中添加固定 `SESSION_SECRET`；
9. 使用默认访问口令作为生产安全保障；
10. 删除上传大小、数量或 MIME 类型校验；
11. 信任文件扩展名而不解析图片；
12. 在没有测试的情况下修改鉴权逻辑；
13. 在单元测试中访问真实 Azure 服务；
14. 修改 GitHub Actions 时暴露 Secret；
15. 未经确认直接修改 Azure 应用名称、部署槽位或目标订阅；
16. 在没有需求的情况下引入大型框架或大规模重构；
17. 改变现有 API 响应结构却不更新前端和测试；
18. 将用户可控内容直接插入 `innerHTML`；
19. 忽略共享内存任务状态的线程安全；
20. 为修复小问题而重新格式化无关文件；
21. 提交 `.venv`、`antenv`、缓存、部署包或生成图片；
22. 声称部署成功而未检查 GitHub Actions 的最终状态；
23. 将重复工作流中的失败误判为主要部署流程失败；
24. 在未验证目标工作流和目标环境前触发部署。

## 10. 生成代码时必须遵守的约束

Copilot 生成代码时必须：

1. 先阅读与任务直接相关的文件和测试；
2. 优先进行最小、局部、可回滚的改动；
3. 保持现有 Flask、原生 JavaScript 和 Azure 架构；
4. 保持 Microsoft Session 和访问口令双鉴权兼容；
5. 保持现有 API 路由兼容，除非需求明确要求破坏性变更；
6. 对所有外部网络请求设置超时；
7. 对 Azure OpenAI、Blob、MSAL 和图片解析失败进行安全处理；
8. 给用户返回可理解的中文错误；
9. 给服务端日志保留足够诊断信息，但不得记录敏感值；
10. 所有鉴权判断必须由后端完成；
11. 使用环境变量存储部署相关配置；
12. 使用已有依赖可以完成任务时，不增加新依赖；
13. 新增依赖时同步更新正确的 requirements 文件；
14. 修改 Python 行为时同步新增或更新 pytest 测试；
15. 修改 DOM 结构时同步检查 `frontend/app.js` 和 `frontend/style.css`；
16. 修改 API 返回值时同步更新前端调用代码；
17. 修改上传逻辑时保留图片数量、大小和格式限制；
18. 修改 `_tasks` 时保留锁保护；
19. 不假设 App Service 只有一个进程或永不重启；
20. 部署相关修改必须指出目标分支、工作流和 App Service；
21. 不得擅自执行部署、合并或修改生产环境配置；
22. 生成 PR 时说明行为变化、配置变化、测试结果和部署影响；
23. 对不确定的 Azure 或认证配置明确说明假设，不得虚构配置；
24. 不要覆盖用户已经在 Azure Portal 中设置的环境变量；
25. 不要在代码、测试、文档或示例中粘贴真实 Secret。

## 11. PR 前检查清单

### 代码

- [ ] 改动范围与任务一致；
- [ ] 没有无关重构或大面积格式变化；
- [ ] Python 代码可以导入和编译；
- [ ] 前端元素 ID 与 JavaScript 查询一致；
- [ ] API 请求和响应结构保持一致或已同步更新；
- [ ] 外部请求均设置超时；
- [ ] 共享任务状态使用锁保护；
- [ ] 用户错误信息清晰；
- [ ] 日志不包含敏感信息。

### 安全

- [ ] 没有提交 Secret、API Key、令牌或连接字符串；
- [ ] 没有输出 OAuth 授权码或完整回调 URL；
- [ ] 后端仍是最终鉴权来源；
- [ ] Microsoft 登录仍执行 state 校验；
- [ ] Session 中只保存最小用户信息；
- [ ] 访问口令兼容路径没有被意外破坏；
- [ ] 上传数量、大小、类型和图片解析校验仍然有效。

### 测试

- [ ] 已安装 `backend/requirements.txt` 和 `requirements-dev.txt`；
- [ ] `python -m compileall backend tests` 通过；
- [ ] `pytest` 通过；
- [ ] 新行为已有测试；
- [ ] 鉴权改动同时覆盖登录 Session 和访问口令；
- [ ] 测试没有调用真实 Azure 服务；
- [ ] 测试没有使用真实生产凭据。

### 配置和依赖

- [ ] 新依赖已加入正确的 requirements 文件；
- [ ] 没有重新引入无效 requirements 条目；
- [ ] 新环境变量已有明确名称和用途；
- [ ] 环境变量名称与代码读取名称完全一致；
- [ ] 没有在客户端暴露服务端配置；
- [ ] 没有把 GitHub OIDC 部署凭据与用户登录凭据混淆。

### 部署

- [ ] 已确认目标分支；
- [ ] 已确认主要工作流是 `.github/workflows/main_tepmimages.yml`；
- [ ] 已确认目标 App Service 是 `tepmimages`；
- [ ] 没有意外触发重复部署流程；
- [ ] GitHub Actions 的 build 和 deploy 均已检查；
- [ ] 部署后检查 `/api/health`；
- [ ] 鉴权改动部署后检查 `/api/auth/status`；
- [ ] Microsoft 登录改动已验证完整的登录、回调和退出流程；
- [ ] 原访问口令流程仍然可用。

## 12. PR 描述要求

PR 描述至少包含：

1. 改动目的；
2. 主要实现；
3. 受影响的接口或页面；
4. 新增或修改的环境变量；
5. 安全影响；
6. 兼容性影响；
7. 执行过的测试命令和结果；
8. 是否需要 Azure Portal 配置；
9. 是否会触发 App Service 部署；
10. 回滚方式。

推荐格式：

```markdown
## 改动目的

## 主要改动

## 配置变化

## 安全与兼容性

## 测试

## 部署与验证

## 回滚方式
```
