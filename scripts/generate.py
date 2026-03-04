import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlencode


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def get_ssl_context():
    """
    当前 8188 链接可能是自签名证书链；INSECURE_TLS=1 时跳过校验（仅用于测试）。
    """
    insecure = os.getenv("INSECURE_TLS", "").strip() in ("1", "true", "True", "yes", "YES")
    if insecure:
        return ssl._create_unverified_context()
    return ssl.create_default_context()


def create_zimage_turbo_workflow(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    seed: Optional[int],
    cfg: float,
    sampler_name: str,
    scheduler: str,
    denoise: float,
):
    """
    Z-Image-Turbo 的最小 workflow（来自 Dreamifly 的模板，做了抽取）。
    """
    # 兼容不同部署的模型文件名（可用环境变量覆盖）
    # 默认使用当前目标端点实际已安装的模型文件
    unet_name = os.getenv("ZIMAGE_UNET_NAME", "z_image_bf16.safetensors")
    clip_name = os.getenv("ZIMAGE_CLIP_NAME", "qwen_3_4b_fp8_mixed.safetensors")

    wf = {
        "3": {
            "inputs": {
                "seed": 47447417949230,
                "steps": 9,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["16", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["13", 0],
            },
            "class_type": "KSampler",
        },
        "6": {"inputs": {"text": "placeholder", "clip": ["18", 0]}, "class_type": "CLIPTextEncode"},
        "7": {"inputs": {"text": "blurry ugly bad", "clip": ["18", 0]}, "class_type": "CLIPTextEncode"},
        "8": {"inputs": {"samples": ["3", 0], "vae": ["17", 0]}, "class_type": "VAEDecode"},
        "9": {"inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]}, "class_type": "SaveImage"},
        "13": {"inputs": {"width": 1024, "height": 1024, "batch_size": 1}, "class_type": "EmptySD3LatentImage"},
        "16": {"inputs": {"unet_name": unet_name, "weight_dtype": "default"}, "class_type": "UNETLoader"},
        "17": {"inputs": {"vae_name": "ae.safetensors"}, "class_type": "VAELoader"},
        "18": {"inputs": {"clip_name": clip_name, "type": "lumina2", "device": "default"}, "class_type": "CLIPLoader"},
    }

    # 注入参数（与 Dreamifly 的 setZImageTurboT2IorkflowParams 同一含义）
    wf["13"]["inputs"]["width"] = width
    wf["13"]["inputs"]["height"] = height
    wf["6"]["inputs"]["text"] = prompt
    wf["7"]["inputs"]["text"] = negative_prompt
    wf["3"]["inputs"]["steps"] = steps
    wf["3"]["inputs"]["cfg"] = cfg
    wf["3"]["inputs"]["sampler_name"] = sampler_name
    wf["3"]["inputs"]["scheduler"] = scheduler
    wf["3"]["inputs"]["denoise"] = denoise
    if seed is not None:
        wf["3"]["inputs"]["seed"] = seed
    return wf


def http_json(
    url: str,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
    ctx=None,
    timeout: int = 180,
):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw.decode("utf-8"))


def http_bytes(url: str, ctx=None, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        return resp.read()


def main():
    base = os.getenv("COMFY_BASE_URL", "https://deployment-318-m5wiwdbe-8188.550w.link").rstrip("/")
    prompt = os.getenv(
        "PROMPT",
        "\n".join(
            [
                "在深蓝天际线下释放高压能量！捕捉城市峡谷中俏皮自信的瞬间，完美融合了水晶般清晰的Y2K美学风格。",
                "",
                "创作灵感：这张照片使用16mm超广角定焦镜头，从极低角度仰拍，以夸张表现动态姿势。",
                "标志性的视觉效果来源于对主体使用硬闪光灯，同时降低背景天空的曝光，从而营造出这种超现实、高饱和度的“日景夜拍”级电光蓝。",
            ]
        ),
    )
    negative = os.getenv(
        "NEGATIVE_PROMPT",
        "blurry, ugly, bad anatomy, deformed hands, extra fingers, low quality",
    )
    width = env_int("WIDTH", 1024)
    height = env_int("HEIGHT", 1024)
    # Turbo 模型通常少步数更稳，默认改为 9（接近工作流原始配置）
    steps = env_int("STEPS", 9)
    cfg = env_float("CFG", 1.0)
    denoise = env_float("DENOISE", 1.0)
    sampler_name = os.getenv("SAMPLER_NAME", "euler")
    scheduler = os.getenv("SCHEDULER", "simple")
    seed_raw = os.getenv("SEED")
    seed = env_int("SEED", 0) if seed_raw else None
    output_name = os.getenv("OUTPUT", "output.png")

    ctx = get_ssl_context()

    workflow = create_zimage_turbo_workflow(
        prompt=prompt,
        negative_prompt=negative,
        width=width,
        height=height,
        steps=steps,
        seed=seed,
        cfg=cfg,
        sampler_name=sampler_name,
        scheduler=scheduler,
        denoise=denoise,
    )
    prompt_url = f"{base}/prompt"
    history_base = f"{base}/history"
    view_base = f"{base}/view"

    print("POST", prompt_url)
    print(
        f"params width={width} height={height} steps={steps} cfg={cfg} "
        f"sampler={sampler_name} scheduler={scheduler} denoise={denoise} seed={seed}"
    )
    resp = http_json(prompt_url, method="POST", body={"prompt": workflow}, ctx=ctx, timeout=180)

    # 分支 1：封装服务直接返回 base64
    images = resp.get("images")
    if isinstance(images, list) and images and isinstance(images[0], str):
        out_path = Path(__file__).resolve().parent / output_name
        out_path.write_bytes(base64.b64decode(images[0]))
        print("saved(base64):", out_path)
        return

    # 分支 2：原生 ComfyUI 返回 prompt_id
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"unexpected response keys={list(resp.keys())}")

    print("prompt_id:", prompt_id)

    # 轮询 history
    history_url = f"{history_base}/{prompt_id}"
    item = None
    for i in range(60):
        data = http_json(history_url, ctx=ctx, timeout=60)
        item = data.get(prompt_id)
        if item and (item.get("outputs") or {}):
            break
        time.sleep(2)

    if not item:
        raise RuntimeError("history timeout: no record for prompt_id")

    outputs = item.get("outputs") or {}
    # 我们的 workflow 里 SaveImage 节点 id 固定为 "9"
    save_out = outputs.get("9") or {}
    out_images = save_out.get("images") or []
    if not out_images:
        # fallback：任意找一个带 images 的输出节点
        for _, v in outputs.items():
            imgs = (v or {}).get("images") or []
            if imgs:
                out_images = imgs
                break

    if not out_images:
        raise RuntimeError(f"no images found in outputs. outputs_keys={list(outputs.keys())}")

    img0 = out_images[0]
    filename = img0.get("filename")
    subfolder = img0.get("subfolder", "")
    ftype = img0.get("type", "output")

    qs = urlencode({"filename": filename, "subfolder": subfolder, "type": ftype})
    view_url = f"{view_base}?{qs}"
    print("GET", view_url)
    blob = http_bytes(view_url, ctx=ctx, timeout=180)

    out_path = Path(__file__).resolve().parent / output_name
    out_path.write_bytes(blob)
    print("saved(file):", out_path)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        body = e.read()
        print("HTTPError:", e.code, e.reason)
        print(body[:1000])
        raise

