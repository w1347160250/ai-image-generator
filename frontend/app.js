const API_BASE = "";

let currentImageUrl = null;
let selectedFile = null;

async function generateImage() {

    const accessCode = document.getElementById("accessCode").value.trim();
    const prompt = document.getElementById("prompt").value.trim();
    if (!accessCode) {
        showError("请输入访问口令");
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
        const requestOptions = { method: "POST" };


        if (selectedFile) {
            const formData = new FormData();
            formData.append("access_code", accessCode);
            formData.append("prompt", prompt);
            formData.append("size", size);
            formData.append("quality", quality);
            formData.append("image", selectedFile);
            requestOptions.body = formData;
        } else {
            requestOptions.headers = { "Content-Type": "application/json" };
            requestOptions.body = JSON.stringify({ access_code: accessCode, prompt, size, quality });
        }

        const resp = await fetch(`${API_BASE}/api/generate`, requestOptions);

        const data = await resp.json();

        if (!resp.ok) {
            throw new Error(data.error || "生成失败");
        }

        currentImageUrl = data.image_url;
        const img = document.getElementById("resultImage");
        img.src = data.image_url;
        showResult();
    } catch (err) {
        showError(err.message);
    } finally {
        hideLoading();
        btn.disabled = false;
        btn.textContent = "生成图片";
    }
}

function handleImageSelected(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) {
        clearSelectedImage();
        return;
    }

    if (!file.type.startsWith("image/")) {
        showError("请上传图片文件");
        clearSelectedImage();
        return;
    }

    selectedFile = file;
    const reader = new FileReader();
    reader.onload = () => {
        document.getElementById("previewImage").src = reader.result;
        document.getElementById("previewArea").classList.remove("hidden");
    };
    reader.readAsDataURL(file);
}

function clearSelectedImage() {
    selectedFile = null;
    document.getElementById("imageInput").value = "";
    document.getElementById("previewImage").src = "";
    document.getElementById("previewArea").classList.add("hidden");
}

function downloadImage() {
    if (!currentImageUrl) return;
    const link = document.createElement("a");
    link.href = currentImageUrl;
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

document.getElementById("imageInput").addEventListener("change", handleImageSelected);
