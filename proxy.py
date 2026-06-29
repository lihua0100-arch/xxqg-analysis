"""完整代理 - 支持 HTTP CONNECT 隧道 + 拦截激活请求
用法: python3 proxy.py [端口]
"""
import socket, threading, sys, select

FAKE_RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 19\r\n\r\n2099-12-31 23:59:59"

TARGET_HOSTS = [b'eydata.net', b't3yanzheng.cn']

def handle_client(client_sock, addr):
    try:
        request = b''
        while b'\r\n\r\n' not in request:
            data = client_sock.recv(4096)
            if not data: break
            request += data
            if len(request) > 65536: break
        
        first_line = request.split(b'\r\n')[0]
        parts = first_line.split(b' ')
        if len(parts) < 2:
            client_sock.close()
            return
        
        method = parts[0]
        url_path = parts[1]
        
        # Parse host from URL or Host header
        host = b''
        if url_path.startswith(b'http://'):
            # Absolute URL
            url_rest = url_path[7:]
            slash = url_rest.find(b'/')
            host = url_rest[:slash] if slash > 0 else url_rest
        else:
            for line in request.split(b'\r\n'):
                if line.lower().startswith(b'host:'):
                    host = line[5:].strip()
                    break
        
        is_target = any(t in host for t in TARGET_HOSTS)
        
        if method == b'CONNECT':
            # Tunnel HTTPS - extract host:port
            host_port = url_path
            if b':' in host_port:
                h, p = host_port.split(b':')
                port = int(p)
                hostname = h.decode()
            else:
                hostname = host_port.decode()
                port = 443
            
            try:
                remote = socket.create_connection((hostname, port), timeout=10)
                client_sock.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                
                # Bidirectional relay
                def relay(src, dst):
                    try:
                        while True:
                            r, _, _ = select.select([src], [], [], 30)
                            if not r: break
                            data = src.recv(8192)
                            if not data: break
                            dst.sendall(data)
                    except:
                        pass
                
                t1 = threading.Thread(target=relay, args=(client_sock, remote), daemon=True)
                t2 = threading.Thread(target=relay, args=(remote, client_sock), daemon=True)
                t1.start(); t2.start()
                t1.join(timeout=60)
            except Exception as e:
                client_sock.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
        elif is_target:
            print(f"[FAKED] {host.decode()} {method.decode()}")
            client_sock.sendall(FAKE_RESPONSE)
        else:
            # Forward HTTP
            try:
                port = 80
                hostname = host.decode()
                if b':' in host:
                    h, p = host.split(b':')
                    hostname = h.decode()
                    port = int(p)
                
                remote = socket.create_connection((hostname, port), timeout=10)
                remote.sendall(request)
                
                # Relay response
                while True:
                    data = remote.recv(8192)
                    if not data: break
                    client_sock.sendall(data)
                remote.close()
            except:
                client_sock.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
    except:
        pass
    finally:
        try:
            client_sock.close()
        except:
            pass

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(50)
    print(f"代理运行在 0.0.0.0:{port}")
    print("手机 WiFi 代理设为此地址")
    print(f"拦截目标: {', '.join(t.decode() for t in TARGET_HOSTS)}")
    try:
        while True:
            client, addr = server.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n停止")

if __name__ == '__main__':
    main()
