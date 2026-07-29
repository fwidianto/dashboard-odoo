import asyncio
import json
from urllib.parse import urlsplit

from src.api import DASHBOARD_SESSION_COOKIE, app
from src.control_tower.router import service_dependency
from src.dashboard_auth import sign_dashboard_session


async def asgi_get(path, cookies=None):
    parsed = urlsplit(path)
    response = {'status': None, 'body': bytearray()}
    headers = []
    if cookies:
        headers.append((b'cookie', '; '.join(f'{key}={value}' for key, value in cookies.items()).encode()))

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(message):
        if message['type'] == 'http.response.start':
            response['status'] = message['status']
        elif message['type'] == 'http.response.body':
            response['body'].extend(message.get('body', b''))

    await app(
        {
            'type': 'http',
            'asgi': {'version': '3.0'},
            'http_version': '1.1',
            'method': 'GET',
            'scheme': 'http',
            'path': parsed.path,
            'raw_path': parsed.path.encode(),
            'query_string': parsed.query.encode(),
            'headers': headers,
            'server': ('testserver', 80),
            'client': ('testclient', 50000),
            'root_path': '',
        },
        receive,
        send,
    )
    return response['status'], bytes(response['body'])


class StubControlTowerService:
    def findings(self, **kwargs):
        return {'rows': [], 'total': 0, 'limit': kwargs.get('limit', 200), 'offset': kwargs.get('offset', 0)}

    def evidence(self, **kwargs):
        return {
            'rows': [],
            'total': 0,
            'limit': kwargs.get('limit', 200),
            'offset': kwargs.get('offset', 0),
            'presentation_category': kwargs.get('presentation_category'),
            'category_counts': {
                'MASALAH_AKTIF': 0,
                'PERLU_DITINJAU': 0,
                'DATA_BELUM_LENGKAP': 0,
            },
        }

    def health(self):
        return {'status': 'ok'}


def test_control_tower_routes_are_registered_and_authenticated():
    paths = app.openapi()['paths']
    assert '/api/control-tower/findings' in paths
    assert '/api/control-tower/evidence' in paths
    assert '/api/control-tower/health' in paths

    app.dependency_overrides[service_dependency] = lambda: StubControlTowerService()
    try:
        unauthenticated_status, _ = asyncio.run(asgi_get('/api/control-tower/findings'))
        assert unauthenticated_status == 401

        session = sign_dashboard_session({'dashboard_authenticated': True, 'dashboard_username': 'test'})
        authenticated_status, authenticated_body = asyncio.run(asgi_get(
            '/api/control-tower/findings?affected_model=sale.order&category=DATA_BELUM_LENGKAP&rule_code=DH2-SALES-001',
            cookies={DASHBOARD_SESSION_COOKIE: session},
        ))
        assert authenticated_status == 200
        assert json.loads(authenticated_body)['total'] == 0

        evidence_status, evidence_body = asyncio.run(asgi_get(
            '/api/control-tower/evidence?presentation_category=PERLU_DITINJAU&limit=2&offset=4',
            cookies={DASHBOARD_SESSION_COOKIE: session},
        ))
        assert evidence_status == 200
        evidence_payload = json.loads(evidence_body)
        assert evidence_payload['presentation_category'] == 'PERLU_DITINJAU'
        assert evidence_payload['limit'] == 2
        assert evidence_payload['offset'] == 4

        health_status, health_body = asyncio.run(asgi_get(
            '/api/control-tower/health',
            cookies={DASHBOARD_SESSION_COOKIE: session},
        ))
        assert health_status == 200
        assert json.loads(health_body)['status'] == 'ok'
    finally:
        app.dependency_overrides.pop(service_dependency, None)
