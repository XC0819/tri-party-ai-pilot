# 总监主导的协作状态实验

对应 [Issue #6 / TASK-20261010-005](https://github.com/XC0819/tri-party-ai-pilot/issues/6)。Python 标准库，独立于未合并的 PR #5。全部修改在本目录。GitHub 是事件来源，两个窗口的中文摘要共享同一个状态对象。网页总监收到通知后处理当前会话，不会因 GitHub 更新自动后台醒来。

## 本地 CLI 与测试

在 `experiments/director_stateflow/` 执行：

```powershell
$env:PYTHONUTF8='1'
python -m unittest discover -s tests -v
python -m director_stateflow examples/awaiting_review.json --view both
python -m director_stateflow examples/checks_started.json --view both
```

CLI 仅读取本地 JSON、查询本机进程身份并输出 Markdown；默认不访问网络或浏览器。第二个示例是虚构的“已启动检查”事件，但没有真实 PID 记录时 CLI 会显示“未验证启动”，不会替虚构数据背书。若提供真实记录：`--poll-record <本地运行记录.json>`。

## 事件协议

GitHub 评论独立一行 `COLLAB_STATUS_V1`，其后为 JSON 对象。必填：`task_id, seq, status, owner, pr_url, head_sha, updated_at, next_action, poll_status, poll_interval_seconds, poll_deadline, evidence_url`。未知写 `none` / `unknown`；时间使用有时区的 ISO 8601；SHA 为完整小写 40 位。可选：`round, poll_run_id, poll_intent, completed`（字符串数组）、`trigger, subtask, milestones_done, milestones_total, user_approval_url, notification_status`（not_sent/sent/failed）。示例目录给出完整载荷。

同任务按 seq 排序；相同 seq 完全重复被忽略，不同内容产生冲突。较旧时间、SHA、轮次和不同 PR 不覆盖当前状态；非法回退拒绝。首次 PR 登记只在 awaiting_review；返工新 SHA 只在 reworking → awaiting_rereview，最多一轮。blocked/timed_out 必须说明原因及下一责任方。awaiting_user_approval 的 owner 必须为 user；closed 要有明确批准记录链接。程序不提供合并操作。角色是业务标签，不是加密身份认证；批准链接仍需人在执行有后果动作前核实。

状态/责任方：assigned、developing（Codex）；awaiting_review、reviewing、awaiting_rereview（ChatGPT）；changes_requested、reworking（Codex）；awaiting_user_approval、closed（user）。blocked/timed_out 由记录指明下一责任方。

摘要使用有效记录；`poll_intent=scheduled` 只表示拟运行。`poll_status=running` 字符本身不是证据：必须有匹配 run_id、任务/PR/SHA/轮次/截止/间隔、有效心跳、仍活着且创建时间相符的本机 PID。PID 复用拒绝；退出记录优先；未同步状态必须调用 `summary(..., synced=False)` 标出“尚未同步 GitHub”。通知是否成功单独显示。

## 五种明确标注的虚构示例

| 文件 | 场景 | 责任方 |
| --- | --- | --- |
| examples/awaiting_code.json | 等待 Codex 提交 | Codex |
| examples/awaiting_review.json | 等待总监审计，通知待发送 | ChatGPT |
| examples/checks_started.json | 假设已经启动两分钟检查；CLI 不凭示例确认运行 | ChatGPT |
| examples/reworking.json | 正在返工 | Codex |
| examples/awaiting_user.json | 技术通过，等待最终批准 | user |

examples/footers.md 展示相同状态下双方摘要。所有样例标有“虚构数据，不是实际日志”；不是本轮实测证据。

## 显式的有限期 GitHub 观察器

仅在用户已授权、待审草稿 PR 存在时显式启动：

```powershell
python -m director_stateflow.observe --pr <实际编号> --head <实际完整SHA> --round 1 --record <工作目录/runtime.json>
```

这是前台本地 Python 进程，不安装服务。固定仓库/分支、GET 只读 gh、120 秒周期，截止为第一次实际启动后最长 30 分钟，第二轮沿用原截止。每轮取 PR、Issue #6 评论、PR 会话评论、review 和 inline 评论；只接受 PR 上实际启动以后产生且 TASK/PR/SHA/round 匹配的 `AUDIT_DECISION_V1`。匹配 verdict/notes 冲突时退出 error，不自行选意见。权限/网络失败退出，未收到审计则截止退出。保存实际 PID/创建身份、开始、心跳、每次检查、已读记录、收到意见的延迟、结束时间；`.jsonl` 最后一条 exited 优先。真实事件回填 `github_state_events`，可包装为 `{"events": [...]} ` 输入离线 CLI。

审计评论 JSON 或逐行格式必含 `task_id, pr_number, head_sha, round, verdict, notes`，verdict 为 request_changes/approve/blocked。notes 只是数据，不执行任意代码或 shell。审计结果由协调方按任务范围处理；观察器不会修改 GitHub、返工或合并。第二轮仅在真实 request_changes、新 SHA 且一轮额度未消耗时允许重启原记录。

## 实战验收与边界

原始测试输出在 evidence/first-round-tests.txt，范围/退出码在 evidence/first-round-validation.json。GitHub PR 评论补充准确 SHA、真实轮询和停止记录。测试中的 mock 传输是单元验证，不作为 GitHub 实测；真实临时进程测试仅验证本机身份机制，不冒充审计轮询。真实双端显示必须以两个窗口实战消息证明，不能用格式化函数的两种输出冒充总监执行。

审计通知与最终交接必须使用 Codex 自己的侧边栏浏览器；发送前重新读取任务书和消息限制。计划最多每个实际轮次一次审计通知，最多一次最终交接，不形成重复通知循环。通知失败显示 blocked；总监技术通过后写 GitHub 最终 awaiting_user_approval 并通知用户。未获用户最终许可始终不关闭或合并 PR。公开仓库禁止正式代码、私有聊天、凭据；浏览器截图只保存本地。
