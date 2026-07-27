const API_BASE = "";

let currentImageUrl = null;
let selectedFiles = [];
let isMicrosoftAuthenticated = false;

async function loadAuthStatus() {
    const status = document.getElementById("authStatus");
    const loginBtn = document.getElementById("loginBtn");
    const logoutBtn = document.getElementById("logoutBtn");
    const accessCodeGroup = document.getElementById("accessCodeGroup");

    try {
        const resp = await fetch(`${API_BASE}/api/auth/status`, {
            credentials: "same-origin",
        });
        if (!resp.ok) {
            throw new Error("无法读取登录状态");
        }

        const data = await resp.json();
        isMicrosoftAuthenticated = Boolean(data.authenticated);

        if (isMicrosoftAuthenticated) {
            const user = data.user || {};
            const displayName = user.name || user.username || "Microsoft 用户";
            status.textContent = `已登录：${displayName}`;
            status.classList.add("authenticated");
            loginBtn.classList.add("hidden");
            logoutBtn.classList.remove("hidden");
            accessCodeGroup.classList.add("hidden");
        } else {
            showLoggedOutState();
        }
    } catch (err) {
        isMicrosoftAuthenticated = false;
        status.textContent = "Microsoft 登录状态暂不可用，可继续使用访问口令";
        status.classList.remove("authenticated");
        loginBtn.classList.remove("hidden");
        logoutBtn.classList.add("hidden");
        accessCodeGroup.classList.remove("hidden");
    }
}

function showLoggedOutState() {
    isMicrosoftAuthenticated = false;
    const status = document.getElementById("authStatus");
    status.textContent = "尚未登录，可使用 Microsoft 登录或访问口令";
    status.classList.remove("authenticated");
    document.getElementById("loginBtn").classList.remove("hidden");
    document.getElementById("logoutBtn").classList.add("hidden");
    document.getElementById("accessCodeGroup").classList.remove("hidden");
}

async function logoutMicrosoft() {
    hideError();
    try {
        const resp = await fetch(`${API_BASE}/api/auth/logout`, {
            method: "POST",
            credentials: "same-origin",
        });
        if (!resp.ok) {
            throw new Error("退出登录失败，请稍后重试");
        }
        document.getElementById("accessCode").value = "";
        showLoggedOutState();
    } catch (err) {
        showError(err.message);
    }
}

async function generateImage() {
    const accessCode = document.getElementById("accessCode").value.trim();
    const prompt = document.getElementById("prompt").value.trim();
    if (!isMicrosoftAuthenticated && !accessCode) {
        showError("请先使用 Microsoft 登录，或输入访问口令");
        return;
    }
    if (!prompt) {
        showError("请输入图片描述");
        return;
    }

    const size = document.getElementById("size").value;
    const quality = document.getElementById("quality").value;
    const btn = document.getElementById("generateBtn");

    hideError();
    hideResult();
    showLoading();
    btn.disabled = true;
    btn.textContent = "生成中...";

    try {
        const requestOptions = {
            method: "POST",
            credentials: "same-origin",
        };

        if (selectedFiles.length > 0) {
            const formData = new FormData();
            if (accessCode) formData.append("access_code", accessCode);
            formData.append("prompt", prompt);
            formData.append("size", size);
            formData.append("quality", quality);
            selectedFiles.forEach((file) => formData.append("images", file));
            requestOptions.body = formData;
        } else {
            requestOptions.headers = { "Content-Type": "application/json" };
            requestOptions.body = JSON.stringify({ access_code: accessCode, prompt, size, quality });
        }

        const resp = await fetch(`${API_BASE}/api/generate`, requestOptions);

        let data;
        const contentType = resp.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            data = await resp.json();
        } else {
            throw new Error(`服务器错误 (${resp.status})：可能是请求超时，请稍后重试。`);
        }

        if (!resp.ok && resp.status !== 202) {
            throw new Error(data.error || "生成失败");
        }

        if (data.task_id) {
            document.querySelector("#loading p").textContent = "AI 正在生成图片，请耐心等待...";
            const result = await pollTask(data.task_id);
            if (result.status === "completed" && result.image_url) {
                currentImageUrl = result.image_url;
                document.getElementById("resultImage").src = result.image_url;
                showResult();
            } else {
                throw new Error(result.error || "生成失败，请重试。");
            }
        } else if (data.image_url) {
            currentImageUrl = data.image_url;
            document.getElementById("resultImage").src = data.image_url;
            showResult();
        }
    } catch (err) {
        showError(err.message);
    } finally {
        hideLoading();
        btn.disabled = false;
        btn.textContent = "生成图片";
    }
}

function handleImageSelected(event) {
    const files = Array.from(event.target.files || []);
    if (files.length === 0) {
        clearSelectedImage();
        return;
    }

    const invalid = files.find((file) => !file.type.startsWith("image/"));
    if (invalid) {
        showError("仅支持上传图片文件");
        clearSelectedImage();
        return;
    }

    selectedFiles = files;
    const grid = document.getElementById("previewGrid");
    grid.innerHTML = "";

    selectedFiles.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = () => {
            const item = document.createElement("div");
            item.className = "preview-item";
            item.innerHTML = `<img src="${reader.result}" alt="参考图 ${index + 1}"><span>${file.name}</span>`;
            grid.appendChild(item);
        };
        reader.readAsDataURL(file);
    });

    document.getElementById("previewArea").classList.remove("hidden");
}

function clearSelectedImage() {
    selectedFiles = [];
    document.getElementById("imageInput").value = "";
    document.getElementById("previewGrid").innerHTML = "";
    document.getElementById("previewArea").classList.add("hidden");
}

async function downloadImage() {
    if (!currentImageUrl) return;
    try {
        const resp = await fetch(currentImageUrl);
        const blob = await resp.blob();
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        link.download = `ai-image-${ts}.png`;
        link.click();
        URL.revokeObjectURL(blobUrl);
    } catch (err) {
        window.open(currentImageUrl, "_blank");
    }
}

function showLoading() {
    document.getElementById("loading").classList.remove("hidden");
}
function hideLoading() {
    document.getElementById("loading").classList.add("hidden");
}
function showError(msg) {
    const el = document.getElementById("error");
    el.textContent = msg;
    el.classList.remove("hidden");
}
function hideError() {
    document.getElementById("error").classList.add("hidden");
}
function showResult() {
    document.getElementById("resultArea").classList.remove("hidden");
}
function hideResult() {
    document.getElementById("resultArea").classList.add("hidden");
}

document.getElementById("prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        generateImage();
    }
});

document.getElementById("imageInput").addEventListener("change", handleImageSelected);

async function pollTask(taskId) {
    const maxAttempts = 120;
    for (let i = 0; i < maxAttempts; i++) {
        await new Promise((r) => setTimeout(r, 5000));
        try {
            const resp = await fetch(`${API_BASE}/api/task/${taskId}`);
            const task = await resp.json();
            if (task.status === "completed" || task.status === "failed") {
                return task;
            }
            const elapsed = (i + 1) * 5;
            document.querySelector("#loading p").textContent = `AI 正在生成图片，已等待 ${elapsed} 秒...`;
        } catch (err) {
            // 网络短暂异常时继续轮询。
        }
    }
    return { status: "failed", error: "生成超时，请稍后重试。" };
}

loadAuthStatus();
