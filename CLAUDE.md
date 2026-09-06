# CLAUDE.md — bifrost-platform-plugin

与本项目用户对话一律使用中文回复；UI 字符串与代码标识符使用 English。

## 工作区定位（2026-09-06）

| 项 | 值 |
|---|---|
| 域 / 载荷 | Ops · **IB Gateway Plugin** —— 全系统**唯一**连接 TWS 的组件（IB API socket，client_ids 70/71 Host、72/73 Secondary）→ `redis-ib` @ `data` NS |
| IB 接入模型 | IB 登录只发生在两台 Win11 的 TWS 软件里（Owner 手工登录 + 2FA），工作区与集群里没有 IB 密码；账户号 `U17123565` / `U8829175` 是标识符不是秘密 |
| D10 | operator 命令流只有 Daemon 可写；Plugin 不下单、不武装实盘 |
| 仓库可见性 | GitHub **PUBLIC**（12 个 repo 全部公开）—— `.env`、Secret YAML、dump、kubeconfig、账户内容永不入库 |
| 硬边界 | D10 交易执行冻结（BLOCKED）· D13 三域边界 · 平台/业务解耦（Flywheel A/B） |
| 事实基线 | `../AGENT_FACTS.md`（§8c 运行时与安全事实）· 规则 `../CLAUDE.md`（§8 Claude Code 运行配置） |

会话请在工作区根 `/stocks` 启动（加载治理层 hooks / auto mode / 共享记忆）；运行时与安全事实以 `../AGENT_FACTS.md` §8c 为准。

## 职责

**`bifrost-plugin`** — Bifrost Ops Platform 的 **Plugin 仓库**。承载非通用系统运维能力（与 `bifrost-platform` 核心控制面分离）。

| Plugin | 目录 | 说明 |
|--------|------|------|
| IB Gateway | `src/bifrost_plugin/ib_gateway/` | Platform 级 TWS 连接总线 — 共享行情/账户/Operator RPC → `redis-ib` |
| (future) | `src/bifrost_plugin/<name>/` | 其他 domain-specific Ops 扩展 |

## 架构边界

- **Platform core** (`bifrost-platform`): 通用环境治理 — matrix、spine、Console shell
- **Plugins** (本 repo): 领域插件 — 独立进程、独立 K8s 清单、通过 Redis/API 与 Platform 解耦
- **Trade** (`bifrost-trade-*`): 消费 Plugin 输出的共享数据总线，不直连 TWS

## IB Gateway Plugin

- 部署 NS: `data`（与 CNPG / redis-live 同级基础设施）
- 共享 Redis: `redis-ib.data.svc.cluster.local`
- 每 IB 账户 1 Pod（Deployment replica=1），1 active client + 备用 cid failover
- Console 治理: Architecture → Plugins → IB Gateway

## K8s 清单

```
k8s/
├── redis-ib/           # 共享 IB 数据 Redis @ data NS
├── ib-gateway/         # Gateway Deployment (Host + Secondary slots)
└── external-names/     # Trade NS → redis-ib ExternalName
```

## 命令

```bash
make install-dev
make install-redis-ib      # apply redis-ib + secret from .env
make apply-external-names  # ExternalName in bifrost-{dev,stg,prod}
make sync-redis-ib-secrets # plugin .env → Trade overlays + platform .env
make verify-ib-gateway-program
make test
```

## 修改纪律

- Plugin 公开 Redis key 契约变更需同步更新 Trade 消费者 + Console catalog
- 新 Plugin 需在 Console `pluginCatalog` / 独立 catalog 注册
- 不 import `bifrost-trade-*` Python 包 — 仅共享 Redis 契约
