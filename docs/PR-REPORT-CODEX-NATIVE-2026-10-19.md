# Codex 原生接入本地验证报告

基线：147170f7a89e9cfa71e4e97966e34183087a3fc2；分支 codex-integration。

## 一、核心特性

Codex 账号聊天使用 `codex://local`，通过安装在本机的 Codex CLI 复用 auth.json；默认 gpt-6-luna / low。不复制账号令牌，不要求 Cockpit 或本地 HTTP 转发。聊天、额度查询共用长驻 app-server。macOS 辅助包声明 LSUIElement/LSBackgroundOnly，复制可执行文件后重新 ad-hoc 签名，保留原厂安装不变。

会话监控在应用进程内只读本地 JSONL，通过 Qt queued signal 呈现；只有当前未结束的根会话参与分配，单宠接全部，多宠按排序轮询均分（3/2 -> 2/1）。结束的历史会话和子代理不占分组。不定时写用户配置、不激活窗口。动画沿用现有行为控制器和素材库。

## 二、修改文件说明

- 新增 `pet/codex_sessions.py`：纯状态收敛和均衡分配。
- 新增 `pet/codex_runtime.py`：单进程读取、Qt 排队呈现和额度采样生命周期。
- 新增 `pet/codex_rpc.py`：长驻协议客户端及后台辅助包。
- 修改 `pet/multi_window_shared.py`：共享服务启动、停止收口。
- 修改 `pet/chat/providers.py`：本地账号 provider 和连接测试。
- 新增 `resources/codex-island-extensions/`：只读额度快照的两个信息段。
- 修改 `scripts/build_macos.sh`：随 macOS 包携带额度段。
- 新增 `tests/test_codex_sessions.py`、`tests/test_codex_provider.py`、`tests/test_codex_runtime.py`：分配、结束、唯一子宠路由和 provider 检查。

增删行数以交付的源码 diff 为准，构建产物不提交。

## 三、实现要点

业务配置保留原有模型连接结构，base_url 使用 codex://local 选择账号通道；agent_link.codex 控制会话追踪。额度段 codex_5h/codex_week 读取配置目录 codex-quota.json，失败或超过420秒按不可用处理。后台查询每180秒一次。不会自动购买额度或使用重置券。

当前实现是文本聊天：回复完整生成后交给现有窗口，未实现逐字增量和图片输入。现有配置页面尚无专用的 Codex 账号选择按钮。

## 四、性能分析

环境：macOS arm64，Python 3.11.15，PySide6 6.12.0。

- timeit 10000次：100会话、2宠分配平均9.52微秒/次。
- timeit 100000次：单条结束事件收敛平均0.06微秒/次。
- 真机两次额度查询复用同一 Codex PID；随后聊天返回“原生接入成功”。
- 启动44秒时单次 ps 样本：桌宠RSS303664 KiB，CPU21%；辅助进程RSS189072 KiB，CPU0%。这是瞬时样本，不是稳态基准，也没有旧版同条件对照，不能据此宣称总CPU降低。
- 新增两条后台线程（会话1Hz、额度180秒）；额度有网络查询，会话只增量读取本地文件。首次复制缓存可执行文件产生磁盘开销；查询复用连接，不按每次查询复制/启动。长期内存增长尚未压测。

## 五、实机运行记录

- 已从本机 auth.json 通过官方 CLI 验证额度和聊天；不输出认证材料。
- 已构建 macOS arm64 .app，帧序列106段、OCR模型摘要、语音依赖、中文编码和Bridge零依赖门通过。
- 本机启动新包，codex-quota.json 写入 ok=true 及真实额度窗口；保持 active slots=[1]，没有新增宠物。
- 已停用旧的三个 LaunchAgent，避免与应用内服务并行。
- 48项新增/相关测试通过，ruff通过；全量测试结果另见交付验证记录。
- CUA对透明合成窗的截图为全白、辅助功能树只有dialog，无法可靠定位宠物或观测其他应用输入焦点。因此未宣称工作动画、跨屏碰撞及输入不被打断已通过目视验收；后台标记和无配置重载仅是实现及进程级证据。

## 六、风险与未验证

本地会话日志不是稳定公开订阅协议；强制退出且无结束事件可能残留忙碌状态。会话按排序轮询分配，成员变化会重新分配，尚不是最小迁移算法。取消聊天会停止显示，但尚不立即中断正在执行的Codex turn。macOS首启后台包装/系统签名策略需要更多真机环境验证。Windows/Linux未打包验收。

## 七、最终复核补充

- Qt queued signal 回归通过，唯一1号子宠接收全部会话，3会话/2宠按2/1分配。
- 实际最终包日志：`Codex session routing: slot=1 state=working sessions=3`。
- 48项相关测试通过，报告契约与新增测试206项通过，ruff通过。
- 全量测试8407项在88%被会话中断；唯一已出现失败是上游禁止Codex文案规则，与新增集成冲突，已缩小豁免范围并单测通过。剩余部分从85%重叠补跑，结果见交付验证记录；不能称为一次完整全绿。
- 运行3分23秒时辅助进程PID33314保持不变，额度成功按180秒刷新，CPU瞬时0%、RSS172752 KiB。
- 上游品牌规则测试增加接入模块的明确豁免；其余产品区域继续保留品牌约束。

## 八、macOS 输入焦点复发修复

用户反馈后台仍打断输入。旧版后台辅助进程修复只覆盖进程启动，未覆盖 OverlayWindow 自身的窗口契约。主透明窗口原有 Tool/StrongFocus，但没有 WindowDoesNotAcceptFocus、WA_ShowWithoutActivating；macOS Cocoa 对照探针直接读取 NSWindow，旧配置 canBecomeKeyWindow=true、isKeyWindow=true，新配置均为false。Qt isActiveWindow 在新旧两者均可返回true，不能拿它代替 Cocoa 键盘窗口证据。

修改仅限 macOS OverlayWindow 构造处追加两个保护；置顶旗标重建保留保护。没有通过抢回用户原焦点来掩盖问题，没有新增后台进程或定时激活/失活操作。鼠标路由保持原样；主动打开的聊天、设置仍是独立窗口。Windows/Linux flags 不变。

TDD Route: strict；新增恢复/置顶重建回归先失败后通过。相关 OverlayWindow、逐像素穿透、CodexRuntime 共60 passed、2 skipped；ruff和diff检查通过。原生对照验证覆盖首次显示、隐藏恢复、置顶旗标重建三条路径（canBecomeKeyWindow=false、isKeyWindow=false），独立输入窗口canBecomeKeyWindow=true。修复包已签名验证并启动，PID46192。长期打字、点击宠物、跨屏和输入法组合的端到端验收仍未覆盖。此修复关闭已证实的主窗口键盘焦点路径，不宣称穷尽所有系统触发点。

最终全量：8329 passed、79 skipped、1 failed，677.26秒。唯一失败 tests/test_island_bevel_fade.py::test_sample_value_change_never_fades：有效采样34点，小于60；单独复跑失败，临时目录解出未经修改的HEAD pet/tests后同样失败，确认是本机既有基线问题；未改动该测试或降低断言。40秒前台进程观察仅记录ChatGPT，未观察到桌宠/辅助进程切前台；不能替代实际持续打字验收。

## 九、焦点再次复发：灵动岛周期置顶激活整个应用

用户确认症状是正在打字时输入突然失效。用临时诊断启动器只记录时间、前台PID/可执行路径、窗口类型、键盘窗口布尔值，不采集输入内容/窗口标题。旧逻辑30秒信息刷新触发reassert_topmost，随后的前台PID由ChatGPT40097变成桌宠53999，所有主窗、气泡、岛isKeyWindow仍为false。说明前一次修复的键盘窗口约束不足以限制应用激活，不能作为端到端成功依据。

Qt6.12.0官方源码QCocoaWindow::raise在orderFront之后调用NSApp activateIgnoringOtherApps:YES（https://github.com/qt/qtbase/blob/v6.12.0/src/plugins/platforms/cocoa/qcocoawindow.mm）。岛的macOS分支此前退回QWidget.raise_，既有30秒刷新会反复触发此应用级激活。修复边界是岛原生置顶适配：新增platform_mac._mac_order_front_without_activating，仅对已有NSWindow调用orderFrontRegardless，不调整层级、不激活应用、不抢回原应用焦点；mac原生失败时返回false，绝不回退Qt.raise_。Windows/Linux分支保留。之前的WindowDoesNotAcceptFocus保护保留，处理独立的窗口键盘焦点路径。

TDD Route: strict。新增两项心跳回归先失败后通过，覆盖原生成功和失败均不走Qt.raise_；73相关项通过、2跳过。更广岛/平台/会话回归与修复后周期观察结果在交付时补充。无新增后台线程和定时器，复用既有刷新；每次原生调用仅重排窗口。

修复后诊断实际运行三个30秒刷新周期：1792397038.242316前后PID40097；1792397068.242666前后PID2546；1792397098.2445052前后PID40097。整个对应区间未见桌宠重新成为前台，用户可以正常切换其它应用。扩大回归741 passed、3 skipped、1 failed（仍为既有bevel采样阈值问题）。新包通过完整构建门和codesign --verify --deep --strict，已停止诊断进程并启动正式outputs/dsh-pet-focus-v2版本，临时诊断启动器已删除；仅保留不含输入内容的证据日志。当前v2只跑了受影响742项回归，没有宣称重新全量通过。

## 十、余额换字测试的字体依赖误报修复

原用例只检查alpha=255的字形核心，要求至少60点。本机默认字体实际34个不透明像素、493个半透明像素；定时器、淡化系数、残影引用和已采到的像素断言都通过，失败来自取样量前提。邻近结构淡化用例已用头像几何锚规避同类字体差异，余额换字用例仍遗漏。

Decision: code-change（仅测试）。保留生产渲染不变，把该用例改为同环境同配置的完整帧参照：切换到目标值的画面必须与新建岛直接显示目标值完全一致，涵盖抗锯齿边缘、内容稀释和旧字残留；保留不启动淡化/系数为1/无残影引用断言，增加读数确实变化、窗口尺寸不变的前提。长转短、短转长两个方向覆盖。没有降低像素阈值或加入平台豁免；原来只适用于不透明像素的helper仍由其它几何锚用例使用。

验证：原用例先复现34<60失败；修改后本文件21项通过。目标两方向在QT_SCALE_FACTOR=1.25和2均通过。额外探索把本文件全部用例强制2倍缩放时有4项既有坐标采样失败，涉及物理像素与逻辑坐标混用；不属于本次余额换字测试修复，未修改或宣称整文件2倍缩放通过。当前默认环境扩大回归结果另附。生产代码、已运行的签名包均不变，无需重启或重打包。

默认环境扩大回归：743 passed、3 skipped，34.70秒；报告契约201项通过、ruff/diff检查通过。本次测试修复未重新运行整个8400余项套件，不宣称全量通过。

## 十一、推送前最终检查

### 修改规模与逐文件说明

| 文件 | 新增 | 删除 | 说明 |
| --- | ---: | ---: | --- |
| `docs/INDEX.md` | 2 | 0 | 登记接入报告入口。 |
| `docs/PR-REPORT-CODEX-NATIVE-2026-10-19.md` | 125 | 0 | 记录接入边界、原生焦点对照和测试证据。 |
| `pet/chat/providers.py` | 13 | 0 | 增加本地账号通道及连接测试。 |
| `pet/codex_rpc.py` | 159 | 0 | 复用长驻app-server与后台辅助包，提供聊天和额度RPC。 |
| `pet/codex_runtime.py` | 130 | 0 | 增量读会话、轮询额度并经Qt信号分发。 |
| `pet/codex_sessions.py` | 28 | 0 | 纯状态收敛和宠物均衡分配。 |
| `pet/dynamic_island.py` | 10 | 4 | macOS置顶改用不激活应用的原生重排。 |
| `pet/multi_window_shared.py` | 4 | 0 | 接入共享Codex服务启停生命周期。 |
| `pet/overlay_window.py` | 8 | 0 | macOS主透明窗拒绝键盘焦点及显示激活。 |
| `pet/platform_mac.py` | 28 | 0 | 实现不激活应用的原生窗口重排。 |
| `resources/codex-island-extensions/codex_5h/island-component.json` | 1 | 0 | 声明额度组件及取值格式。 |
| `resources/codex-island-extensions/codex_5h/provider.py` | 11 | 0 | 只读额度快照，过期或不可用时不返回假零。 |
| `resources/codex-island-extensions/codex_week/island-component.json` | 1 | 0 | 声明额度组件及取值格式。 |
| `resources/codex-island-extensions/codex_week/provider.py` | 11 | 0 | 只读额度快照，过期或不可用时不返回假零。 |
| `scripts/build_macos.sh` | 1 | 0 | 随包分发两个额度组件。 |
| `tests/test_codex_provider.py` | 14 | 0 | 验证聊天走长驻账号客户端。 |
| `tests/test_codex_runtime.py` | 57 | 0 | 验证单宠接全部会话和禁用时不启动。 |
| `tests/test_codex_sessions.py` | 13 | 0 | 验证会话结束和均衡分配。 |
| `tests/test_desktop_pet_features.py` | 7 | 0 | 为明确集成模块收窄原有品牌规则。 |
| `tests/test_island_bevel_fade.py` | 28 | 8 | 改为完整帧对照并覆盖长短读数双向切换。 |
| `tests/test_island_topmost.py` | 26 | 2 | 覆盖macOS置顶成功/失败均不调用Qt.raise_。 |
| `tests/test_overlay_window.py` | 18 | 0 | 覆盖显示恢复与置顶重建后的焦点约束。 |

### 校验记录

- ruff覆盖pet/与tests/通过，diff空白检查通过；22个待提交文件的凭据模式扫描无匹配，未提交本地认证、配置或构建产物。
- 18个CPU负载进程并行时，受影响时序测试族连续三轮均为107 passed、2 skipped（2.64秒、2.45秒、2.59秒）；负载进程已全部退出。
- 推送前最终全量：`QT_QPA_PLATFORM=offscreen .venv311/bin/python -m pytest -q`，8333 passed、79 skipped、20 warnings，664.65秒。当前累计分支全量通过；跳过项保留各测试原有平台/能力条件。

## 十、发布前修复：大记录阻断会话结束事件

2026-10-19 真机复现：Codex 当前两条活跃会话，旧包显示四条。两条已结束会话的日志含 14 / 12 条超过 1 MiB 的 JSONL 记录，最大记录分别为 13,414,916 / 11,082,570 字节。旧读取器 `readline(1024 * 1024)` 将大记录误判为未写完的尾行，回退后每轮重新读取相同片段，永远无法到达其后的完成事件。

修改文件说明：`pet/codex_runtime.py` 移除单条记录的 1 MiB 读取上限，保留按换行判断未完成尾行、增量 offset、根会话过滤、Qt queued signal 和多宠均分；`tests/test_codex_runtime.py` 新增正常完成、取消、部分大记录追加后的三项永久回归。此报告补充诊断及性能证据，逐文件增删行数以提交 diff 为准。

性能分析：macOS arm64 / Python 3.11，同一批七条真实会话日志，一次冷扫描耗时 0.5680 秒，紧接的无新增记录增量轮耗时 0.0003 秒；该独立诊断进程峰值 RSS 341,245,952 字节。按完整单行解析会暂存大记录，峰值随最大记录增长；未新增线程、网络、配置写入或定时全量扫描，仍为 1 Hz 增量读取。没有长期 RSS 稳态测量，不宣称总内存降低。

实机运行记录：旧读取路径在本机对应两条已结束日志处卡住，分别保留 thinking 状态；完整读取并收敛后仅剩两条活跃根会话，与 Codex 应用状态一致。合成四会话回归修改前失败（4 != 2），修改后通过；部分大记录尚无换行时仍保持原状态，追加剩余记录和完成事件后归零。最终包和全量测试结果随 Release 验证文件提供。

风险边界：本次修复大记录导致的确定性卡读；日志没有产生任何结束事件的异常退出仍可能残留忙碌，未通过固定超时冒充已完成。原有后台非激活呈现保持不变。

## 十一、逐会话结束提示

`pet/codex_runtime.py` 在已有路由快照上比较会话状态，只有原来分配给该宠物的会话明确转为 idle 才提示“1个会话已结束 · 剩余1个会话”；正常完成与取消均称“结束”，不把文件消失或分组迁移推断为结束。不另建定时器、不激活窗口、不读取聊天正文；沿用现有 4500ms 气泡。空闲后下一轮不重复通知，全结束保留“已完成”。`tests/test_codex_runtime.py` 通过 queued signal 覆盖单宠、多宠完成与分组变化、不重复弹出、最终归零。

实机修复包 PID 94787 启动后记录 `Codex session routing: slot=1 state=working sessions=2`，仍为原有 active slots=[1]、106段动画。本条证明大记录修复后的真实路由；逐会话提示的最终包运行及回归结果另随 Release 交付。当前气泡不包含会话标题，避免泄露内容；剩余数是该宠物当前分配数量。

性能补充：100会话 / 2只宠物、交替结束一个会话、10000轮共20000次呈现快照，使用真实 QObject 和无绘制 overlay seam 的 timeit 实测平均 17.69 微秒/快照；此值不包含气泡实际绘制，不据此声称绘制耗时。

## 十二、新增会话快速提示

修改文件说明：`pet/codex_runtime.py` 将会话扫描间隔从 1 秒缩至 0.5 秒，依据全局活跃 ID 集合差异提示“新增1个会话 · 当前2个会话”；每只宠物只通知实际分配给自己的新增会话，已有会话跨宠物重新分组不冒充新增。新增/结束通知沿用 4500ms 气泡，期间普通思考/工作阶段变化不覆盖；新生命周期事件、等待查看和异常可优先更新，交互审批气泡仍由原控件保护。旧轮询线程和 queued signal 继续负责全部读取/呈现，不新增服务、线程、持久化状态或配置。`tests/test_codex_runtime.py` 补充单宠/多宠新增通知、阶段覆盖防护、等待态优先、到期恢复、下一次0.5秒轮询发现新文件的永久回归。

性能分析：独立临时 CODEX_HOME，真实后台轮询线程，空初始集合后落盘 task_started，五次“落盘至读取器发出 updated 信号”分别为 0.5056、0.5022、0.5039、0.5030、0.5010 秒。该数不包含气泡绘制延时；冷启动首次扫描大日志成本仍见第十节。轮询频率从1Hz增至2Hz，原有每轮 glob/stat/open 次数不变，因此空闲文件元数据访问频率约翻倍；仍不按每轮全量解析旧内容，没有新增网络请求。

实机运行记录：旧包在新增会话时只将通用“工作中 · 1个会话”改成“工作中 · 2个会话”，本机日志对应17:24:10至17:25:21的路由记录；原路径没有新增文案，也未保护通知免受下一轮阶段更新覆盖。新增回归在旧代码下三项失败，新代码下通过。最终包启动和最终全量测试见随 Release 发布的验证记录。
