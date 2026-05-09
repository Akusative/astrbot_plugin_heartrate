"""
HDS Heart Rate HTTP Receiver v2
HDS App uses HTTP PUT to send health data, not WebSocket
"""
import asyncio
import json
import time
import os
import sys
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# 数据文件路径
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(DATA_DIR, "heartrate_latest.json")
LOG_FILE = os.path.join(DATA_DIR, "heartrate_server.log")

# 全局心率数据
heartrate_data = {
    "bpm": 0,
    "timestamp": 0,
    "last_update": "",
    "history": [],
    "session_active": False,
    "raw_data": {}
}

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

def save_data():
    export = {
        "bpm": heartrate_data["bpm"],
        "timestamp": heartrate_data["timestamp"],
        "last_update": heartrate_data["last_update"],
        "session_active": heartrate_data["session_active"],
        "history_count": len(heartrate_data["history"]),
        "recent_history": heartrate_data["history"][-20:],
        "raw_data": heartrate_data["raw_data"]
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

def extract_heartrate(data):
    """从不同格式数据中提取心率"""
    hr = None
    
    if isinstance(data, dict):
        # 直接字段
        for key in ["heartRate", "heart_rate", "hr", "bpm", "HeartRate", "heartrate", "value"]:
            if key in data:
                try:
                    hr = int(float(data[key]))
                    return hr
                except (ValueError, TypeError):
                    pass
        
        # HDS Overlay格式: {"data": {"heartRate": 74}}
        if "data" in data and isinstance(data["data"], dict):
            return extract_heartrate(data["data"])
        
        # HDS App格式: {"data": "heartRate:81"}
        if "data" in data and isinstance(data["data"], str):
            parts = data["data"].split(":")
            if len(parts) >= 2:
                try:
                    return int(float(parts[1].strip()))
                except (ValueError, TypeError):
                    pass
        
        # 遍历所有值找数字
        for key, val in data.items():
            if isinstance(val, (int, float)) and 30 <= val <= 250:
                if any(hint in key.lower() for hint in ["heart", "hr", "bpm", "pulse", "rate"]):
                    return int(val)
    
    elif isinstance(data, (int, float)):
        return int(data)
    
    return hr

def update_heartrate_data(hr, raw_data, method=""):
    if hr is not None and 30 <= hr <= 250:
        now = datetime.now()
        heartrate_data["raw_data"] = raw_data
        heartrate_data["session_active"] = True
        heartrate_data["bpm"] = hr
        heartrate_data["timestamp"] = time.time()
        heartrate_data["last_update"] = now.strftime("%Y-%m-%d %H:%M:%S")
        
        heartrate_data["history"].append({
            "bpm": hr,
            "time": now.strftime("%H:%M:%S"),
            "timestamp": time.time()
        })
        if len(heartrate_data["history"]) > 500:
            heartrate_data["history"] = heartrate_data["history"][-500:]
        
        log(f"<3 Heart Rate: {hr} BPM {method}")
        save_data()
        return True
    return False

class HDSHandler(BaseHTTPRequestHandler):
    """处理HTTP请求"""
    
    def log_message(self, format, *args):
        # 静默默认日志
        pass
    
    def _send_response(self, code=200, body=b"OK", content_type="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def do_OPTIONS(self):
        self._send_response(200, b"")
    
    def do_PUT(self):
        """HDS, Notify or Health Sync sending data via PUT/POST"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        
        self._send_response(200, b"OK")
        
        try:
            body_str = body.decode("utf-8", errors="replace")
            # 缩略打印长数据
            log(f"{self.command} {self.path} | Body: {body_str[:100]}")
            
            # 尝试解析JSON
            try:
                data = json.loads(body_str)
            except json.JSONDecodeError:
                # 尝试解析 URL 编码表单数据
                if "=" in body_str:
                    parsed = urllib.parse.parse_qs(body_str)
                    data = {k: v[0] for k, v in parsed.items()}
                else:
                    data = body_str
            
            raw_data = data if isinstance(data, dict) else {"raw": str(data)}
            hr = extract_heartrate(data)
            update_heartrate_data(hr, raw_data, method=f"(via {self.command})")
            
        except Exception as e:
            log(f"Error processing {self.command}: {e}")
    
    def do_POST(self):
        """统一走 PUT 的处理逻辑"""
        self.do_PUT()
    
    def do_GET(self):
        """状态页面和API以及GET方式推送"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        # 支持简单 GET 推送，如 /api/push?bpm=75
        if path.startswith("/api/push") or path.startswith("/push"):
            query = urllib.parse.parse_qs(parsed_path.query)
            data = {k: v[0] for k, v in query.items()}
            hr = extract_heartrate(data)
            
            if update_heartrate_data(hr, data, method="(via GET)"):
                self._send_response(200, b"OK")
            else:
                self._send_response(400, b"Missing or invalid heart rate data")
            return
            
        if path == "/api/heartrate":
            body = json.dumps({
                "bpm": heartrate_data["bpm"],
                "timestamp": heartrate_data["timestamp"],
                "last_update": heartrate_data["last_update"],
                "session_active": heartrate_data["session_active"],
                "recent": heartrate_data["history"][-10:]
            }, ensure_ascii=False).encode("utf-8")
            self._send_response(200, body, "application/json; charset=utf-8")
            return
        
        if path == "/status" or path == "/":
            status = "ONLINE" if heartrate_data["session_active"] else "OFFLINE"
            bpm = heartrate_data["bpm"] if heartrate_data["bpm"] > 0 else "--"
            html = f"""<html><head><meta charset='utf-8'><title>Heart Rate Server</title>
            <meta http-equiv='refresh' content='3'>
            <style>
                body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; 
                       display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
                .card {{ background: #16213e; border-radius: 20px; padding: 40px 60px; text-align: center; 
                        box-shadow: 0 8px 32px rgba(0,0,0,0.3); }}
                .bpm {{ font-size: 96px; font-weight: bold; color: #e94560; }}
                .label {{ font-size: 18px; color: #888; margin-top: 10px; }}
                .status {{ font-size: 14px; margin-top: 20px; }}
            </style></head>
            <body><div class='card'>
                <div class='bpm'>{bpm}</div>
                <div class='label'>BPM</div>
                <div class='status'>{status} | {heartrate_data["last_update"] or "Waiting..."}</div>
            </div></body></html>""".encode("utf-8")
            self._send_response(200, html, "text/html; charset=utf-8")
            return
            
        # 默认返回OK - 客户端探测
        self._send_response(200, b"Heart Rate Receiver OK")

def run_server(port=3476):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except PermissionError:
        pass  
    
    log("=" * 50)
    log("  Heart Rate Receiver v2 (HTTP+GET+POST+PUT)")
    log(f"  Port: {port}")
    log(f"  Status: http://localhost:{port}/status")
    log(f"  API GET Push: http://localhost:{port}/api/push?bpm=xx")
    log(f"  API POST Push: http://localhost:{port}/api/push")
    log(f"  Data: {DATA_FILE}")
    log("=" * 50)
    log("Waiting for data connection (HDS/Tasker/Health Sync)...")
    
    save_data()
    
    server = HTTPServer(("0.0.0.0", port), HDSHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Server stopped")
        server.server_close()

if __name__ == "__main__":
    run_server(3476)
