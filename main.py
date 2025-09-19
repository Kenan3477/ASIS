from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from wsgiref.simple_server import make_server
from urllib.parse import parse_qs

# WSGI Application for Railway Nixpacks
def application(environ, start_response):
    path = environ['PATH_INFO']
    method = environ['REQUEST_METHOD']
    
    if method == 'GET':
        if path == '/':
            response_body = json.dumps({"message": "ASIS Research Platform", "status": "running"})
        elif path == '/health':
            response_body = json.dumps({"status": "healthy"})
        else:
            start_response('404 Not Found', [('Content-Type', 'application/json')])
            return [json.dumps({"error": "Not found"}).encode()]
    elif method == 'POST' and path == '/register':
        try:
            request_body_size = int(environ.get('CONTENT_LENGTH', 0))
            request_body = environ['wsgi.input'].read(request_body_size).decode('utf-8')
            data = json.loads(request_body)
            email = data.get('email', '')
            response_body = json.dumps({
                "message": "Registration successful",
                "email": email,
                "is_academic": email.endswith('.edu'),
                "discount": 50 if email.endswith('.edu') else 0
            })
        except:
            start_response('400 Bad Request', [('Content-Type', 'application/json')])
            return [json.dumps({"error": "Invalid JSON"}).encode()]
    else:
        start_response('404 Not Found', [('Content-Type', 'application/json')])
        return [json.dumps({"error": "Not found"}).encode()]
    
    start_response('200 OK', [
        ('Content-Type', 'application/json'),
        ('Access-Control-Allow-Origin', '*'),
        ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
        ('Access-Control-Allow-Headers', 'Content-Type')
    ])
    return [response_body.encode()]

# For gunicorn compatibility
app = application

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            response = {"message": "ASIS Research Platform", "status": "running"}
        elif self.path == '/health':
            response = {"status": "healthy"}
        else:
            self.send_response(404)
            self.end_headers()
            return
            
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def do_POST(self):
        if self.path == '/register':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                email = data.get('email', '')
                response = {
                    "message": "Registration successful",
                    "email": email,
                    "is_academic": email.endswith('.edu'),
                    "discount": 50 if email.endswith('.edu') else 0
                }
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server():
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f'ASIS server running on port {port}')
    print(f'Health check: http://0.0.0.0:{port}/health')
    server.serve_forever()

if __name__ == '__main__':
    run_server()
