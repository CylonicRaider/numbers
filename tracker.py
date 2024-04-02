#!/usr/bin/env python3
# -*- coding: ascii -*-

import time
import argparse
import urllib.parse, urllib.request

DEFAULT_URL = 'https://31337.leet.nu/data'

def get(url):
    with urllib.request.urlopen(url) as resp:
        body = resp.read()
        return resp.status, body.decode('utf-8')

def format_time(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S Z', time.gmtime(ts))

def do_track(base_url):
    ts = None
    while 1:
        now = time.time()
        if ts is not None:
            url = urllib.parse.urljoin(base_url, '?t=' + str(ts))
        else:
            url = base_url
        status, body = get(url)
        if status != 200:
            yield (int(now), '[Error: {}]'.format(body))
            if ts is None:
                time.sleep(5)
            else:
                ts += 5
            continue
        body_params = urllib.parse.parse_qs(body)
        ts = int(body_params['t'][0])
        data = body_params['d'][0]
        yield (ts, data)
        time.sleep(max(ts + 4 - time.time(), 0))
        ts += 5

def main():
    p = argparse.ArgumentParser()
    p.add_argument('url', nargs='?', default=DEFAULT_URL,
                   help='API URL (default: %(default)s)')
    a = p.parse_args()

    for ts, text in do_track(a.url):
        print(format_time(ts), '->', text)

if __name__ == '__main__': main()
