from http.server import HTTPServer, BaseHTTPRequestHandler
import requests, os

class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            url = "http://localhost:9091/transmission/rpc"
            session_header = "X-Transmission-Session-Id"
            username = os.environ.get('USER')
            password = os.environ.get('PASS')

            response1 = requests.post(url, auth=(username, password))

            if 'X-Transmission-Session-Id' in response1.headers: 
                session_id = response1.headers['X-Transmission-Session-Id']
                response2 = requests.post(url, auth=(username, password), headers={session_header: session_id}) 
                self.send_response(response2.status_code)
                self.send_header("Content-type", response2.headers["Content-Type"])
                self.end_headers()
                self.wfile.write(response2.content)
            else: 
                self.send_error(401, 'Authentication failed')

def run_proxy(port=8000):
   server_address = ('', port)
   httpd = HTTPServer(server_address, ProxyHandler)
   print(f"Starting proxy server on port {port}")
   httpd.serve_forever()

if __name__ == "__main__":
   run_proxy()
