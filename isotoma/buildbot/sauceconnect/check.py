#! /usr/bin/env python
import sys
import os
import time
from datetime import datetime, timedelta


timeout_limit = datetime.now() + timedelta(seconds = 60 * 5)

readyfile = os.path.join(os.path.dirname(__file__), 'sauce_tunnel.ready')

while True:
    if datetime.now() > timeout_limit:
        print "Timeout exceeded, stopping"
        print "SSH Tunnel didn't start in time"
        sys.exit(1)
    if os.path.exists(readyfile):
        sys.exit(0)

    time.sleep(10)

