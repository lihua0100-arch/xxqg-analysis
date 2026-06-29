"""mitmproxy 拦截脚本 - 假激活响应
用法:
  mitmdump -s eyblock.py -p 8888
  
  然后在手机上:
  设置 -> WiFi -> HTTP代理 -> 手动
  服务器: <你电脑IP>, 端口: 8888
"""
from mitmproxy import http

def response(flow: http.HTTPFlow):
    # 拦截所有 eydata 和 t3yanzheng 的请求
    host = flow.request.pretty_host
    if 'eydata' in host or 't3yanzheng' in host:
        # 返回假激活成功响应
        flow.response = http.Response.make(
            200,
            b"2099-12-31 23:59:59",  # 假过期时间
            {"Content-Type": "text/plain"}
        )
        print(f"[FAKED] {flow.request.pretty_url}")
