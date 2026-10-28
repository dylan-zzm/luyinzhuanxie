---
name: sales-plan
description: 销售把客户沟通录音（或文字稿）发来后，转写录音 → 按方案 prompt 先出“预生成确认单”给销售确认 → 根据销售意见生成完整求职服务方案。销售上传录音/文字稿、说“出方案”“生成方案”“确认”“改一下方案”、或要更新方案 prompt 时使用。
---

# 销售录音 → 求职服务方案

整个流程分三步，**第二步之后必须停下来等销售回复**，不能一口气直接写完整方案。

## 第 0 步：检查方案 prompt

```bash
python scripts/prompt_admin.py status
```

- 输出 `NOT_SET`：先回复销售（或管理员）——
  “目前还没有设置最新版的方案 prompt，请把最新版 prompt 直接粘贴给我。”
  拿到后写入 `cases/.incoming_prompt.md`（临时文件），运行
  `python scripts/prompt_admin.py set cases/.incoming_prompt.md`，然后删除临时文件，告诉对方新版本号。
  再把新 prompt 里的服务名称、价格同步到 `prompts/glossary.md`（替换旧的服务列表）。
  **没有 prompt 就不要生成方案**；`prompts/history/v0-旧版方案示例.md` 只是旧版示例，不能当 prompt 用。
- 任何时候有人说“更新 prompt / 换新版方案模板”并给出内容，同样用 `set` 替换（旧版会自动归档）。
- 输出 `OK`：读完整份 `prompts/plan_prompt.md`，后面两步都以它为准。

## 第 1 步：拿到文字稿

1. 建案例目录：`cases/YYYYMMDD-客户称呼/`（客户称呼从销售的话或录音里取；不确定就先用 `客户A` 之类，之后可改名）。
2. 找到录音文件：销售给了路径就用；没给就在工作目录和上传目录里找最近的音频
   （`find ~ /tmp -maxdepth 4 -newermt '-2 hours' -type f \( -iname '*.m4a' -o -iname '*.mp3' -o -iname '*.wav' -o -iname '*.aac' -o -iname '*.amr' -o -iname '*.mp4' -o -iname '*.ogg' -o -iname '*.flac' -o -iname '*.webm' \)`）。
   找不到就请销售提供路径，或直接粘贴文字稿。把录音复制进案例目录。
3. 转写：
   ```bash
   python scripts/transcribe.py cases/<目录>/<录音文件> --out cases/<目录>/transcript.md
   ```
   - 默认用项目内的本地小模型（SenseVoice + 说话人分离），免费离线；1 小时录音约 5 分钟，命令超时要设长一些。
     缺依赖先 `pip install -r requirements.txt`；首次运行会自动下载模型（约 260MB）。
   - 销售说有 3 人及以上参与（如客户带家长）：加 `--speakers <人数>`，不确定就 `--speakers -1`。
   - 模型下载失败（网络被拦）：如实告诉销售，让管理员按 README 放行 `github.com`；
     同时提供替代方案——把飞书妙记 / 通义听悟等导出的文字稿直接粘贴过来。
   - 销售直接给文字稿：原样存为 `cases/<目录>/transcript.md`。
   - **绝不编造录音内容**。转写失败就如实说失败。
4. 通读文字稿，对照 `prompts/glossary.md` 理解：
   - 说话人 A/B 是模型按声音分的，根据内容判断谁是销售（介绍服务、报价的一方）、谁是客户，在确认单里写明。
   - 同音错字（尤其服务名、公司名、岗位名）按术语表和语境纠正，拿不准的列入确认单的“转写存疑处”。

## 第 2 步：预生成确认单（停下来等确认）

按 `templates/brief_template.md` 的结构，结合 prompt 的要求，写 `cases/<目录>/brief.md`：
客户画像、核心问题判断、拟推荐服务路径（主推/备选/不建议）、方案章节大纲、需要销售确认的问题、转写存疑处。

要求：
- 每条客户信息尽量附录音时间点；录音里没聊到的写“未提及”，不要脑补。
- 服务名称与价格只用 prompt 里给出的，prompt 里没有的不要编。
- “需要销售确认的问题”控制在 3–6 条，挑真正影响方案走向的问。
- 把确认单全文发给销售，结尾提示：回“确认”即生成，或直接写修改意见。然后**结束本轮，等待回复**。

## 第 3 步：生成完整方案

销售回复后：
1. 把销售原话追加到 `cases/<目录>/feedback.md`（带时间）。
2. 销售意见优先级最高：与录音推断冲突时以销售为准；销售说不要写的内容不写。
3. 严格按 `prompts/plan_prompt.md` 的格式、语气、章节和服务列表生成完整方案，写入 `cases/<目录>/plan.md`，并把全文发给销售（方便直接复制给客户）。
4. 方案末尾不要附内部信息（时间点、置信度、确认问题等），这些只留在 brief.md。
5. 销售继续提修改：在原方案基础上改，旧版另存为 `plan_v1.md`、`plan_v2.md`…，`plan.md` 始终是最新版。

## 收尾

案例文件是唯一留存；如果仓库连接了 GitHub，完成后提交（不提交录音，`.gitignore` 已排除）：
`git add cases/<目录> && git commit -m "方案：<客户称呼>"`，再按会话说明推送。
