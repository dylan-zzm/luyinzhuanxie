# 销售方案助手

本仓库用于：销售发来客户沟通录音 → 转写成文字 → 按方案 prompt 先出“预生成确认单” → 销售确认/补充意见 → 生成完整求职服务方案。

- 只要销售发来录音、文字稿，或提到出方案/改方案/确认/更新 prompt，就使用 `sales-plan` skill（`.claude/skills/sales-plan/SKILL.md`），按里面的步骤走。
- 用中文和销售沟通，语气简洁直接；销售大多不懂技术，不要让他们跑命令，命令由你执行。
- 当前生效的方案 prompt：`prompts/plan_prompt.md`。若内容含 `PROMPT_NOT_SET`，先请使用者粘贴最新版 prompt 并用 `scripts/prompt_admin.py set` 替换，再继续。
- 预生成确认单发出后必须等销售回复，不能跳过确认直接写完整方案。
- 不编造录音里没有的客户信息，不编造 prompt 里没有的服务和价格。
- 每个客户一个目录：`cases/YYYYMMDD-客户称呼/`，内含 transcript.md、brief.md、feedback.md、plan.md。
