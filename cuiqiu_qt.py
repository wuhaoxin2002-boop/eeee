#!/usr/bin/env python3
import json, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from PySide6.QtWidgets import QApplication, QFormLayout, QLineEdit, QMainWindow, QPushButton, QLabel, QTextEdit, QWidget, QMessageBox
from PySide6.QtCore import QObject, Signal
import cuiqiu_captcha as api

APP_VERSION = '1.0.8'

class LogBridge(QObject):
    message = Signal(str)

class ApiServer(ThreadingHTTPServer):
    allow_reuse_address = True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): self.server.window.log(fmt % args)
    def do_GET(self): self.handle_request(parse_qs(urlparse(self.path).query))
    def do_POST(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get('content-length', 0))) or b'{}')
            self.handle_request({k: [str(v)] for k, v in data.items()})
        except Exception: self.send_json(400, {'error': 'invalid JSON'})
    def handle_request(self, query):
        mail, password = query.get('mail', [''])[0].strip(), query.get('password', [''])[0]
        if not mail or not password: return self.send_json(400, {'error': 'mail and password are required'})
        request_id = uuid.uuid4().hex[:8]; started = time.monotonic()
        log = lambda text: self.server.window.log(f'[{request_id}] {text}')
        log(f'收到请求 mail={mail}')
        try:
            code = api.fetch_latest_code(mail, password, log); self.send_json(200, {'code': code, 'found': bool(code)})
            log(f'请求完成 code={code or "未找到"} 耗时={time.monotonic()-started:.1f}s')
        except Exception as exc: self.send_json(500, {'error': str(exc)}); log(f'请求失败: {exc} 耗时={time.monotonic()-started:.1f}s')
    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)

class Window(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f'邮箱验证码服务 v{APP_VERSION}'); self.setFixedSize(620, 430); self.server = None
        self.log_bridge=LogBridge(); self.log_bridge.message.connect(self._append_log)
        form = QFormLayout(); self.host=QLineEdit('127.0.0.1'); self.port=QLineEdit('1231'); self.button=QPushButton('启动服务'); self.address=QLabel('服务未启动'); self.copy_button=QPushButton('复制'); self.copy_button.setEnabled(False); self.copy_button.clicked.connect(self.copy_address); self.logs=QTextEdit(); self.logs.setReadOnly(True)
        address_row=QWidget(); address_layout=QFormLayout(address_row); address_layout.setContentsMargins(0,0,0,0); address_layout.addRow(self.address, self.copy_button)
        form.addRow('监听地址',self.host); form.addRow('端口',self.port); form.addRow('',self.button); form.addRow('接口地址',address_row); form.addRow('运行日志',self.logs)
        root=QWidget(); root.setLayout(form); self.setCentralWidget(root); self.button.clicked.connect(self.toggle)
    def log(self, text): self.log_bridge.message.emit(str(text))
    def _append_log(self, text):
        self.logs.append(time.strftime('%H:%M:%S ') + text)
        self.logs.ensureCursorVisible()
    def toggle(self):
        if self.server: self.server.shutdown(); self.server.server_close(); self.server=None; self.button.setText('启动服务'); self.address.setText('服务未启动'); self.copy_button.setEnabled(False); self.log('服务已停止'); return
        try:
            port=int(self.port.text()); self.server=ApiServer((self.host.text().strip(),port),Handler); self.server.window=self; threading.Thread(target=self.server.serve_forever,daemon=True).start(); self.button.setText('停止服务'); self.address.setText(f'http://{self.host.text().strip()}:{port}/captcha'); self.copy_button.setEnabled(True); self.log(f'服务已启动 v{APP_VERSION}: http://{self.host.text().strip()}:{port}/captcha（进程内模式）')
        except Exception as exc: self.server=None; QMessageBox.critical(self,'启动失败',str(exc)); self.log(f'启动失败: {exc}')
    def copy_address(self):
        QApplication.clipboard().setText(self.address.text()); self.log('接口地址已复制')
    def closeEvent(self,event):
        if self.server: self.server.shutdown(); self.server.server_close()
        event.accept()

if __name__ == '__main__':
    app=QApplication([]); window=Window(); window.show(); app.exec()
