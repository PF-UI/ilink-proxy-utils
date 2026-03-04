# ilink-proxy-utils 发布说明

## 使用本 Release 前需要的配置文件

Go 代理 **必须** 在**项目根目录**（即 `proxy_manager.exe` 所在目录的**父目录**）下存在以下配置文件，否则无法启动或无法转发：

| 文件 | 说明 | 如何生成 |
|------|------|----------|
| **proxy_current.json** | 当前线路与认证（sid、username、password） | 运行 `python get_proxy_info.py [line_sn]` 或 `python get_pac.py [line_sn]` |
| **lines.json** | 线路列表（面板与切换用） | 运行 `python linelist.py` |
| **lines_proxy.json** | 各线路上游 proxy 串（转发必读） | 运行 `python get_all_lines_proxy.py` |

**运行方式**：将 `proxy_manager.exe` 放在任意目录下的子目录（例如 `proxy_manager`）中，在该子目录内运行 exe；其**父目录**即为“项目根”，上述三个 JSON 文件须放在该父目录下。

**首次使用**：请先在本仓库中按 README 使用流程执行 `login.py` → `linelist.py` → `get_proxy_info.py` 或 `get_pac.py` → `get_all_lines_proxy.py` 生成配置文件，再运行 `proxy_manager.exe`。
