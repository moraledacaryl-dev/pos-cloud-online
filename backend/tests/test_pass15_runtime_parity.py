from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding='utf-8')


def test_supported_container_runtimes_match_ci_and_live_ports():
    frontend = read('frontend/Dockerfile')
    backend = read('backend/Dockerfile')

    assert 'FROM node:24-alpine' in frontend
    assert frontend.count('node:24-alpine@sha256:') == 2
    assert 'EXPOSE 3100' in frontend
    assert '"3100"' in frontend

    assert 'FROM python:3.12-slim' in backend
    assert 'python:3.12-slim@sha256:' in backend
    assert 'requirements.lock' in backend
    assert 'requirements.txt' not in backend
    assert 'EXPOSE 8100' in backend
    assert '"8100"' in backend


def test_systemd_templates_use_the_same_canonical_units_as_production():
    systemd = REPO_ROOT / 'deploy' / 'systemd'
    expected = {
        'pos-backend.service',
        'pos-frontend.service',
        'pos-sync-worker.service',
    }
    present = {path.name for path in systemd.glob('*.service')}

    assert expected <= present
    assert not {name for name in present if name.startswith('hiddenoasis-pos-')}

    backend = read('deploy/systemd/pos-backend.service')
    frontend = read('deploy/systemd/pos-frontend.service')
    worker = read('deploy/systemd/pos-sync-worker.service')

    assert '--port 8100' in backend
    assert 'redis-server.service' in backend
    assert '-p 3100' in frontend
    assert 'pos-backend.service' in frontend
    assert 'redis-server.service' in worker
    assert 'pos-backend.service' in worker

    for unit in (backend, frontend, worker):
        assert 'NoNewPrivileges=true' in unit
        assert 'PrivateTmp=true' in unit
        assert 'PrivateDevices=true' in unit
        assert 'ProtectHome=true' in unit
        assert 'ProtectSystem=strict' in unit
        assert 'ProtectKernelTunables=true' in unit
        assert 'ProtectKernelModules=true' in unit
        assert 'ProtectControlGroups=true' in unit
        assert 'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' in unit
        assert 'RestrictSUIDSGID=true' in unit
        assert 'LockPersonality=true' in unit
        assert 'CapabilityBoundingSet=' in unit
        assert 'AmbientCapabilities=' in unit
        assert 'UMask=0027' in unit
        assert 'TasksMax=' in unit
        assert 'LimitNOFILE=' in unit
        assert 'MemoryMax=' in unit

    assert 'ReadWritePaths=/opt/pos-cloud-online/frontend/.next/cache' in frontend


def test_frontend_sample_and_csp_match_supported_production_runtime():
    frontend_env = read('frontend/.env.production.example')
    next_config = read('frontend/next.config.js')
    proxy = read('frontend/proxy.js')

    assert 'PORT=3100' in frontend_env
    assert "'unsafe-inline'" not in next_config
    assert 'Content-Security-Policy' not in next_config
    assert "script-src 'self' 'nonce-${nonce}' 'strict-dynamic'" in proxy
    assert "style-src 'self' 'unsafe-inline'" in proxy
    assert "script-src 'self' 'unsafe-inline'" not in proxy
    assert "script-src 'self' 'unsafe-inline'" not in proxy


def test_container_parity_workflow_builds_and_starts_both_images():
    workflow = read('.github/workflows/container-parity-ci.yml')

    assert 'docker build -t hiddenoasis-pos-backend:ci backend' in workflow
    assert 'docker build -t hiddenoasis-pos-frontend:ci frontend' in workflow
    assert 'http://127.0.0.1:18100/healthz' in workflow
    assert 'http://127.0.0.1:13100/login' in workflow
    assert "grep 'Python 3.12'" in workflow
    assert "grep '^v24\\.'" in workflow
