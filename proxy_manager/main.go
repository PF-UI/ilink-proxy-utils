// iLink 代理管理器：仅读取配置文件（proxy_current.json、lines.json），不调用 Python 或任何外部程序。
// 提供本地 HTTP 代理、一键切换线路与配置重载。需在 proxy_manager 目录下运行，ProjectRoot 为父目录。
package main

import (
	"bufio"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// ProxyAuth 代理认证信息，从 proxy_current.json 读取（支持 username/password 或 p_user/p_pass）
type ProxyAuth struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Sid      string `json:"sid"`
}

// proxyCurrentFile 文件格式：兼容 username/password 与 p_user/p_pass
type proxyCurrentFile struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Sid      string `json:"sid"`
	PUser    string `json:"p_user"`
	PPass    string `json:"p_pass"`
}

// GlobalConfig 全局配置
type GlobalConfig struct {
	ProxyPort        int               // 本地监听端口
	PanelPort        int               // Web 控制面板端口
	ProjectRoot      string            // 项目根目录（含 proxy_current.json、lines.json、lines_proxy.json）
	Auth             ProxyAuth
	UpstreamProxyURL *url.URL          // 当前使用的上游代理
	LinesProxy       map[string]string // sid -> var proxy 整串，来自 lines_proxy.json，用于按线路切换上游
	mu               sync.RWMutex
}

var config = &GlobalConfig{
	ProxyPort: 8888,
	PanelPort: 8889,
}

// loadProxyAuth 从 proxy_current.json 加载 p_user/p_pass（即代理认证），支持字段名 username/password 或 p_user/p_pass
func (c *GlobalConfig) loadProxyAuth() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	authFile := filepath.Join(c.ProjectRoot, "proxy_current.json")
	data, err := os.ReadFile(authFile)
	if err != nil {
		return fmt.Errorf("read proxy_current.json: %v", err)
	}

	var raw proxyCurrentFile
	if err := json.Unmarshal(data, &raw); err != nil {
		return fmt.Errorf("parse proxy_current.json: %v", err)
	}

	c.Auth.Sid = raw.Sid
	if raw.Username != "" {
		c.Auth.Username = raw.Username
	} else {
		c.Auth.Username = raw.PUser
	}
	if raw.Password != "" {
		c.Auth.Password = raw.Password
	} else {
		c.Auth.Password = raw.PPass
	}
	return nil
}

// parseProxyString 从 "HTTPS host:port; ..." 或 "PROXY host:port; ..." 解析出第一个有效地址为 *url.URL
func parseProxyString(proxyStr string) *url.URL {
	proxyStr = strings.TrimSpace(proxyStr)
	for _, part := range strings.Split(proxyStr, ";") {
		part = strings.TrimSpace(part)
		if part == "" || strings.EqualFold(part, "DIRECT") {
			continue
		}
		var scheme, hostPort string
		if strings.HasPrefix(strings.ToUpper(part), "HTTPS ") {
			scheme = "https"
			hostPort = strings.TrimSpace(part[6:])
		} else if strings.HasPrefix(strings.ToUpper(part), "PROXY ") {
			scheme = "http"
			hostPort = strings.TrimSpace(part[6:])
		} else {
			continue
		}
		if hostPort == "" {
			continue
		}
		u, err := url.Parse(scheme + "://" + hostPort)
		if err != nil {
			continue
		}
		return u
	}
	return nil
}

// loadLinesProxy 从 lines_proxy.json 加载 sid -> proxy 字符串，供切换线路时选用上游
func (c *GlobalConfig) loadLinesProxy() {
	c.mu.Lock()
	defer c.mu.Unlock()

	path := filepath.Join(c.ProjectRoot, "lines_proxy.json")
	data, err := os.ReadFile(path)
	if err != nil {
		c.LinesProxy = nil
		return
	}
	var m map[string]string
	if err := json.Unmarshal(data, &m); err != nil {
		c.LinesProxy = nil
		return
	}
	c.LinesProxy = m
}

// applyUpstreamForSid 根据当前 sid 从 lines_proxy.json 取该线路的 proxy 串并解析为上游地址；切换线路时调用以同步切换上游
func (c *GlobalConfig) applyUpstreamForSid(sid string) error {
	c.mu.Lock()
	var proxyStr string
	var hasLine bool
	if c.LinesProxy != nil {
		proxyStr, hasLine = c.LinesProxy[sid]
	}
	c.mu.Unlock()

	if !hasLine || proxyStr == "" {
		c.mu.Lock()
		c.UpstreamProxyURL = nil
		c.mu.Unlock()
		return fmt.Errorf("lines_proxy.json 中无线路 %s 的代理配置", sid)
	}
	u := parseProxyString(proxyStr)
	if u == nil {
		c.mu.Lock()
		c.UpstreamProxyURL = nil
		c.mu.Unlock()
		return fmt.Errorf("线路 %s 的 proxy 串解析失败", sid)
	}
	c.mu.Lock()
	c.UpstreamProxyURL = u
	c.mu.Unlock()
	log.Printf("已从 lines_proxy.json 加载线路 %s 的上游: %s", sid, u.String())
	return nil
}

func cors(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
}

// apiLines 返回 lines.json 内容（线路列表）
func apiLines(w http.ResponseWriter, r *http.Request) {
	cors(w, r)
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	data, err := os.ReadFile(filepath.Join(config.ProjectRoot, "lines.json"))
	if err != nil {
		http.Error(w, "lines.json 未找到，请先在项目目录生成该文件", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Write(data)
}

// apiCurrent 返回当前代理线路信息
func apiCurrent(w http.ResponseWriter, r *http.Request) {
	cors(w, r)
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	config.mu.RLock()
	auth := config.Auth
	config.mu.RUnlock()
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(auth)
}

// lineItem 与 lines.json 中单条一致，含可选认证字段（username/password 写入后即可一键切换）
type lineItem struct {
	LineSN   string `json:"line_sn"`
	Name     string `json:"name"`
	Username string `json:"username"`
	Password string `json:"password"`
	PUser    string `json:"p_user"`
	PPass    string `json:"p_pass"`
}

// apiSwitch 从 lines.json 读取指定线路的认证，写入 proxy_current.json 并更新内存，实现一键切换
func apiSwitch(w http.ResponseWriter, r *http.Request) {
	cors(w, r)
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	sid := r.URL.Query().Get("sid")
	if sid == "" {
		http.Error(w, "sid is required", http.StatusBadRequest)
		return
	}

	linesPath := filepath.Join(config.ProjectRoot, "lines.json")
	data, err := os.ReadFile(linesPath)
	if err != nil {
		http.Error(w, "lines.json 未找到，请先在项目目录生成该文件", http.StatusNotFound)
		return
	}

	var lines []lineItem
	if err := json.Unmarshal(data, &lines); err != nil {
		http.Error(w, "lines.json 格式错误", http.StatusInternalServerError)
		return
	}

	var user, pass string
	lineExists := false
	for i := range lines {
		if lines[i].LineSN != sid {
			continue
		}
		lineExists = true
		if lines[i].Username != "" {
			user = lines[i].Username
		} else {
			user = lines[i].PUser
		}
		if lines[i].Password != "" {
			pass = lines[i].Password
		} else {
			pass = lines[i].PPass
		}
		break
	}

	if !lineExists {
		http.Error(w, "线路 "+sid+" 不在 lines.json 中", http.StatusBadRequest)
		return
	}
	// 若该线路在 lines.json 中无认证，则用当前 proxy_current.json 的账号密码，仅切换 sid
	if user == "" || pass == "" {
		config.mu.RLock()
		user = config.Auth.Username
		pass = config.Auth.Password
		config.mu.RUnlock()
		if user == "" || pass == "" {
			http.Error(w, "当前无认证信息且该线路也无认证，请先在项目目录生成 proxy_current.json", http.StatusBadRequest)
			return
		}
		log.Printf("线路 %s 无单独认证，使用当前账号仅切换 sid", sid)
	}

	config.mu.Lock()
	config.Auth.Username = user
	config.Auth.Password = pass
	config.Auth.Sid = sid
	config.mu.Unlock()

	currentPath := filepath.Join(config.ProjectRoot, "proxy_current.json")
	payload := map[string]string{"username": user, "password": pass, "sid": sid}
	out, _ := json.MarshalIndent(payload, "", "  ")
	if err := os.WriteFile(currentPath, out, 0644); err != nil {
		http.Error(w, "写入 proxy_current.json 失败: "+err.Error(), http.StatusInternalServerError)
		return
	}

	config.loadLinesProxy()
	_ = config.applyUpstreamForSid(sid)
	log.Printf("已切换线路: %s", sid)
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(map[string]string{"sid": sid, "msg": "ok"})
}

// servePanel 返回 Web 控制面板 HTML
func servePanel(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write([]byte(panelHTML))
}

const panelHTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>iLink 线路切换</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: "Segoe UI", system-ui, sans-serif; margin: 0; padding: 24px; background: #0f0f1a; color: #e4e4e7; min-height: 100vh; }
    h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 20px 0; letter-spacing: 0.02em; }
    .current { background: #1e1e2e; padding: 14px 18px; border-radius: 10px; margin-bottom: 20px; font-size: 0.95rem; display: flex; align-items: center; flex-wrap: wrap; gap: 12px; border: 1px solid #2a2a3e; }
    .current .label { color: #a1a1aa; }
    #reloadBtn { margin-left: 0; }
    .lines { display: flex; flex-wrap: wrap; gap: 10px; }
    .btn { padding: 10px 18px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9rem;
           background: #27272a; color: #e4e4e7; transition: background 0.15s, transform 0.05s; border: 1px solid #3f3f46; }
    .btn:hover { background: #3f3f46; }
    .btn.active { background: #7c3aed; border-color: #7c3aed; color: #fff; }
    .msg { margin-top: 16px; padding: 12px 16px; border-radius: 8px; font-size: 0.9rem; line-height: 1.5; border: 1px solid transparent; }
    .msg.hint { background: #1e1e2e; color: #a1a1aa; border-color: #2a2a3e; }
    .msg.hint .cmd { display: block; margin-top: 8px; padding: 10px 14px; background: #0f0f1a; border-radius: 6px; font-family: "Consolas", "Monaco", monospace; font-size: 0.85rem; color: #a5f3fc; word-break: break-all; }
    .msg.ok { background: #14532d; color: #86efac; border-color: #166534; }
    .msg.err { background: #450a0a; color: #fca5a5; border-color: #7f1d1d; }
  </style>
</head>
<body>
  <h1>iLink 代理</h1>
  <div class="current"><span class="label">当前线路:</span> <span id="current">加载中...</span> <button class="btn" id="reloadBtn">重新加载配置</button></div>
  <div class="lines" id="lines">加载中...</div>
  <div id="msg"></div>
  <script>
    const API = 'http://localhost:8888';
    async function loadCurrent() {
      try {
        const r = await fetch(API + '/api/current');
        const d = await r.json();
        document.getElementById('current').textContent = d.sid ? (d.sid + ' (' + d.username + ')') : '未设置';
      } catch (e) {
        document.getElementById('current').textContent = '获取失败';
      }
    }
    document.getElementById('reloadBtn').onclick = async () => {
      const msgEl = document.getElementById('msg');
      msgEl.textContent = '重新加载中...';
      msgEl.className = 'msg';
      try {
        const r = await fetch(API + '/api/reload');
        const text = await r.text();
        if (r.ok) {
          msgEl.textContent = '已重新加载配置';
          msgEl.className = 'msg ok';
          loadCurrent();
          loadLines();
        } else {
          msgEl.textContent = text || '加载失败';
          msgEl.className = 'msg err';
        }
      } catch (e) {
        msgEl.textContent = '请求失败: ' + e.message;
        msgEl.className = 'msg err';
      }
    };
    async function loadLines() {
      const el = document.getElementById('lines');
      try {
        const r = await fetch(API + '/api/lines');
        const lines = await r.json();
        if (!Array.isArray(lines) || lines.length === 0) {
          el.innerHTML = '<span>无线路数据，请先在项目目录生成 lines.json</span>';
          return;
        }
        const cur = await (await fetch(API + '/api/current')).json();
        el.innerHTML = lines.map(l => {
          const sid = l.line_sn || '';
          const name = (l.name || sid) + (l.connect ? '' : ' [已满]');
          const active = sid === cur.sid ? ' active' : '';
          return '<button class="btn' + active + '" data-sid="' + sid + '">' + name + '</button>';
        }).join('');
        el.querySelectorAll('.btn').forEach(b => {
          b.onclick = async () => {
            const sid = b.dataset.sid;
            const msgEl = document.getElementById('msg');
            msgEl.textContent = '切换中...';
            msgEl.className = 'msg';
            try {
              const r = await fetch(API + '/api/switch?sid=' + encodeURIComponent(sid));
              const text = await r.text();
              if (r.ok) {
                msgEl.textContent = '已切换到 ' + sid;
                msgEl.className = 'msg ok';
                loadCurrent();
                el.querySelectorAll('.btn').forEach(x => x.classList.remove('active'));
                b.classList.add('active');
              } else {
                msgEl.textContent = text || '切换失败';
                msgEl.className = 'msg err';
              }
            } catch (e) {
              msgEl.textContent = '请求失败: ' + e.message;
              msgEl.className = 'msg err';
            }
          };
        });
      } catch (e) {
        el.innerHTML = '<span>加载失败，请确保 lines.json 存在且代理已启动</span>';
      }
    }
    loadCurrent();
    loadLines();
  </script>
</body>
</html>`

// basicAuthEncode 生成 Proxy-Authorization 的 Basic 认证头
func basicAuthEncode(user, password string) string {
	return base64.StdEncoding.EncodeToString([]byte(user + ":" + password))
}

// handleConnect 参考“可成功代理”的实现：原始 TCP+TLS 连上游，手动发 CONNECT+Basic 认证，再双向转发
func handleConnect(w http.ResponseWriter, r *http.Request, proxyURL *url.URL, auth ProxyAuth) {
	target := r.Host
	if target == "" {
		target = r.URL.Host
	}
	if target == "" && r.URL.Path != "" {
		target = r.URL.Path
	}
	if target == "" {
		http.Error(w, "CONNECT without target", http.StatusBadRequest)
		return
	}

	hijacker, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "hijack not supported", http.StatusInternalServerError)
		return
	}
	clientConn, _, err := hijacker.Hijack()
	if err != nil {
		log.Printf("[CONNECT] Hijack: %v", err)
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer clientConn.Close()

	upstreamAddr := proxyURL.Host
	if proxyURL.Port() == "" {
		if proxyURL.Scheme == "https" {
			upstreamAddr = net.JoinHostPort(proxyURL.Hostname(), "443")
		} else {
			upstreamAddr = net.JoinHostPort(proxyURL.Hostname(), "80")
		}
	}
	tcpUpstream, err := net.DialTimeout("tcp", upstreamAddr, 15*time.Second)
	if err != nil {
		log.Printf("[CONNECT] 连上游失败 %s: %v", upstreamAddr, err)
		clientConn.Write([]byte("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\n" + err.Error()))
		return
	}
	defer tcpUpstream.Close()

	var upstream net.Conn = tcpUpstream
	if proxyURL.Scheme == "https" {
		tlsUpstream := tls.Client(tcpUpstream, &tls.Config{
			ServerName:         proxyURL.Hostname(),
			InsecureSkipVerify: true,
		})
		if err := tlsUpstream.Handshake(); err != nil {
			log.Printf("[CONNECT] 上游 TLS 握手失败: %v", err)
			clientConn.Write([]byte("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\n" + err.Error()))
			return
		}
		upstream = tlsUpstream
	}

	authHeader := ""
	if auth.Username != "" && auth.Password != "" {
		authHeader = "Proxy-Authorization: Basic " + basicAuthEncode(auth.Username, auth.Password) + "\r\n"
	}
	connectReq := fmt.Sprintf("CONNECT %s HTTP/1.1\r\nHost: %s\r\n%s\r\n", target, target, authHeader)
	if _, err := upstream.Write([]byte(connectReq)); err != nil {
		log.Printf("[CONNECT] 写上游失败: %v", err)
		clientConn.Write([]byte("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\n" + err.Error()))
		return
	}

	br := bufio.NewReader(upstream)
	resp, err := http.ReadResponse(br, nil)
	if err != nil {
		log.Printf("[CONNECT] 读上游响应失败: %v", err)
		clientConn.Write([]byte("HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\n" + err.Error()))
		return
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		log.Printf("[CONNECT] 上游返回 %d: %s", resp.StatusCode, string(body))
		clientConn.Write([]byte(fmt.Sprintf("HTTP/1.1 %d %s\r\n", resp.StatusCode, resp.Status)))
		for k, vv := range resp.Header {
			for _, v := range vv {
				clientConn.Write([]byte(k + ": " + v + "\r\n"))
			}
		}
		clientConn.Write([]byte("\r\n"))
		clientConn.Write(body)
		return
	}
	resp.Body.Close()

	// 将上游已读的剩余数据（如有）与 br 合并后与 client 双向转发
	if _, err := clientConn.Write([]byte("HTTP/1.1 200 Connection Established\r\n\r\n")); err != nil {
		return
	}
	go io.Copy(upstream, clientConn)
	io.Copy(clientConn, br)
}

// handleHTTP 将请求转发至上游代理（从 lines_proxy.json 按当前线路读取）。CONNECT 走 handleConnect（TCP+TLS+手动 CONNECT），其余用 Transport
func handleHTTP(w http.ResponseWriter, r *http.Request) {
	config.mu.RLock()
	auth := config.Auth
	proxyURL := config.UpstreamProxyURL
	config.mu.RUnlock()

	if proxyURL == nil {
		http.Error(w, "未配置上游代理，请运行 python get_all_lines_proxy.py 生成 lines_proxy.json 并确保当前线路在其中", http.StatusBadGateway)
		return
	}

	if r.Method == http.MethodConnect {
		handleConnect(w, r, proxyURL, auth)
		return
	}

	// 非 CONNECT：用 Transport 转发
	transport := &http.Transport{
		Proxy:           http.ProxyURL(proxyURL),
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	if auth.Username != "" {
		transport.ProxyConnectHeader = http.Header{}
		transport.ProxyConnectHeader.Add("Proxy-Authorization", "Basic "+basicAuthEncode(auth.Username, auth.Password))
	}
	client := &http.Client{Transport: transport, Timeout: 90 * time.Second}

	if r.URL.Scheme == "" {
		if r.URL.Host == "" {
			r.URL.Host = r.Host
			if r.URL.Host == "" && r.URL.Path != "" {
				r.URL.Host = r.URL.Path
				r.URL.Path = ""
			}
		}
		r.URL.Scheme = "http"
	}
	r.RequestURI = ""
	resp, err := client.Do(r)
	if err != nil {
		log.Printf("[代理转发失败] %v", err)
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	for k, vv := range resp.Header {
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

func main() {
	cwd, _ := os.Getwd()
	config.ProjectRoot = filepath.Dir(cwd) // 假设在 proxy_manager 目录运行

	log.Println("=== iLink 代理管理器 ===")

	err := config.loadProxyAuth()
	if err != nil {
		log.Fatalf("加载代理配置失败（请先在项目目录生成 proxy_current.json）: %v", err)
	}
	log.Printf("已加载代理信息 - 线路: %s, 用户: %s", config.Auth.Sid, config.Auth.Username)

	config.loadLinesProxy()
	if err := config.applyUpstreamForSid(config.Auth.Sid); err != nil {
		log.Printf("⚠️ 未加载上游代理: %v（请运行 python get_all_lines_proxy.py 生成 lines_proxy.json）", err)
	} else {
		config.mu.RLock()
		u := config.UpstreamProxyURL
		config.mu.RUnlock()
		if u != nil {
			log.Printf("已加载上游代理: %s", u.String())
		}
	}

	// 自定义 Handler：CONNECT 请求的 Path 为 authority（如 www.google.com:443），不以 / 开头，默认 ServeMux 会 404
	proxyMux := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/reload":
			cors(w, r)
			if err := config.loadProxyAuth(); err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
			config.loadLinesProxy()
			_ = config.applyUpstreamForSid(config.Auth.Sid)
			log.Printf("已重新加载配置 - 线路: %s", config.Auth.Sid)
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			json.NewEncoder(w).Encode(map[string]string{"sid": config.Auth.Sid, "msg": "ok"})
		case "/api/switch":
			apiSwitch(w, r)
		case "/api/lines":
			apiLines(w, r)
		case "/api/current":
			apiCurrent(w, r)
		default:
			handleHTTP(w, r)
		}
	})

	// 启动代理服务 (8888)
	go func() {
		addr := fmt.Sprintf(":%d", config.ProxyPort)
		log.Printf("HTTP 代理: http://localhost%s", addr)
		if err := http.ListenAndServe(addr, proxyMux); err != nil {
			log.Fatal("代理服务启动失败: ", err)
		}
	}()

	// 启动 Web 控制面板 (8889)
	panelMux := http.NewServeMux()
	panelMux.HandleFunc("/", servePanel)
	panelAddr := fmt.Sprintf(":%d", config.PanelPort)
	log.Printf("Web 控制面板: http://localhost%s", panelAddr)
	log.Printf("重新加载配置: http://localhost:%d/api/reload", config.ProxyPort)
	if err := http.ListenAndServe(panelAddr, panelMux); err != nil {
		log.Fatal("控制面板启动失败: ", err)
	}
}
