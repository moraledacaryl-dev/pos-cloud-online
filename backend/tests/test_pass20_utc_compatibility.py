from pathlib import Path


def test_application_code_has_no_deprecated_datetime_utcnow_calls():
    app_root = Path(__file__).resolve().parents[1] / 'app'
    offenders = []
    for path in app_root.rglob('*.py'):
        if 'datetime.utcnow(' in path.read_text():
            offenders.append(str(path.relative_to(app_root)))
    assert not offenders, f'deprecated datetime.utcnow() remains in: {offenders}'
