#!/usr/bin/env python3
# -*- coding: ascii -*-

import sys, os, time
import argparse
import urllib.parse, urllib.request, urllib.error

from main import VALID_UPLOAD

DEFAULT_URL = 'https://31337.leet.nu/data'

def resolve_color(param, stream=None):
    if isinstance(param, str):
        param = {'never': False, 'always': True, 'auto': None}[param.lower()]
    if param is None:
        if os.environ.get('NO_COLOR'):
            return False
        if stream is not None and stream.isatty():
            return True
        return False
    return bool(param)

def request(url, post=None):
    try:
        with urllib.request.urlopen(url, data=post) as resp:
            body = resp.read()
            return resp.status, body.decode('utf-8')
    except urllib.error.HTTPError as exc:
        return exc.status, exc.fp.read().decode('utf-8')

def format_timestamp(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S Z', time.gmtime(ts))

def format_text(text, note, color=False):
    if text is None:
        return '\033[1;31m--/--\033[0m' if color else '--/--'
    elif not color:
        return text
    elif note is None:
        return text

    if note == 'sync word':
        highlight = '2'
    elif note.startswith('repeated'):
        highlight = '32'
    else:
        highlight = '1'
    return f'\033[{highlight}m{text}\033[0m'

def track(base_url):
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
        elif not data.isdigit():
            note = 'letters'
        elif data.count(data[0]) == len(data):
            note = 'repeated ' + data[0]
        else:
            note = None
        yield (ts, data, note)
        time.sleep(max(ts + 4 - time.time(), 0))
        ts += 5

def do_track(base_url, stream, color=False):
    color = resolve_color(color, stream)
    for ts, text, note in track(base_url):
        ts_text = format_timestamp(ts)
        ts_text = f'\033[2m{ts_text} ->\033[0m' if color else ts_text + ' ->'
        formatted_text = format_text(text, note, color=color)
        if not note:
            note_text = ''
        elif color:
            note_text = f' \033[36m[{note}]\033[0m'
        else:
            note_text = f' [{note}]'

        line = f'{ts_text} {formatted_text}{note_text}'
        print(line, file=stream)

def do_upload(url, text):
    if not VALID_UPLOAD.match(text):
        raise ValueError('Invalid upload text')
    body = urllib.parse.urlencode({'d': text}).encode('utf-8')
    return request(url, body)

def main():
    p = argparse.ArgumentParser(description='Receive and print 31337 '
                                            'transmissions')
    p.add_argument('--url', '-u', default=DEFAULT_URL,
                   help='API URL (default: %(default)s)')
    p.add_argument('--color', choices=('never', 'always', 'auto'),
                   default='auto',
                   help='Decide whether to color-code output')
    p.add_argument('submit', nargs='?',
                   help='Upload text instead of retrieving updates')
    a = p.parse_args()

    if a.submit is not None:
        code, body = do_upload(a.url, a.submit.upper())
        if code == 200:
            print('OK')
        else:
            print(f'ERROR {code}: {body}')
    else:
        do_track(a.url, sys.stdout, color=a.color)

if __name__ == '__main__': main()
