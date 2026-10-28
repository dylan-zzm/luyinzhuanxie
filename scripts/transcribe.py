#!/usr/bin/env python3
"""把销售沟通录音转成文字稿（Markdown）。

用法：
    python scripts/transcribe.py <录音文件> [--out cases/xxx/transcript.md] [--speakers 2]

两种后端（config.env 中 STT_BACKEND，见 config.env.example）：
  local（默认）—— 项目内部署的小模型，免费、离线：
           sherpa-onnx + SenseVoice（阿里开源中文识别模型，带标点）
           + pyannote 分段 / 3D-Speaker 声纹（区分说话人：销售 vs 客户）。
           模型首次使用时自动从 GitHub 下载到 models/（约 190MB）。
  api   —— 任何兼容 OpenAI `/audio/transcriptions` 的在线接口（Groq、OpenAI、硅基流动等），作为备用。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
SAMPLE_RATE = 16000
RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SENSE_VOICE = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
SEGMENTATION = "sherpa-onnx-pyannote-segmentation-3-0"
EMBEDDING = "3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx"
MAX_PIECE_SECONDS = 20  # SenseVoice 适合 30 秒以内的片段，长段落在 10–20 秒间的停顿处切开
MIN_PIECE_SECONDS = 10


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


# ---------------------------------------------------------------- local 后端

def ensure_models():
    """缺模型时从 sherpa-onnx 的 GitHub Releases 下载。"""
    MODELS.mkdir(exist_ok=True)
    downloads = [
        (MODELS / SENSE_VOICE / "model.int8.onnx", f"{RELEASES}/asr-models/{SENSE_VOICE}.tar.bz2"),
        (MODELS / SEGMENTATION / "model.onnx", f"{RELEASES}/speaker-segmentation-models/{SEGMENTATION}.tar.bz2"),
        (MODELS / EMBEDDING, f"{RELEASES}/speaker-recongition-models/{EMBEDDING}"),
    ]
    for target, url in downloads:
        if target.exists():
            continue
        print(f"下载模型 {url.rsplit('/', 1)[1]} …", file=sys.stderr)
        tmp = MODELS / (url.rsplit("/", 1)[1] + ".part")
        urllib.request.urlretrieve(url, tmp)
        if url.endswith(".tar.bz2"):
            with tarfile.open(tmp) as tar:
                tar.extractall(MODELS, filter="data")
            tmp.unlink()
        else:
            tmp.rename(target)


def load_audio(src):
    """用 ffmpeg 解码为 16kHz 单声道 float32。"""
    import numpy as np

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def split_long(samples, start, end):
    """把超过 MAX_PIECE_SECONDS 的段落在音量最低处切开，返回 [(start, end)]（秒）。"""
    import numpy as np

    pieces = []
    frame = int(0.03 * SAMPLE_RATE)
    while end - start > MAX_PIECE_SECONDS:
        lo, hi = int((start + MIN_PIECE_SECONDS) * SAMPLE_RATE), int((start + MAX_PIECE_SECONDS) * SAMPLE_RATE)
        window = samples[lo:hi]
        n = len(window) // frame
        energy = (window[: n * frame].reshape(n, frame) ** 2).mean(axis=1)
        cut = start + MIN_PIECE_SECONDS + int(np.argmin(energy)) * frame / SAMPLE_RATE
        pieces.append((start, cut))
        start = cut
    pieces.append((start, end))
    return pieces


def diarize(samples, num_speakers):
    import sherpa_onnx as so

    config = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(MODELS / SEGMENTATION / "model.onnx")),
            num_threads=os.cpu_count() or 2,
        ),
        embedding=so.SpeakerEmbeddingExtractorConfig(
            model=str(MODELS / EMBEDDING), num_threads=os.cpu_count() or 2),
        clustering=so.FastClusteringConfig(num_clusters=num_speakers, threshold=0.5),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    result = so.OfflineSpeakerDiarization(config).process(samples).sort_by_start_time()
    order = {}  # 按首次开口的顺序编号：先说话的是 A
    return [(s.start, s.end, order.setdefault(s.speaker, len(order))) for s in result]


def transcribe_local(src, cfg, language, num_speakers):
    try:
        import sherpa_onnx as so
    except ImportError:
        sys.exit("未安装 sherpa-onnx：pip install -r requirements.txt")
    ensure_models()

    samples = load_audio(src)
    duration = len(samples) / SAMPLE_RATE

    t0 = time.time()
    print("区分说话人…", file=sys.stderr)
    segments = diarize(samples, num_speakers)  # 同时滤掉静音、音乐等非人声
    print(f"  得到 {len(segments)} 段（{time.time() - t0:.0f}s）", file=sys.stderr)

    sv = MODELS / SENSE_VOICE
    recognizer = so.OfflineRecognizer.from_sense_voice(
        model=str(sv / "model.int8.onnx"), tokens=str(sv / "tokens.txt"),
        language=language or "auto", use_itn=True, num_threads=os.cpu_count() or 2,
    )
    t0 = time.time()
    lines = []  # [(start, speaker, text)]，同一说话人连续的段落合并
    for i, (start, end, speaker) in enumerate(segments, 1):
        texts = []
        for s, e in split_long(samples, start, end):
            stream = recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, samples[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)])
            recognizer.decode_stream(stream)
            texts.append(stream.result.text.strip())
        text = "".join(texts)
        if not text:
            continue
        if lines and lines[-1][1] == speaker:
            lines[-1] = (lines[-1][0], speaker, lines[-1][2] + text)
        else:
            lines.append((start, speaker, text))
        if i % 50 == 0:
            print(f"  识别进度 {i}/{len(segments)}", file=sys.stderr)
    print(f"  识别完成（{time.time() - t0:.0f}s）", file=sys.stderr)

    parts = []
    for start, speaker, text in lines:
        parts.append(f"**[{fmt_ts(start)}]** 说话人{chr(ord('A') + speaker)}：{text}")
    return duration, parts, "local · SenseVoice + 说话人分离"


# ---------------------------------------------------------------- api 后端

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


def main():
    ap = argparse.ArgumentParser(description="录音转文字")
    ap.add_argument("audio", help="录音文件路径（m4a/mp3/wav/aac/amr/mp4 等 ffmpeg 支持的格式）")
    ap.add_argument("--out", help="输出 Markdown 路径；不填则打印到标准输出")
    ap.add_argument("--backend", choices=["api", "local"], help="覆盖 config.env 中的 STT_BACKEND")
    ap.add_argument("--language", help="语言代码，默认 zh；传空字符串表示自动识别")
    ap.add_argument("--speakers", type=int,
                    help="说话人数（仅 local）：默认 2（销售+客户）；-1 自动判断")
    args = ap.parse_args()

    cfg = load_config()
    src = Path(args.audio).expanduser().resolve()
    if not src.exists():
        sys.exit(f"找不到录音文件：{src}")
    if not shutil.which("ffmpeg"):
        sys.exit("需要 ffmpeg，请先安装。")

    backend = args.backend or cfg.get("STT_BACKEND", "local")
    language = cfg.get("STT_LANGUAGE", "zh") if args.language is None else args.language
    speakers = args.speakers if args.speakers is not None else int(cfg.get("STT_SPEAKERS", "2"))

    if backend == "local":
        duration, parts, engine = transcribe_local(src, cfg, language, speakers)
    else:
        chunk_seconds = int(cfg.get("STT_CHUNK_SECONDS", "600"))
        with tempfile.TemporaryDirectory() as tmp:
            duration, chunks = split_audio(src, tmp, chunk_seconds)
            parts, engine = transcribe_api(chunks, cfg, language)

    note = "说话人 A/B 由模型按声音区分，谁是销售需结合内容判断；" if backend == "local" else "未区分说话人；"
    md = "\n".join([
        f"# 录音转写：{src.name}",
        "",
        f"- 时长：{fmt_ts(duration)}",
        f"- 引擎：{engine}",
        f"- 转写时间：{datetime.now():%Y-%m-%d %H:%M}",
        f"- 说明：{note}机器转写可能有同音错字，关键信息以销售确认为准。",
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
