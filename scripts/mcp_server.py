#!/usr/bin/env python3
import sys, json, urllib.request

BASE = 'http://localhost:8000'

def post(path, data=None):
    body = json.dumps(data or {}).encode('utf-8')
    req = urllib.request.Request(f'{BASE}{path}', data=body,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(req).read())

def send(msg):
    sys.stdout.write(json.dumps(msg) + '\n')
    sys.stdout.flush()

pending = {}

while True:
    line = sys.stdin.readline()
    if not line:
        break
    msg = json.loads(line)
    mid = msg.get('id')
    method = msg.get('method', '')
    params = msg.get('params', {})

    if method == 'initialize':
        send({'jsonrpc': '2.0', 'id': mid, 'result': {
            'protocolVersion': '2024-11-05',
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'dialogmesh-mcp', 'version': '1.0.0'},
        }})
    elif method == 'notifications/initialized':
        continue
    elif method == 'tools/list':
        send({'jsonrpc': '2.0', 'id': mid, 'result': {
            'tools': [{
                'name': 'dialogmesh_query',
                'description': 'Send a query to DialogMesh agent. Creates sessions automatically.',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'query': {'type': 'string', 'description': 'User query text'},
                        'session_id': {'type': 'string', 'description': 'Optional existing session ID'},
                    },
                    'required': ['query'],
                },
            }]
        }})
    elif method == 'tools/call':
        name = params.get('name')
        args = params.get('arguments', {})
        if name == 'dialogmesh_query':
            query = args.get('query', '')
            sid = args.get('session_id')
            try:
                if not sid:
                    r = post('/v3/session')
                    sid = r['session_id']
                r = post(f'/v3/session/{sid}/message', {'content': query})
                content = r.get('content') or r.get('answer') or ''
                intent = r.get('intent')
                latency = r.get('latency_ms', 0)
                send({'jsonrpc': '2.0', 'id': mid, 'result': {
                    'content': [{'type': 'text', 'text': content}],
                    'meta': {'session_id': sid, 'intent': intent, 'latency_ms': latency},
                }})
            except Exception as e:
                send({'jsonrpc': '2.0', 'id': mid, 'error': {
                    'code': -32000, 'message': str(e),
                }})
        else:
            send({'jsonrpc': '2.0', 'id': mid, 'error': {
                'code': -32601, 'message': f'Unknown tool: {name}',
            }})
    elif method.startswith('notifications/'):
        continue
    else:
        if mid:
            send({'jsonrpc': '2.0', 'id': mid, 'result': {}})
