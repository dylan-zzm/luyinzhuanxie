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

### 2. 配置录音转写
```bash
cp config.env.example config.env
pip install -r requirements.txt
```
在 `config.env` 里选一种：

| 方案 | 配置 | 说明 |
|---|---|---|
| 硅基流动 SenseVoice（默认，中文推荐） | `STT_BASE_URL=https://api.siliconflow.cn/v1`，填 `STT_API_KEY` | 国内可用，便宜 |
| OpenAI | `STT_BASE_URL=https://api.openai.com/v1`，`STT_MODEL=gpt-4o-transcribe` | |
| Groq | `STT_BASE_URL=https://api.groq.com/openai/v1`，`STT_MODEL=whisper-large-v3` | 快 |
| 本机 faster-whisper | `STT_BACKEND=local`，`pip install faster-whisper` | 不用 API Key，但要能下载模型、CPU 慢 |

**云端环境注意**：Claude Code 云端会话默认网络受限，需要在环境设置的 Network access 里放行所用转写服务的域名（如 `api.siliconflow.cn`；本机模型则放行 `huggingface.co`）。API Key 建议放到环境变量 `STT_API_KEY` 中，不要提交到仓库。

## 目录结构

```
CLAUDE.md                          Claude 的总规则
.claude/skills/sales-plan/SKILL.md 完整工作流（转写 → 确认单 → 方案）
prompts/plan_prompt.md             当前生效的方案 prompt
prompts/history/                   历史 prompt 版本
templates/brief_template.md        预生成确认单模板
scripts/transcribe.py              录音转文字（自动切片、带时间戳）
scripts/prompt_admin.py            prompt 版本管理：status / set / history
cases/YYYYMMDD-客户/               每个客户：transcript.md、brief.md、feedback.md、plan.md
```

录音文件不入库（含客户隐私、体积大），文字稿和方案会保留在 `cases/`。
