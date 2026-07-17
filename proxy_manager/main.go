// iLink 代理管理器：读取 Python 保存的认证信息，提供本地 HTTP/HTTPS 代理与线路切换 API。
// 上游是 HTTPS 代理（TLS-wrapped HTTP proxy），需要先 TLS 握手再发送代理请求。
// 在 proxy_manager 目录下编译运行: go run .
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
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

// ProxyAuth 代理认证信息（与 proxy_current.json 结构对应）
type ProxyAuth struct {
	Username     string `json:"username"`
	Password     string `json:"password"`
	Sid          string `json:"sid"`
	UpstreamHost string `json:"upstream_host"`
	UpstreamPort string `json:"upstream_port"`
}

// GlobalConfig 全局配置
type GlobalConfig struct {
	ProxyPort   int    // 本地监听端口
	PanelPort   int    // Web 控制面板端口
	PythonCmd   string // Python 解释器
	ProjectRoot string // 项目根目录
	Auth        ProxyAuth
	mu          sync.RWMutex
}

var config = &GlobalConfig{
	ProxyPort: 8888,
	PanelPort: 8889,
	PythonCmd: "python",
}

// loadProxyAuth 从 proxy_current.json 加载认证信息
func (c *GlobalConfig) loadProxyAuth() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	authFile := filepath.Join(c.ProjectRoot, "proxy_current.json")
	data, err := os.ReadFile(authFile)
	if err != nil {
		return fmt.Errorf("读取认证文件失败: %v", err)
	}

	var auth ProxyAuth
	if err := json.Unmarshal(data, &auth); err != nil {
		return fmt.Errorf("解析认证文件失败: %v", err)
	}

	if auth.UpstreamHost == "" {
		auth.UpstreamHost = "cmb-gate.gamecaches.com"
	}
	if auth.UpstreamPort == "" {
		auth.UpstreamPort = "25670"
	}

	c.Auth = auth
	return nil
}

// getUpstreamAddr 返回上游代理地址 host:port
func (c *GlobalConfig) getUpstreamAddr() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return fmt.Sprintf("%s:%s", c.Auth.UpstreamHost, c.Auth.UpstreamPort)
}

// executePythonScript 在 ProjectRoot 下执行 Python 脚本
func (c *GlobalConfig) executePythonScript(scriptName string, args ...string) error {
	scriptPath := filepath.Join(c.ProjectRoot, scriptName)
	cmdArgs := append([]string{scriptPath}, args...)

	cmd := exec.Command(c.PythonCmd, cmdArgs...)
	cmd.Dir = c.ProjectRoot
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return cmd.Run()
}

// switchProxy 调用 get_proxy_info.py 切换线路并重新加载认证
func (c *GlobalConfig) switchProxy(sid string) error {
	log.Printf("[切换] 开始切换代理至线路: %s", sid)

	if err := c.executePythonScript("get_proxy_info.py", sid); err != nil {
		return fmt.Errorf("执行 get_proxy_info.py 失败: %v", err)
	}

	if err := c.loadProxyAuth(); err != nil {
		return fmt.Errorf("加载代理认证信息失败: %v", err)
	}

	log.Printf("[切换] 成功! 线路: %s, 上游: %s:%s", c.Auth.Sid, c.Auth.UpstreamHost, c.Auth.UpstreamPort)
	return nil
}

// cors 设置跨域头
func cors(w http.ResponseWriter) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
}

// apiHealth 健康检查
func apiHealth(w http.ResponseWriter, r *http.Request) {
	cors(w)
	config.mu.RLock()
	auth := config.Auth
	config.mu.RUnlock()

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":        "ok",
		"sid":           auth.Sid,
		"username":      auth.Username,
		"upstream_host": auth.UpstreamHost,
		"upstream_port": auth.UpstreamPort,
	})
}

// apiLines 返回线路列表
func apiLines(w http.ResponseWriter, r *http.Request) {
	cors(w)
	if r.Method == http.MethodOptions {
		return
	}
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	data, err := os.ReadFile(filepath.Join(config.ProjectRoot, "lines.json"))
	if err != nil {
		http.Error(w, "lines.json not found, run: python linelist.py", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Write(data)
}

// apiCurrent 返回当前线路
func apiCurrent(w http.ResponseWriter, r *http.Request) {
	cors(w)
	if r.Method == http.MethodOptions {
		return
	}
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	config.mu.RLock()
	auth := config.Auth
	config.mu.RUnlock()
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"username":      auth.Username,
		"sid":           auth.Sid,
		"upstream_host": auth.UpstreamHost,
		"upstream_port": auth.UpstreamPort,
	})
}

// servePanel Web 控制面板
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
    body { font-family: system-ui, sans-serif; margin: 24px; background: #1a1a2e; color: #eee; }
    h1 { font-size: 1.25rem; margin-bottom: 16px; }
    .status { background: #16213e; padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 0.9rem; }
    .current { background: #16213e; padding: 12px; border-radius: 8px; margin-bottom: 16px; font-size: 0.9rem; }
    .lines { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
    .btn { padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9rem;
           background: #0f3460; color: #eee; transition: background 0.2s; }
    .btn:hover { background: #e94560; }
    .btn.active { background: #e94560; }
    .msg { margin-top: 12px; padding: 8px; border-radius: 4px; font-size: 0.85rem; display: none; }
    .msg.show { display: block; }
    .msg.ok { background: #0d5c0d; }
    .msg.err { background: #5c0d0d; }
    .info { margin-top: 16px; font-size: 0.8rem; color: #888; }
    .info code { background: #0f3460; padding: 2px 6px; border-radius: 3px; }
    .refresh { margin-top: 10px; }
    .refresh button { background: #0f3460; color: #eee; border: none; padding: 6px 14px;
                     border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
  </style>
</head>
<body>
  <h1>iLink 线路切换</h1>
  <div class="status">代理状态: <span id="status">检查中...</span></div>
  <div class="current">当前线路: <span id="current">加载中...</span></div>
  <div class="lines" id="lines">加载中...</div>
  <div id="msg"></div>
  <div class="refresh"><button onclick="loadAll()">刷新</button></div>
  <div class="info">
    本地代理: <code>127.0.0.1:8888</code> | 面板: <code>127.0.0.1:8889</code>
  </div>
  <script>
    const API = 'http://localhost:8888';
    async function loadStatus() {
      try {
        const r = await fetch(API + '/api/health');
        const d = await r.json();
        document.getElementById('status').textContent = d.upstream_host + ':' + d.upstream_port + ' OK';
        document.getElementById('status').style.color = '#4ecca3';
      } catch (e) {
        document.getElementById('status').textContent = 'Offline';
        document.getElementById('status').style.color = '#e94560';
      }
    }
    async function loadCurrent() {
      try {
        const r = await fetch(API + '/api/current');
        const d = await r.json();
        document.getElementById('current').textContent = d.sid ? (d.sid + ' (' + d.username + ')') : 'Not set';
      } catch (e) {
        document.getElementById('current').textContent = 'Failed';
      }
    }
    async function loadLines() {
      const el = document.getElementById('lines');
      try {
        const r = await fetch(API + '/api/lines');
        const lines = await r.json();
        if (!Array.isArray(lines) || lines.length === 0) {
          el.innerHTML = '<span>No lines, run: python linelist.py</span>';
          return;
        }
        const cur = await (await fetch(API + '/api/current')).json();
        el.innerHTML = lines.map(l => {
          const sid = l.line_sn || '';
          const name = (l.name || sid) + (l.connect ? '' : ' [full]');
          const active = sid === cur.sid ? ' active' : '';
          return '<button class="btn' + active + '" data-sid="' + sid + '">' + name + '</button>';
        }).join('');
        el.querySelectorAll('.btn').forEach(b => {
          b.onclick = async () => {
            const sid = b.dataset.sid;
            showMsg('Switching...', '');
            try {
              const r = await fetch(API + '/api/switch?sid=' + encodeURIComponent(sid));
              const d = await r.json();
              if (r.ok && d.status === 'ok') {
                showMsg('Switched to ' + sid, 'ok');
                loadCurrent(); loadStatus();
                el.querySelectorAll('.btn').forEach(x => x.classList.remove('active'));
                b.classList.add('active');
              } else {
                showMsg('Failed: ' + JSON.stringify(d), 'err');
              }
            } catch (e) {
              showMsg('Error: ' + e.message, 'err');
            }
          };
        });
      } catch (e) {
        el.innerHTML = '<span>Load failed, ensure proxy is running</span>';
      }
    }
    function showMsg(text, cls) {
      const el = document.getElementById('msg');
      el.textContent = text;
      el.className = 'msg show ' + cls;
      if (cls === 'ok') setTimeout(() => el.classList.remove('show'), 3000);
    }
    function loadAll() { loadStatus(); loadCurrent(); loadLines(); }
    loadAll();
    setInterval(loadStatus, 15000);
  </script>
</body>
</html>`

// connectToUpstream 连接到上游 HTTPS 代理，返回 TLS 连接
func connectToUpstream() (*tls.Conn, error) {
	addr := config.getUpstreamAddr()
	tlsConfig := &tls.Config{
		InsecureSkipVerify: true, // 上游代理可能使用自签名证书
	}

	dialer := &net.Dialer{Timeout: 10 * time.Second}
	rawConn, err := dialer.Dial("tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("TCP 连接失败: %v", err)
	}

	tlsConn := tls.Client(rawConn, tlsConfig)
	if err := tlsConn.Handshake(); err != nil {
		rawConn.Close()
		return nil, fmt.Errorf("TLS 握手失败: %v", err)
	}

	return tlsConn, nil
}

// makeBasicAuth 生成 Proxy-Authorization 头的值
func makeBasicAuthHdr() string {
	config.mu.RLock()
	defer config.mu.RUnlock()
	auth := config.Auth
	authStr := fmt.Sprintf("%s:%s", auth.Username, auth.Password)
	return "Basic " + base64.StdEncoding.EncodeToString([]byte(authStr))
}

// handleHTTP 通过上游 HTTPS 代理转发 HTTP 请求
// 上游 HTTPS 代理只支持 CONNECT，因此 HTTP 请求也通过 CONNECT 隧道转发
func handleHTTP(w http.ResponseWriter, r *http.Request) {
	targetURL := r.URL.String()
	log.Printf("[HTTP] %s %s", r.Method, targetURL)

	// 连接到上游 HTTPS 代理
	tlsConn, err := connectToUpstream()
	if err != nil {
		log.Printf("[HTTP] 连接上游失败: %v", err)
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer tlsConn.Close()

	// 通过 CONNECT 建立到目标主机的隧道
	connectPort := r.URL.Port()
	if connectPort == "" {
		connectPort = "80"
	}
	connectTarget := fmt.Sprintf("%s:%s", r.URL.Hostname(), connectPort)

	connectReq := fmt.Sprintf("CONNECT %s HTTP/1.1\r\n", connectTarget)
	connectReq += fmt.Sprintf("Host: %s\r\n", connectTarget)
	connectReq += fmt.Sprintf("Proxy-Authorization: %s\r\n", makeBasicAuthHdr())
	connectReq += "\r\n"

	if _, err := tlsConn.Write([]byte(connectReq)); err != nil {
		log.Printf("[HTTP] 发送 CONNECT 失败: %v", err)
		http.Error(w, "Failed to send CONNECT", http.StatusBadGateway)
		return
	}

	// 读取 CONNECT 响应
	statusLine, err := readLine(tlsConn)
	if err != nil {
		log.Printf("[HTTP] 读取 CONNECT 响应失败: %v", err)
		http.Error(w, "Failed to read CONNECT response", http.StatusBadGateway)
		return
	}
	log.Printf("[HTTP] CONNECT 上游响应: %s", statusLine)

	// 跳过响应头
	for {
		line, err := readLine(tlsConn)
		if err != nil {
			return
		}
		if line == "" {
			break
		}
	}

	if !strings.Contains(statusLine, "200") {
		log.Printf("[HTTP] CONNECT 被拒绝: %s", statusLine)
		http.Error(w, "Upstream proxy rejected CONNECT", http.StatusBadGateway)
		return
	}

	// CONNECT 成功后，通过隧道发送实际的 HTTP 请求
	reqLine := fmt.Sprintf("%s %s HTTP/1.1\r\n", r.Method, r.URL.Path)
	if r.URL.RawQuery != "" {
		reqLine = fmt.Sprintf("%s %s?%s HTTP/1.1\r\n", r.Method, r.URL.Path, r.URL.RawQuery)
	}
	reqLine += fmt.Sprintf("Host: %s\r\n", r.URL.Host)

	for key, values := range r.Header {
		keyLower := strings.ToLower(key)
		if keyLower == "proxy-connection" || keyLower == "proxy-authorization" {
			continue
		}
		for _, v := range values {
			reqLine += fmt.Sprintf("%s: %s\r\n", key, v)
		}
	}
	reqLine += "Connection: close\r\n\r\n"

	if _, err := tlsConn.Write([]byte(reqLine)); err != nil {
		return
	}

	if r.Body != nil {
		io.Copy(tlsConn, r.Body)
	}

	// 读取 HTTP 响应并转发
	resp, err := http.ReadResponse(bufio.NewReader(tlsConn), r)
	if err != nil {
		log.Printf("[HTTP] 读取 HTTP 响应失败: %v", err)
		http.Error(w, "读取上游响应失败", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	for key, values := range resp.Header {
		for _, v := range values {
			w.Header().Add(key, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)

	log.Printf("[HTTP] %d %s %s", resp.StatusCode, r.Method, targetURL)
}

// handleConnect 处理 HTTPS CONNECT 隧道
func handleConnect(w http.ResponseWriter, r *http.Request) {
	target := r.Host
	log.Printf("[CONNECT] %s", target)

	// 连接到上游 HTTPS 代理
	tlsConn, err := connectToUpstream()
	if err != nil {
		log.Printf("[CONNECT] 连接上游失败: %v", err)
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer tlsConn.Close()

	// 通过上游 TLS 连接发送 CONNECT 请求
	connectReq := fmt.Sprintf("CONNECT %s HTTP/1.1\r\n", target)
	connectReq += fmt.Sprintf("Host: %s\r\n", target)
	connectReq += fmt.Sprintf("Proxy-Authorization: %s\r\n", makeBasicAuthHdr())
	connectReq += "\r\n"

	if _, err := tlsConn.Write([]byte(connectReq)); err != nil {
		log.Printf("[CONNECT] 发送 CONNECT 失败: %v", err)
		http.Error(w, "Failed to send CONNECT", http.StatusBadGateway)
		return
	}

	// 手动读取上游 CONNECT 响应（不使用 bufio.Reader，避免缓冲问题）
	statusLine, err := readLine(tlsConn)
	if err != nil {
		log.Printf("[CONNECT] 读取状态行失败: %v", err)
		http.Error(w, "Failed to read response", http.StatusBadGateway)
		return
	}
	log.Printf("[CONNECT] 上游响应: %s", statusLine)

	// 读取所有响应头（直到空行）
	for {
		line, err := readLine(tlsConn)
		if err != nil {
			log.Printf("[CONNECT] 读取响应头失败: %v", err)
			http.Error(w, "Failed to read headers", http.StatusBadGateway)
			return
		}
		if line == "" {
			break
		}
	}

	// 检查状态码
	if !strings.Contains(statusLine, "200") {
		log.Printf("[CONNECT] 上游拒绝: %s", statusLine)
		http.Error(w, "Upstream proxy rejected CONNECT", http.StatusBadGateway)
		return
	}

	// 劫持客户端连接
	hijacker, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "Hijacking not supported", http.StatusInternalServerError)
		return
	}

	clientConn, _, err := hijacker.Hijack()
	if err != nil {
		http.Error(w, err.Error(), http.StatusServiceUnavailable)
		return
	}
	defer clientConn.Close()

	// 先发送 200 响应给客户端
	clientConn.Write([]byte("HTTP/1.1 200 Connection Established\r\n\r\n"))

	// 双向转发
	done := make(chan struct{}, 2)

	go func() {
		io.Copy(tlsConn, clientConn)
		done <- struct{}{}
	}()
	go func() {
		io.Copy(clientConn, tlsConn)
		done <- struct{}{}
	}()

	<-done
	tlsConn.Close()
	clientConn.Close()

	log.Printf("[CONNECT] 隧道关闭: %s", target)
}

// readLine 从连接中读取一行（以 \r\n 结尾）
func readLine(conn net.Conn) (string, error) {
	var line []byte
	buf := make([]byte, 1)
	for {
		_, err := conn.Read(buf)
		if err != nil {
			return "", err
		}
		line = append(line, buf[0])
		if len(line) >= 2 && line[len(line)-2] == '\r' && line[len(line)-1] == '\n' {
			return string(line[:len(line)-2]), nil
		}
	}
}

// proxyHandler 自定义 HTTP 处理器，正确处理 CONNECT 方法
type proxyHandler struct{}

func (h *proxyHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// 处理 CONNECT 请求（Go 的 ServeMux 无法正确路由 CONNECT）
	if r.Method == http.MethodConnect {
		handleConnect(w, r)
		return
	}

	// API 路由（仅对非 CONNECT 请求）
	path := r.URL.Path
	switch {
	case path == "/api/health":
		apiHealth(w, r)
	case path == "/api/lines":
		apiLines(w, r)
	case path == "/api/current":
		apiCurrent(w, r)
	case path == "/api/switch":
		cors(w)
		if r.Method == http.MethodOptions {
			return
		}
		sid := r.URL.Query().Get("sid")
		if sid == "" {
			http.Error(w, "sid is required", http.StatusBadRequest)
			return
		}
		if err := config.switchProxy(sid); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		fmt.Fprintf(w, `{"status":"ok","sid":"%s"}`, sid)
	default:
		// 代理转发
		handleHTTP(w, r)
	}
}

// isPortAvailable 检查端口是否可监听
func isPortAvailable(port int) (bool, string) {
	addr := fmt.Sprintf(":%d", port)
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		if isAddrInUse(err) {
			return false, fmt.Sprintf("端口 %d 已被占用", port)
		}
		return false, fmt.Sprintf("端口 %d 不可用: %v", port, err)
	}
	ln.Close()
	return true, ""
}

// isAddrInUse 判断错误是否为地址已被占用
func isAddrInUse(err error) bool {
	if opErr, ok := err.(*net.OpError); ok {
		if sysErr, ok := opErr.Err.(*os.SyscallError); ok {
			return sysErr.Err == syscall.EADDRINUSE
		}
	}
	return false
}

func main() {
	cwd, _ := os.Getwd()
	config.ProjectRoot = filepath.Dir(cwd)

	log.Println("========================================")
	log.Println("   iLink 代理管理器 v2.1 (HTTPS upstream)")
	log.Println("========================================")

	err := config.loadProxyAuth()
	if err != nil {
		log.Printf("[初始化] 未找到代理信息 (%v)", err)
		log.Printf("[初始化] 尝试默认线路 (sg-bgp)...")
		if err := config.switchProxy("sg-bgp"); err != nil {
			log.Printf("[初始化] 获取默认线路失败: %v", err)
			log.Println("[初始化] 使用 proxy_current.json 中的备用凭据继续")
			_ = config.loadProxyAuth()
		}
	}

	config.mu.RLock()
	log.Printf("[初始化] 线路: %s", config.Auth.Sid)
	log.Printf("[初始化] 上游: %s:%s (HTTPS)", config.Auth.UpstreamHost, config.Auth.UpstreamPort)
	config.mu.RUnlock()

	// 启动前检查端口
	ok, msg := isPortAvailable(config.ProxyPort)
	if !ok {
		log.Printf("[错误] %s — 请先关闭占用端口的进程或等待其释放", msg)
		log.Println("[提示] Windows: netstat -ano | findstr :8888  然后 taskkill /F /PID <PID>")
		os.Exit(1)
	}
	ok, msg = isPortAvailable(config.PanelPort)
	if !ok {
		log.Printf("[错误] %s — 请先关闭占用端口的进程或等待其释放", msg)
		log.Println("[提示] Windows: netstat -ano | findstr :8889  然后 taskkill /F /PID <PID>")
		os.Exit(1)
	}

	// 代理服务 goroutine 错误通道
	proxyErr := make(chan error, 1)

	go func() {
		addr := fmt.Sprintf(":%d", config.ProxyPort)
		log.Printf("[代理] HTTP/HTTPS 代理: localhost%s", addr)
		log.Printf("[代理] 切换: localhost%s/api/switch?sid=line_sn", addr)
		log.Printf("[代理] 健康: localhost%s/api/health", addr)
		if err := http.ListenAndServe(addr, &proxyHandler{}); err != nil {
			proxyErr <- err
		}
	}()

	// 等待代理服务就绪
	time.Sleep(300 * time.Millisecond)
	select {
	case err := <-proxyErr:
		log.Printf("[代理] 启动失败: %v", err)
		os.Exit(1)
	default:
	}

	// 启动控制面板
	panelMux := http.NewServeMux()
	panelMux.HandleFunc("/", servePanel)
	panelAddr := fmt.Sprintf(":%d", config.PanelPort)
	log.Printf("[面板] 控制面板: localhost%s", panelAddr)
	log.Println("========================================")
	if err := http.ListenAndServe(panelAddr, panelMux); err != nil {
		log.Printf("[面板] 启动失败: %v", err)
		os.Exit(1)
	}
}
