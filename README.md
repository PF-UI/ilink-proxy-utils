# iLink 代理转本地

将 iLink 代理服务转为本地 HTTP/HTTPS 代理，支持一键启动、Web 面板切换线路、Windows/macOS/Linux 全平台。

## 架构

```
用户浏览器/系统
    │  系统代理 → 127.0.0.1:8888
    ▼
本地 Go 代理 (proxy_manager)
    │  TLS 连接上游 HTTPS 代理
    │  Proxy-Authorization: Basic 认证
    ▼
iLink 上游代理 (cmb-gate.gamecaches.com:25670)
    │
    ▼
目标网站 (Google / GitHub / YouTube 等)
```

- **Python 脚本**：登录获取 token → 拉取线路列表 → 获取代理认证信息
- **Go 代理**：读取配置作为本地 HTTP/HTTPS 代理，通过 TLS 隧道转发到 iLink 上游
- **Web 面板**：`http://localhost:8889` 可视化切换线路

---

## 项目结构

```
ilink-proxy-utils/
├── main.py                  # 统一入口脚本 (setup / login / lines / proxy / start / stop / test)
├── config.py                # 统一配置模块，从 .env 读取凭据
├── login.py                 # 邮箱登录，获取 token（支持自动模式）
├── linelist.py              # 获取线路列表 → lines.json
├── get_proxy_info.py        # 获取指定线路代理认证信息 → proxy_current.json
├── test.py                  # API 底层模块 (get_server / get_pac / send_code / login_email)
├── proxy.pac                # PAC 脚本（国内直连，国外走 127.0.0.1:8888）
├── proxy_current.json       # 当前线路、认证、上游地址（Go 代理读取）
├── proxy_auth.json          # 代理认证缓存
├── lines.json               # 线路列表缓存
├── token.txt                # API 认证 token
├── .env                     # 登录凭据 (user_name / user_password)
│
├── proxy_manager/           # Go 代理管理器
│   ├── main.go              # HTTP/HTTPS 代理 + TLS 上游 + Web 面板 + 线路切换
│   └── go.mod
│
├── start.vbs                # Windows 双击静默启动（无窗口）
├── start.bat                # Windows 双击启动（带命令行窗口）
├── start.ps1                # Windows PowerShell 启动
├── start.sh                 # Linux/macOS 启动
├── stop.bat                 # Windows 停止代理
└── stop.sh                  # Linux/macOS 停止代理
```

---

## 依赖

| 环境 | 说明 |
|------|------|
| Python 3.8+ | 运行登录、线路、认证脚本 |
| Go 1.21+ | 仅 `proxy_manager` 需要（使用预编译 exe 可跳过） |
| requests | `pip install requests` |

---

## 快速开始

### 方式一：一键启动

```bash
# Windows — 直接双击以下文件:
start.bat          # 带命令行窗口
start.vbs          # 静默后台启动（无窗口）

# Linux / macOS:
chmod +x start.sh && ./start.sh
```

首次运行会自动初始化并启动代理。

### 方式二：使用统一入口

```bash
# 完整初始化
python main.py setup

# 启动代理
python main.py start

# 或一键完成
python main.py all
```

---

## 命令行参考

### 统一入口 `python main.py`

| 命令 | 说明 |
|------|------|
| `python main.py setup` | 完整初始化：登录 → 获取线路 → 获取代理信息 |
| `python main.py login` | 仅登录获取 token |
| `python main.py lines` | 获取线路列表 |
| `python main.py proxy [sid]` | 获取指定线路代理认证（默认 sg-bgp） |
| `python main.py start` | 启动 Go 代理服务器 |
| `python main.py start --compiled` | 使用预编译 exe 启动（无需 Go 环境） |
| `python main.py stop` | 停止所有代理进程 |
| `python main.py test` | 测试代理是否正常工作 |
| `python main.py all` | setup + start 一键完成 |

### 分步脚本

```bash
# 1. 登录
python login.py              # 交互式
python login.py --auto       # 从 .env 自动读取邮箱

# 2. 获取线路列表
python linelist.py
python linelist.py --auto    # token 过期时自动重登

# 3. 获取代理认证
python get_proxy_info.py          # 默认 sg-bgp
python get_proxy_info.py hk-bgp1  # 指定线路
```

---

## 启动代理

启动后可用服务：

| 服务 | 地址 |
|------|------|
| HTTP/HTTPS 代理 | `127.0.0.1:8888` |
| Web 控制面板 | `http://127.0.0.1:8889` |
| 健康检查 | `http://127.0.0.1:8888/api/health` |
| 切换线路 | `http://127.0.0.1:8888/api/switch?sid=line_sn` |
| 线路列表 | `http://127.0.0.1:8888/api/lines` |
| 当前线路 | `http://127.0.0.1:8888/api/current` |

### 编译为可执行文件（可选）

```bash
cd proxy_manager
go build -o proxy_manager.exe .
```

之后使用 `python main.py start --compiled` 即可跳过 Go 环境依赖。

---

## 配置系统代理

### 方式 A：手动代理（全部流量走代理）

1. **Windows**：设置 → 网络和 Internet → 代理 → 手动设置代理
2. 地址：`127.0.0.1`，端口：`8888`

### 方式 B：PAC 脚本（按域名分流，推荐）

1. **Windows**：设置 → 网络和 Internet → 代理 → 使用设置脚本
2. 脚本地址：`file:///E:/ilink_proxy/proxy.pac`（按实际路径修改）
3. PAC 规则：国内域名直连，国外域名走 `127.0.0.1:8888`

---

## 可用线路

| 地区 | 线路 SID | 说明 |
|------|----------|------|
| 香港 | `hk-bgp1`, `hk-idc2`, `hk-tidc`, `hk-tidc2` | 机房专线，高速稳定 |
| 香港 | `gk-idc1`, `gk-us-idc1`, `tw-hinet3` | 德国/美国/台湾专线 |
| 美国 | `us-user1`, `H-IR7838` | 家宽/CN2 |
| 亚洲 | `sg-bgp`, `kr1`, `jp-idcx`, `jp2`, `tw-hinet2` | 新加坡/韩国/日本/台湾 |

完整列表运行 `python linelist.py` 查看。

---

## 配置说明

`.env` 文件存储登录凭据（不上传到 git）：

```
user_name=your_email@example.com
user_password=your_password
```

`proxy_current.json` 由脚本自动生成，Go 代理读取此文件：

```json
{
  "username": "your_email",
  "password": "your_password",
  "sid": "sg-bgp",
  "upstream_host": "cmb-gate.gamecaches.com",
  "upstream_port": "25670"
}
```

---

## 注意事项

- **工作目录**：Go 代理必须在 `proxy_manager` 目录下运行，程序自动以父目录为项目根路径
- **端口冲突**：启动时自动检测并清理旧进程，无需手动处理
- **上游变更**：线路切换后运行 `python main.py proxy <sid>` 更新代理配置
- **凭据安全**：`.env`、`token.txt`、`proxy_current.json` 含敏感信息，建议加入 `.gitignore`

---

## 发布（维护者）

```bash
cd proxy_manager && go build -o proxy_manager.exe .
git tag v2.0.0 && git push origin v2.0.0
# 在 GitHub Releases 上传 proxy_manager.exe
```
