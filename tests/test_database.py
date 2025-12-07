import os
import tempfile
from datetime import datetime
from database import Database


def test_save_and_get_latest_check_record():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        db = Database(path)
        db.save_check_record('qq1', 'uid1', datetime.now(), datetime.now(), True, 0, 'ok')
        rec = db.get_latest_check_record('qq1', 'uid1')
        assert rec is not None
        assert rec['qq_number'] == 'qq1'
    finally:
        try:
            os.remove(path)
        except:
            pass
