#!/usr/bin/env python3
# -*- coding: ascii -*-

import os, re, time, inspect
import collections
import random
import threading
import urllib.parse
import wsgif

THIS_DIR = os.path.abspath(os.path.dirname(inspect.getfile(lambda: None)))

VALID_UPLOAD = re.compile(r'\A\s*[0-9A-Z]{5}(\s+[0-9A-Z]{5}){,10}\s*\Z')

RANDOM = random.SystemRandom()

class NumberQueue:
    def __init__(self):
        self.queued = {}
        self.queued_range = None

    def _available_indices(self, idx):
        while 1:
            if not idx % 60 or idx in self.queued:
                idx += 5
                continue
            for offset in range(1, 12):
                si = idx + 5 * offset
                if si % 60 and si not in self.queued: continue
                yield (idx, offset)
                break
            idx = si + 5

    def _update_range(self, add_range):
        if self.queued_range is None:
            self.queued_range = add_range
        else:
            self.queued_range = [min(self.queued_range[0], add_range[0]),
                                 max(self.queued_range[1], add_range[1])]

    def add(self, values, start_idx):
        assert len(values) <= 11
        for idx, count in self._available_indices(start_idx):
            if count < len(values): continue
            for offset, v in enumerate(values):
                self.queued[idx + 5 * offset] = v
            self._update_range([idx, idx + 5 * len(values)])
            break

    def pop(self, idx):
        if self.queued_range is None:
            return None

        if idx >= self.queued_range[1]:
            self.queued.clear()
            self.queued_range = None
        elif idx > self.queued_range[0]:
            for idx in range(self.queued_range[0], idx, 5):
                self.queued.pop(idx, None)
            self.queued_range[0] = idx + 5
        else:
            self.queued_range[0] = max(self.queued_range[0],
                                       idx + 5)

        return self.queued.pop(idx, None)

class NumberSupply:
    def __init__(self):
        self.current = [None, None, None, None]
        self.queue = NumberQueue()
        self.lock = threading.RLock()

    def generate_value(self, index):
        if index % 60 == 0:
            return '31337'
        v = self.queue.pop(index)
        if v is None:
            v = format(RANDOM.randrange(100000), '05')
        return v

    def update_values(self, now):
        next_index = int((now + 2) / 5) * 5
        if self.current[0] == next_index - 10:
            self.current[0] += 5
            self.current[1] = self.current[2]
            self.current[2] = self.generate_value(next_index)
        elif self.current[0] is None or self.current[0] < next_index - 10:
            self.current[0] = next_index - 5
            self.current[1] = self.generate_value(next_index - 5)
            self.current[2] = self.generate_value(next_index)
        else:
            return
        self.current[3] = self.current[0] + 8

    def add_values(self, values, now=None):
        with self.lock:
            if now is None: now = time.time()
            self.update_values(now)
            self.queue.add(values, self.current[0] + 10)

    def get_value(self, index, now=None):
        with self.lock:
            if now is None:
                now = time.time()
            if self.current[3] is None or now >= self.current[3]:
                self.update_values(now)
            current = tuple(self.current)

        base_index = current[0]
        if index == base_index:
            return {'code': 200,
                    'data': {'t': base_index, 'd': current[1]},
                    'expires': base_index + 8}
        elif index == base_index + 5:
            return {'code': 200,
                    'data': {'t': base_index + 5, 'd': current[2]},
                    'expires': base_index + 13}
        elif index % 5 != 0:
            return {'code': 404,
                    'text': '404 Not Found',
                    'expires': max(index, now) + 3600}
        elif index < base_index:
            return {'code': 410,
                    'text': '410 Gone',
                    'expires': max(index, now) + 3600}
        else:
            return {'code': 404,
                    'text': '404 Not Found',
                    'expires': index - 2}

THE_NUMBERS = NumberSupply()

route = wsgif.RouteBuilder()

@route('/')
def handle_root(app):
    return app.send_static('/index.html')

@route('/data')
def handle_data(app):
    raw_index = app.query_vars.get('t')
    now = time.time()
    if not raw_index:
        raw_index = int(now / 5) * 5
    try:
        index = int(raw_index)
    except ValueError:
        return app.send_code(400, '400 Bad Request')
    result = THE_NUMBERS.get_value(index, now=now)
    max_age = max(int(result['expires'] - now), 0)
    app.add_header('Cache-Control', 'max-age={}'.format(max_age))
    if result['code'] == 200:
        body = urllib.parse.urlencode(result['data'])
        return app.send_code(result['code'], body,
                             content_type='application/x-www-form-urlencoded')
    else:
        return app.send_code(result['code'], result['text'])

@route('/data', method='POST')
def handle_data_post(app):
    body = app.request_body.read(128)
    if len(body) >= 128:
        return app.send_code(400, '400 Bad Request')
    raw_fields = urllib.parse.parse_qs(body.decode('utf-8', errors='replace'))
    fields = {k: v[-1] for k, v in raw_fields.items()}
    m = VALID_UPLOAD.match(fields.get('d', ''))
    if not m:
        return app.send_code(400, '400 Bad Request')
    THE_NUMBERS.add_values(m.group(0).split())
    return app.send_code(200, '200 OK')

@route('/*')
def handle_statics(app):
    return app.send_static(app.path)

route.fallback(route.fixed(404))

application = route.build_wsgi(static_root=os.path.join(THIS_DIR, 'www'))

if __name__ == '__main__': wsgif.run_app(application)
