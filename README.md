# 销售方案助手

销售把客户沟通录音发给 Claude → Claude 转写成文字 → 先出一份**预生成确认单**（准备写什么、推荐哪条服务路径、有哪些需要确认的问题）→ 销售确认或补充意见 → Claude 生成完整求职服务方案。

## 使用流程（销售）

1. 在 Claude Code 里打开本项目，上传录音（m4a / mp3 / wav / amr 等都行），说一句“帮我出方案，客户叫 xxx”。
   没有录音、只有文字稿（飞书妙记、通义听悟等导出）也可以直接粘贴。
2. Claude 回复一份确认单。看一遍，回“确认”，或者直接写意见，例如：
   “主推改成通用陪跑；客户预算紧，不要提高阶方案；语气口语一点。”
3. Claude 生成完整方案，可直接复制发给客户。还要改就继续说，旧版本会自动保留。

## 首次配置（管理员）

### 1. 放入最新版方案 prompt
第一次使用时 Claude 会提示粘贴最新版 prompt，粘贴后自动保存为 `prompts/plan_prompt.md`。
以后要换新版，直接对 Claude 说“更新方案 prompt”并粘贴新内容，旧版自动归档到 `prompts/history/`。
（`prompts/history/v0-旧版方案示例.md` 是旧版方案成品，仅供对照。）

### 2. 录音转写（默认无需配置）
```bash
pip install -r requirements.txt
```
默认使用**项目内部署的本地小模型**，免费、不需要 API Key：

- **SenseVoice**（阿里开源的中文语音识别模型，自带标点），通过 sherpa-onnx 在 CPU 上运行；
- **说话人分离**（pyannote + 3D-Speaker），文字稿按“说话人A / 说话人B”分段，Claude 再判断谁是销售、谁是客户。

模型首次转写时自动从 GitHub 下载到 `models/`（约 260MB，不入库）。在 4 核 CPU 上，1 小时录音约 5 分钟转完。
默认按 2 人（销售 + 客户）区分；多人通话可在 `config.env` 里改 `STT_SPEAKERS`。

机器转写仍可能有同音错字，尤其是专有名词。`prompts/glossary.md` 是术语表，Claude 读文字稿时据此纠正；建议把服务名称、常见岗位名维护进去。

**备用：在线接口**。复制 `config.env.example` 为 `config.env`，设 `STT_BACKEND=api` 并填写 `STT_API_KEY`，可改用 Groq、OpenAI、硅基流动等兼容 OpenAI 格式的接口（需在云端环境的 Network access 中放行对应域名）。

## 目录结构

```
CLAUDE.md                          Claude 的总规则
.claude/skills/sales-plan/SKILL.md 完整工作流（转写 → 确认单 → 方案）
prompts/plan_prompt.md             当前生效的方案 prompt
prompts/history/                   历史 prompt 版本
prompts/glossary.md                术语表（纠正转写错字）
templates/brief_template.md        预生成确认单模板
scripts/transcribe.py              录音转文字（本地模型、区分说话人、带时间戳）
models/                            语音模型（自动下载，不入库）
scripts/prompt_admin.py            prompt 版本管理：status / set / history
cases/YYYYMMDD-客户/               每个客户：transcript.md、brief.md、feedback.md、plan.md
```

录音文件不入库（含客户隐私、体积大），文字稿和方案会保留在 `cases/`。
