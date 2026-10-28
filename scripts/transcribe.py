#!/usr/bin/env python3
"""把销售沟通录音转成文字稿（Markdown）。

用法：
    python scripts/transcribe.py <录音文件> [--out cases/xxx/transcript.md] [--backend api|local]

两种后端（在 config.env 里配置，见 config.env.example）：
  api   —— 任何兼容 OpenAI `/audio/transcriptions` 的接口：
           OpenAI（whisper-1 / gpt-4o-transcribe）、硅基流动 SiliconFlow（SenseVoice，中文效果好）、Groq 等。
  local —— 本机 faster-whisper，无需外部 API，但首次需要从 HuggingFace 下载模型，CPU 上较慢。

长录音会先用 ffmpeg 转成 16kHz 单声道 mp3，再按 STT_CHUNK_SECONDS 切片逐段识别，
每段前标注起始时间，方便回听核对。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config():
    """读取 config.env（KEY=VALUE），环境变量优先。"""
    cfg = {}
    env_file = ROOT / "config.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k.startswith("STT_"):
            cfg[k] = v
    return cfg


def fmt_ts(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def split_audio(src, workdir, chunk_seconds):
    """转码为 16kHz 单声道 64kbps mp3 并切片，返回 [(起始秒, 切片路径)]。"""
    duration = probe_duration(src)
    chunks = []
    start = 0.0
    idx = 0
    while start < duration:
        dst = Path(workdir) / f"chunk_{idx:03d}.mp3"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(chunk_seconds),
             "-i", str(src), "-ac", "1", "-ar", "16000", "-b:a", "64k", str(dst)],
            check=True,
        )
        chunks.append((start, dst))
        start += chunk_seconds
        idx += 1
    return duration, chunks


def transcribe_api(chunks, cfg, language):
    import requests

    base_url = cfg.get("STT_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key = cfg.get("STT_API_KEY")
    model = cfg.get("STT_MODEL", "whisper-1")
    if not api_key:
        sys.exit("缺少 STT_API_KEY：请在 config.env 中配置（参考 config.env.example）。")

    parts = []
    for i, (offset, path) in enumerate(chunks, 1):
        print(f"[{i}/{len(chunks)}] 识别 {fmt_ts(offset)} 起的片段…", file=sys.stderr)
        data = {"model": model, "response_format": "json"}
        if language:
            data["language"] = language
        for attempt in range(1, 4):
            try:
                with open(path, "rb") as f:
                    resp = requests.post(
                        f"{base_url}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        data=data,
                        files={"file": (path.name, f, "audio/mpeg")},
                        timeout=600,
                    )
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                text = resp.json().get("text", "").strip()
                break
            except Exception as e:  # 网络抖动重试，最后一次仍失败则退出
                if attempt == 3:
                    sys.exit(f"片段 {fmt_ts(offset)} 识别失败：{e}")
                print(f"  第 {attempt} 次失败（{e}），{2 ** attempt}s 后重试", file=sys.stderr)
                time.sleep(2 ** attempt)
        parts.append(f"**[{fmt_ts(offset)}]** {text}")
    return parts, f"api · {model} @ {base_url}"


def transcribe_local(src, cfg, language):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("未安装 faster-whisper：pip install faster-whisper")

    model_name = cfg.get("STT_LOCAL_MODEL", "large-v3")
    model = WhisperModel(model_name, device=cfg.get("STT_LOCAL_DEVICE", "cpu"),
                         compute_type=cfg.get("STT_LOCAL_COMPUTE", "int8"))
    segments, _ = model.transcribe(
        str(src), language=language or None, vad_filter=True,
        initial_prompt="以下是求职咨询的销售沟通录音，涉及简历、岗位、面试、陪跑服务。",
    )
    parts = []
    for seg in segments:
        print(f"  {fmt_ts(seg.start)} {seg.text.strip()[:40]}", file=sys.stderr)
        parts.append(f"**[{fmt_ts(seg.start)}]** {seg.text.strip()}")
    return parts, f"local · faster-whisper {model_name}"


def main():
    ap = argparse.ArgumentParser(description="录音转文字")
    ap.add_argument("audio", help="录音文件路径（m4a/mp3/wav/aac/amr/mp4 等 ffmpeg 支持的格式）")
    ap.add_argument("--out", help="输出 Markdown 路径；不填则打印到标准输出")
    ap.add_argument("--backend", choices=["api", "local"], help="覆盖 config.env 中的 STT_BACKEND")
    ap.add_argument("--language", help="语言代码，默认 zh；传空字符串表示自动识别")
    args = ap.parse_args()

    cfg = load_config()
    src = Path(args.audio).expanduser().resolve()
    if not src.exists():
        sys.exit(f"找不到录音文件：{src}")
    if not shutil.which("ffmpeg"):
        sys.exit("需要 ffmpeg，请先安装。")

    backend = args.backend or cfg.get("STT_BACKEND", "api")
    language = cfg.get("STT_LANGUAGE", "zh") if args.language is None else args.language

    if backend == "local":
        duration = probe_duration(src)
        parts, engine = transcribe_local(src, cfg, language)
    else:
        chunk_seconds = int(cfg.get("STT_CHUNK_SECONDS", "600"))
        with tempfile.TemporaryDirectory() as tmp:
            duration, chunks = split_audio(src, tmp, chunk_seconds)
            parts, engine = transcribe_api(chunks, cfg, language)

    md = "\n".join([
        f"# 录音转写：{src.name}",
        "",
        f"- 时长：{fmt_ts(duration)}",
        f"- 引擎：{engine}",
        f"- 转写时间：{datetime.now():%Y-%m-%d %H:%M}",
        "- 说明：机器转写未区分说话人，可能有同音错字，关键信息以销售确认为准。",
        "",
        "---",
        "",
        "\n\n".join(parts),
        "",
    ])
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"已写入 {out}（{len(md)} 字符）", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
