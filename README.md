# iLink 代理工具

基于 iLink 扩展 API 的配套工具：邮箱登录、获取线路与代理认证，配合本地 Go 代理实现全局/分流代理。Go 代理**仅读取配置文件**（不调用 Python），上游地址从 `lines_proxy.json` 按当前线路切换。

---

## 项目结构

```
proxy/
├── login.py              # 邮箱登录，获取验证码，保存 token 到 token.txt
├── linelist.py           # 获取线路列表，保存到 lines.json
├── get_proxy_info.py     # 获取指定线路的代理账号密码，保存到 proxy_auth.json、proxy_current.json
├── get_pac.py            # 获取指定线路的 PAC 与认证，写入 proxy.pac、proxy_current.json 并更新 lines.json
├── get_all_lines_proxy.py # 拉取所有线路的 var proxy，写入 lines_proxy.json（Go 按线路切换上游必用）
├── proxy.pac             # PAC 脚本（国内直连、国外走 127.0.0.1:8888，系统代理「脚本地址」指向此文件）
├── test.py               # API 模块（get_server、get_pac 等）
├── proxy_manager/        # Go 代理管理器
│   ├── main.go           # 本地 HTTP 代理 + Web 面板 + 线路切换，仅读配置不调 Python
│   └── go.mod
├── token.txt             # 登录后生成的 token（需先运行 login.py）
├── proxy_current.json    # 当前线路与认证（username/password、sid），Go 与脚本共用
├── proxy_auth.json       # 代理认证缓存（get_proxy_info.py / get_pac.py 写入）
├── lines.json            # 线路列表（linelist.py 生成），面板展示与一键切换用
└── lines_proxy.json      # 各线路的 var proxy 串（get_all_lines_proxy.py 生成），Go 上游唯一来源
```

---

## Go 配置文件存放路径

Go 代理从**项目根目录**（即 `proxy_manager` 的**父目录**）读取配置，且**必须在 `proxy_manager` 目录下启动**（`cd proxy_manager` 再执行 `go run main.go`），否则会找错目录。

| 配置文件           | 说明 |
|--------------------|------|
| `proxy_current.json` | 当前线路与认证（sid、username、password） |
| `lines.json`         | 线路列表，面板展示与一键切换用 |
| `lines_proxy.json`   | 各线路上游 proxy 串，Go 转发必读 |

**路径示例**（与 `proxy_manager` 文件夹同级）：

- Windows：`D:\proxy\proxy\proxy_current.json`、`D:\proxy\proxy\lines.json`、`D:\proxy\proxy\lines_proxy.json`
- 即项目根目录 = 运行时的当前工作目录的父目录（在 `proxy_manager` 下运行时，父目录即为项目根）。

---

## 依赖

| 环境   | 说明                    |
|--------|-------------------------|
| Python 3.x | 运行登录、线路、认证等脚本 |
| Go 1.x     | 仅 `proxy_manager` 需要   |
| 第三方库   | `pip install requests`   |

---

## 使用流程

### 1. 登录获取 Token

```bash
python login.py
```

按提示输入邮箱和验证码，token 会保存到 `token.txt`。**后续步骤都依赖该 token。**

### 2. 获取线路列表

```bash
python linelist.py
```

线路列表保存到 `lines.json`，控制台按地区分组展示。记下要使用的 `line_sn`（如 `sg-bgp`）。

### 3. 获取代理认证与 PAC（二选一或组合使用）

**方式 A：只更新当前线路认证（不更新 PAC 文件）**

```bash
python get_proxy_info.py [line_sn]
```

- 不传参数时默认 `sg-bgp`。认证写入 `proxy_auth.json`、`proxy_current.json`。

**方式 B：获取指定线路的 PAC 并设为当前线路**

```bash
python get_pac.py [line_sn]
```

- 拉取该线路 PAC 写入 `proxy.pac`，认证写入 `proxy_current.json`、`proxy_auth.json`，并更新 `lines.json` 中该线路的账号密码（便于面板一键切换）。

### 4. 生成所有线路的上游配置（必做，否则 Go 无法转发）

```bash
python get_all_lines_proxy.py
```

- 按 `lines.json` 逐条请求 PAC，提取 `var proxy = "HTTPS ...; ..."` 写入 `lines_proxy.json`。
- **Go 仅从 `lines_proxy.json` 读取上游**，无此文件或当前线路不在其中时，代理会报未配置上游。面板切换线路时也会按 `lines_proxy.json` 自动换上游。

建议：首次使用或线路列表/接口有更新后执行一次。

### 5. 启动 Go 代理

```bash
cd proxy_manager
go run main.go
```

或运行已编译的 `proxy_manager.exe`。

| 服务           | 地址                                             |
|----------------|--------------------------------------------------|
| HTTP 代理      | `http://localhost:8888`                          |
| Web 控制面板   | `http://localhost:8889`                          |
| 切换线路 API   | `http://localhost:8888/api/switch?sid=<line_sn>` |
| 重载配置 API   | `http://localhost:8888/api/reload`               |

控制面板从 `lines.json` 读取线路列表，点击线路即可一键切换（认证与上游均随 `lines_proxy.json` 更新）。

### 6. 配置系统代理（二选一）

#### 方式 A：手动代理（全部流量走代理）

1. 打开 **Windows 设置 → 网络和 Internet → 代理**。
2. 开启「使用代理服务器」，地址填 `127.0.0.1`，端口填 `8888`。
3. 系统流量经本地代理转发至 iLink 上游。

#### 方式 B：PAC 脚本（按域名分流，推荐）

1. 打开 **Windows 设置 → 网络和 Internet → 代理**。
2. 选择「使用设置脚本」，脚本地址填本机 PAC 路径，例如：  
   `file:///D:/proxy/proxy/proxy.pac`（按实际路径修改）。
3. 项目内 `proxy.pac` 已配置为：国内域名直连，国外域名走 `127.0.0.1:8888`，由 Go 代理认证并转发。

**关闭代理**：在系统代理设置中关闭「使用代理服务器」或清除 PAC 脚本，并停止 `proxy_manager` 进程。

---

## 注意事项

- **执行顺序**：先运行 `login.py` 拿到 token，再执行 `linelist.py`；之后按需运行 `get_proxy_info.py` 或 `get_pac.py`。**使用 Go 代理前务必至少执行一次 `get_all_lines_proxy.py`**，生成 `lines_proxy.json`。
- **工作目录**：必须在 `proxy_manager` 目录下运行 Go（`cd proxy_manager`），程序会从父目录读取 `proxy_current.json`、`lines.json`、`lines_proxy.json` 等。
- **上游地址**：Go 仅从 `lines_proxy.json` 按当前线路（`proxy_current.json` 中的 `sid`）读取上游，不读 `proxy.pac`。线路或网关变更后请重新执行 `get_all_lines_proxy.py` 更新 `lines_proxy.json`。
