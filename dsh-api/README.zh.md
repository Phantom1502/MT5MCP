# dsh-api — DeepSeek Harness 的 HTTP 控制面插件

中文 | [English](./README.md)

`dsh-api` 是 [DeepSeek Harness（dsh）][dsh] 的官方插件，把 dsh 自身的内部能力
以 HTTP 路由的形式挂到 dsh 已经在监听的本机 loopback socket 上。同一台机器上
的任何进程 —— 桌面壳、浏览器扩展、CLI、编辑器集成 —— 都能通过这一个统一入口
驱动 dsh，不必去理解 dsh 的进程模型或直接接触它的 in-process service。

- 路由前缀（默认）：**`/dsh-api`**
- 只在 dsh 已经绑定的地址监听（127.0.0.1）
- 除 Node.js 本身外零运行时依赖

[dsh]: https://www.npmjs.com/package/@deepseek-ai/dsh

## 安装

```sh
# 从 GitHub（任何 dsh profile）：
dsh plugin --profile web add github:lilming123/dsh-api

# 从 npm（发布之后）：
dsh plugin --profile web add dsh-api
```

`dsh plugin` 就是一个 pnpm 包装。两种形式都会把包装到
`$DSH_HOME/profiles/<profile>/node_modules/`，并在 profile 的 bundle 列表里
注册 `dsh-api`——下次 `dsh web` 自动加载，不需要 `--patch`。

桌面壳 [`dsh-desktop`][dsh-desktop] 会自动检测 profile 里是否已经装了
`dsh-api`：装了就直接复用，没装则走它自带的兜底副本。**只有当你想直接对
dsh 使用本插件时，才需要手动安装它。**

[dsh-desktop]: https://github.com/lilming123/dsh-desktop

## 接口

在 `/dsh-api` 前缀下分两层：

### 1. 原生（插件加载即可用）

| 方法 | 路径                          | 用途                                                    |
| ---- | ----------------------------- | ------------------------------------------------------- |
| GET  | `/dsh-api/health`             | 活性 + 基本身份（dsh 端口、cwd、是否有 companion）      |
| GET  | `/dsh-api/language`           | 读 `locale.preference`                                  |
| POST | `/dsh-api/language`           | 写 `locale.preference`（`{ "language": "zh"\|"en" }`）  |
| GET  | `/dsh-api/workspace/list`     | 列出 `workspaceRegistry` 里的所有工作区                 |
| GET  | `/dsh-api/workspace/current`  | 当前 cwd + companion 快照（若已注册）                   |
| POST | `/dsh-api/workspace/create`   | `{ path, title? }`——新建工作区注册项                   |
| GET  | `/dsh-api/events`             | Server-Sent Events 长连接（见下文）                     |

### 2. Companion 桥接（需要注册 companion 进程）

「Companion」指本机上写了 `$DSH_HOME/dsh-api-companion.json`
（含 `{ port, token, pid, ... }`）并实现 `/companion/*` 协议的任意进程。
以下路由在无 companion 时返回 `503`，但上述原生路由始终可用。

| 方法 | 路径                          | 用途                                     |
| ---- | ----------------------------- | ---------------------------------------- |
| GET  | `/dsh-api/companion/state`    | Companion 状态快照                       |
| POST | `/dsh-api/workspace/open`     | 切换 dsh cwd（在 companion 侧重启 dsh）  |
| POST | `/dsh-api/input/paste`        | `{ text }` —— 注入文本到 dsh UI 的输入框 |
| POST | `/dsh-api/window/show`        | 聚焦 host 窗口                           |
| POST | `/dsh-api/window/reload`      | 重载 host 窗口                           |
| POST | `/dsh-api/app/quit`           | 退出 host 应用                           |

### `/dsh-api/events`（SSE）

长连接 HTTP GET，产生带 event name 的 SSE 帧：

```
event: ready
data: {"timestamp":1730000000000}

event: agent-idle
data: {"sessionId":"…","title":"…","previousStatus":"running","timestamp":…}

event: approval-needed
data: {"sessionId":"…","kind":"…","summary":"…","timestamp":…}

event: heartbeat
data: {"timestamp":…}
```

- `agent-idle`：任何 `agent/status` 从 `running → idle` 时触发。
- `approval-needed`：对 dsh `approval/request` waterfall 的**只读旁路**——
  插件观察请求、广播摘要，然后原封不动把控制权交回真正的答题链。
- `heartbeat`：每 25 秒一次，防止中间层 idle 掐流。
- dsh 退出前，订阅方会收到一条 `server-stopping` 事件，随后 socket 关闭。

## 安全性

- dsh 仅绑定 `127.0.0.1`，本插件复用这个 socket。
- 变更类请求校验 `Origin`：允许无 `Origin`（CLI）与 loopback origin，其他一律
  `403`。
- Companion 桥接路由会在请求头里带上 discovery 文件里的 token
  （`x-dsh-api-companion-token`），companion 侧应拒绝不匹配的请求。

## 配置

插件暴露两个可调参数，都写在 loader 项的 `config: { ... }` 里：

| 键              | 默认值                              | 用途                                    |
| --------------- | ----------------------------------- | --------------------------------------- |
| `basePath`      | `/dsh-api`                          | HTTP 路由前缀                           |
| `companionFile` | `$DSH_HOME/dsh-api-companion.json`  | 按需读取的 companion discovery 文件     |

示例（`$DSH_HOME/profiles/web/cordis.patch.yml`）：

```yaml
- id: dsh-api
  config:
    basePath: /control
```

## 开发

`dsh-api` 是纯 ESM 插件，无构建步骤。克隆仓库，软链到某个 dsh profile，然后
`--patch` 起 dsh：

```sh
git clone https://github.com/lilming123/dsh-api.git
cd dsh-api

# 一次性：以可实时编辑的形式挂到 profile 里
mkdir -p "$DSH_HOME/profiles/web/dsh-api-dev"
ln -sf "$PWD/index.mjs" "$DSH_HOME/profiles/web/dsh-api-dev/index.mjs"
cat > /tmp/dsh-api-dev.patch.yml <<'YML'
- insert:
    - id: dsh-api-dev
      name: ./dsh-api-dev/index.mjs
YML

dsh web --patch /tmp/dsh-api-dev.patch.yml --port 3181

# 另开一个 shell：
curl http://127.0.0.1:3181/dsh-api/health
curl -N http://127.0.0.1:3181/dsh-api/events
```

## License

MIT © 2026 lilming123
