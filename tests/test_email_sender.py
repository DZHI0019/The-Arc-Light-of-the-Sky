import pytest
import smtplib
from email_sender import EmailSender

class DummySMTP:
    def __init__(self, *args, **kwargs):
        pass
    def starttls(self):
        pass
    def login(self, user, pwd):
        pass
    def sendmail(self, frm, to, msg):
        return {}
    def quit(self):
        pass

class DummySMTPSSL(DummySMTP):
    pass

def test_send_email_starttls(monkeypatch):
    sent = {}
    def fake_smtp(*args, **kwargs):
        return DummySMTP()
    monkeypatch.setattr(smtplib, 'SMTP', fake_smtp)

    sender = EmailSender('smtp.test', 587, 'a@test', 'pwd', 'b@test', subject_prefix='x', use_ssl=False)
    ok = sender.send_email('s', 'b')
    assert ok is True


def test_send_email_ssl(monkeypatch):
    def fake_smtp_ssl(*args, **kwargs):
        return DummySMTPSSL()
    monkeypatch.setattr(smtplib, 'SMTP_SSL', fake_smtp_ssl)

    sender = EmailSender('smtp.test', 465, 'a@test', 'pwd', 'b@test', use_ssl=True)
    ok = sender.send_email('s', 'b')
    assert ok is True
