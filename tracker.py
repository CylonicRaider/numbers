#!/usr/bin/env python3
# -*- coding: ascii -*-

import time
import argparse
import urllib.parse, urllib.request

from main import VALID_UPLOAD

DEFAULT_URL = 'https://31337.leet.nu/data'

def request(url, post=None):
    with urllib.request.urlopen(url, data=post) as resp:
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
        status, body = request(url)
        if status != 200:
            yield (int(now), None, 'error: {}'.format(body))
            if ts is None:
                time.sleep(5)
            else:
                ts += 5
            continue
        body_params = urllib.parse.parse_qs(body)
        ts = int(body_params['t'][0])
        data = body_params['d'][0]
        if ts % 60 == 0:
            note = 'sync word' if data == '31337' else 'wat?!'
        elif data.count(data[0]) == len(data):
            note = 'repeated ' + data[0]
        elif not data.isdigit():
            note = 'letters'
        else:
            note = None
        yield (ts, data, note)
        time.sleep(max(ts + 4 - time.time(), 0))
        ts += 5

def do_upload(url, text):
    if not VALID_UPLOAD.match(text):
        raise ValueError('Invalid upload text')
    body = urllib.parse.urlencode({'d': text}).encode('utf-8')
    return request(url, body)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', '-u', default=DEFAULT_URL,
                   help='API URL (default: %(default)s)')
    p.add_argument('submit', nargs='?',
                   help='Upload text instead of retrieving updates')
    a = p.parse_args()

    if a.submit is not None:
        code, body = do_upload(a.url, a.submit)
        if code == 200:
            print('OK')
        else:
            print(f'ERROR {code}: {body}')
    else:
        for ts, text, note in do_track(a.url):
            line = f'{format_time(ts)} -> {"--/--" if text is None else text}'
            if note: line += f' [{note}]'
            print(line)

if __name__ == '__main__': main()
