"""Explicitly guarded JOB v1 acceptance. Never discovers unrelated live tests."""
import os
os.environ['MYSQL_DATABASE']='opspilot_test'
os.environ['OPSPILOT_EXPECTED_DATABASE']='opspilot_test'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
import sys
sys.dont_write_bytecode=True
import runpy
import unittest
from pathlib import Path
from db import get_connection

def main():
    c=get_connection()
    try:
        with c.cursor() as s:
            s.execute('SELECT DATABASE() AS db')
            if s.fetchone()['db'] != 'opspilot_test': raise RuntimeError('Wrong DB')
        print('[SAFETY] current_database=opspilot_test')
    finally: c.close()
    root=Path(__file__).resolve().parent
    suite=unittest.defaultTestLoader.discover(str(root),pattern='test_job_runtime.py')
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    for name in ('test_job_e2e_8d.py','test_job_e2e_9.py','test_job_e2e_9a.py','test_job_e2e_10c.py','test_job_e2e_10d.py','test_job_e2e_10e.py','test_job_e2e_10f.py','test_job_e2e_12a.py'):
        runpy.run_path(str(root/name),run_name='__main__')
    print('[TEST] ALL PASS: JOB v1 acceptance')
if __name__=='__main__': main()
