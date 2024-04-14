#!/usr/bin/env python3
# -*- coding: ascii -*-

import sys, os, time
import argparse
import datetime
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

def highlight(text, hlcode, color=True):
    return f'\033[{hlcode}m{text}\033[0m' if color else text

def format_timestamp(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S Z', time.gmtime(ts))

def format_text(text, note, color=False):
    if text is None:
        return highlight('--/--', '1;31', color)
    elif not color or note is None:
        return text

    if note == 'sync word':
        hlcode = '34'
    elif note == 'wat?!':
        hlcode = '1;33'
    elif note.startswith('repeated'):
        hlcode = '32'
    else:
        hlcode = '1'
    return highlight(text, hlcode)

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
        ts_text = highlight(f'{format_timestamp(ts)} ->', '2', color)
        formatted_text = format_text(text, note, color=color)
        note_text = ' ' + highlight(f'[{note}]', '36', color) if note else ''
        line = f'{ts_text} {formatted_text}{note_text}'
        print(line, file=stream)

def do_track_fancy(base_url, stream, color=False):
    color = resolve_color(color, stream)

    heading = ('#      '  +
               ' '.join(f' :{i:02} ' for i in range(0, 60, 5))).rstrip()
    print(highlight(heading, '2', color), file=stream)

    prev_date, prev_time, prev_second = None, None, None
    for ts, text, note in track(base_url):
        dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        cur_date = dt.date()
        cur_time = (dt.hour, dt.minute)
        cur_second = dt.second

        if cur_date != prev_date:
            print(highlight(f'{dt:%Y-%m-%d}:', '35', color), file=stream)
            prev_date = cur_date
        if cur_time != prev_time:
            print(highlight(f'{dt:%H:%M}:', '2;35', color), end='',
                  file=stream)
            prev_time = cur_time
            prev_second = -5

        if prev_second != cur_second - 5:
            print('      ' * ((cur_second - prev_second) // 5 - 1), end='',
                  file=stream)
        formatted_text = format_text(text, note, color=color)
        print(' ' + formatted_text, end=('\n' if cur_second == 55 else ''),
              file=stream, flush=True)
        prev_second = cur_second

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
    p.add_argument('--compact', '-c', action='store_true',
                   help='Display tracking output in a compact human-readable '
                        'manner')
    p.add_argument('submit', nargs='?',
                   help='Upload text instead of retrieving updates')
    a = p.parse_args()

    if a.submit is not None:
        code, body = do_upload(a.url, a.submit.upper())
        if code == 200:
            print('OK')
        else:
            print(f'ERROR {code}: {body}')
    elif a.compact:
        try:
            do_track_fancy(a.url, sys.stdout, color=a.color)
        except KeyboardInterrupt:
            print()
    else:
        do_track(a.url, sys.stdout, color=a.color)

if __name__ == '__main__': main()
