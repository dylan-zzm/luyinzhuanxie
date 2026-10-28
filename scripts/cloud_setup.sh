#!/bin/bash
# 云端环境初始化脚本：把整个文件内容粘贴到 Claude Code 云端环境设置的 “Setup script” 里。
# 作用：预装转写依赖、预下载语音模型。云端会把结果做成快照缓存，之后每个新会话开箱即用，不再重复下载。
# 约 1 分钟完成（缓存要求 5 分钟内）。缓存大约每 7 天、或修改脚本/网络设置后自动重建一次。
set -euo pipefail

pip install -q "sherpa-onnx>=1.12" numpy "requests>=2.31"

MODELS="$HOME/.cache/sales-plan-assistant/models"
B=https://github.com/k2-fsa/sherpa-onnx/releases/download
mkdir -p "$MODELS" && cd "$MODELS"

[ -f sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx ] ||
  curl -fsSL "$B/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2" | tar xj
[ -f sherpa-onnx-pyannote-segmentation-3-0/model.onnx ] ||
  curl -fsSL "$B/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" | tar xj
[ -f 3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx ] ||
  curl -fsSL -o 3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx \
    "$B/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx"
echo "语音模型已就绪：$MODELS"
