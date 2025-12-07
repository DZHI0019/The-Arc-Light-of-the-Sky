import json
from datetime import datetime
import requests
from bilibili_checker import BilibiliChecker

class DummyResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.headers = {'Content-Type': 'application/json'}
    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.HTTPError()
    def json(self):
        return self._data


def test_get_user_info(monkeypatch):
    sample = {'code': 0, 'data': {'name': 'x', 'face': 'f'}}
    def fake_get(url, timeout=None, params=None):
        return DummyResp(sample)
    checker = BilibiliChecker()
    monkeypatch.setattr(checker.session, 'get', fake_get)
    user = checker.get_user_info('1')
    assert user is not None


def test_get_user_dynamics_and_parse(monkeypatch):
    dynamics = {'code':0, 'data': {'items':[{'pub_ts': 1600000000}]}}
    user_info = {'code':0, 'data': {'name':'testuser', 'face':'f'}}
    def fake_get(url, params=None, timeout=None):
        if 'acc/info' in url:
            return DummyResp(user_info)
        return DummyResp(dynamics)
    checker = BilibiliChecker()
    monkeypatch.setattr(checker.session, 'get', fake_get)
    res = checker.get_user_dynamics('1')
    assert res is not None
    assert res['count'] == 1
    ok, last_time, info = checker.check_user_activity('1')
    assert ok is True
