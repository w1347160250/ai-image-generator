const API_BASE = "";

let currentImageData = null;

async function generateImage() {
    const prompt = document.getElementById("prompt").value.trim();
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
        const resp = await fetch(`${API_BASE}/api/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt, size, quality }),
        });

        const data = await resp.json();

        if (!resp.ok) {
            throw new Error(data.error || "生成失败");
        }

        currentImageData = data.image;
        const img = document.getElementById("resultImage");
        img.src = `data:image/png;base64,${data.image}`;
        showResult();
    } catch (err) {
        showError(err.message);
    } finally {
        hideLoading();
        btn.disabled = false;
        btn.textContent = "生成图片";
    }
}

function downloadImage() {
    if (!currentImageData) return;
    const link = document.createElement("a");
    link.href = `data:image/png;base64,${currentImageData}`;
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    link.download = `ai-image-${ts}.png`;
    link.click();
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

// Enter 键触发生成
document.getElementById("prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        generateImage();
    }
});
