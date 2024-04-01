
# -*- coding: ascii -*-

import os, io
import calendar
import urllib.parse
import email.utils
import posixpath
import wsgiref.util

try:
    from http import HTTPStatus as _HTTPStatus
    def http_phrase(code):
        return _HTTPStatus(code).phrase
except ImportError:
    from http.client import responses as _http_responses
    def http_phrase(code):
        return _http_responses[code]

MIME_TYPES = {
    '.txt': 'text/plain; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.ico': 'image/vnd.microsoft.icon'
}

def parse_http_date(string):
    fields = email.utils.parsedate(string)
    return calendar.timegm(fields)

def format_http_date(timestamp):
    return email.utils.formatdate(timestamp, usegmt=True)

def parse_cookies(string):
    ret = {}
    for item in string.split(';'):
        n, s, v = item.partition('=')
        if s:
            ret[n.strip()] = v.strip()
        else:
            ret[''] = n.strip()
    return ret

def format_cookie(name, value, attrs):
    ret = [name, '=', value]
    for k, v in attrs.items():
        if k.lower() == 'expires' and isinstance(v, (int, float)):
            v = format_http_date(v)
        elif k.lower() == 'path' and v is not None:
            v = urllib.parse.quote(v)
        ret.extend(('; ', k))
        if v is not None: ret.extend(('=', v))
    return ''.join(ret)

def make_relative(path):
    ret = posixpath.relpath(posixpath.join('/', path), '/')
    if ret == '.': ret = ''
    return ret

def join_paths(base, subpath):
    return posixpath.join(base, make_relative(subpath))

class InputWrapper(io.RawIOBase):
    def __init__(self, wrapped, remaining=None):
        self.wrapped = wrapped
        self.remaining = remaining

    def readable(self):
        return True

    def read(self, size=-1):
        if self.remaining is None:
            return self.wrapped.read(size)
        elif self.remaining == 0:
            return b''
        else:
            if size == -1: size = self.remaining
            rd = self.wrapped.read(min(size, self.remaining))
            if rd is not None: self.remaining -= len(rd)
            return rd

    def readinto(self, buf):
        rd = self.read(len(buf))
        if rd is None: return None
        buf[:len(rd)] = rd
        return len(rd)

class ApplicationWrapper:
    factory = None
    static_root = None

    @classmethod
    def create(cls, factory, **kwds):
        kwds['factory'] = staticmethod(factory)
        return type('<anonymous:%s>' % cls.__name__, (cls,), kwds)

    def __init__(self, environ, start_response):
        self.parent = None
        self.environ = environ
        self.start_response = start_response
        self.script_name = environ.get('SCRIPT_NAME', '')
        self.route = ''
        self.path = environ.get('PATH_INFO', '')
        self.query = environ.get('QUERY_STRING', '')
        self.app = self.factory(self)
        self.response = iter(self.app)

    def __iter__(self):
        return self.response

class Application:
    def __init__(self, parent):
        self.parent = parent
        self.environ = parent.environ
        self._start_response = parent.start_response
        self.method = self.environ['REQUEST_METHOD']
        self.script_name = parent.script_name
        self.route = parent.route
        self.path = parent.path
        self.query = parent.query
        self._req_cookies = None
        self.response_cookies = []
        self.response_headers = []
        self._query_vars = None
        self._req_body = None

    def __iter__(self):
        return iter(self.process())

    def start_response(self, status, response_headers, exc_info=None):
        # Inject cookies into response, and ensure they are not silently
        # dropped thereafter.
        for n, v, a in self.response_cookies:
            response_headers.append(('Set-Cookie', format_cookie(n, v, a)))
        response_headers.extend(self.response_headers)
        self.response_cookies = None
        if exc_info is None:
            return self._start_response(status, response_headers)
        else:
            return self._start_response(status, response_headers, exc_info)

    def process(self):
        raise NotImplementedError

    @property
    def request_cookies(self):
        if self._req_cookies is None:
            self._req_cookies = parse_cookies(
                self.environ.get('HTTP_COOKIE', ''))
        return self._req_cookies

    @property
    def query_vars(self):
        if self._query_vars is None:
            pairs = urllib.parse.parse_qs(self.query)
            self._query_vars = {k: v[-1] for k, v in pairs.items()}
        return self._query_vars

    @property
    def request_body(self):
        if self._req_body is None:
            try:
                cl = int(self.environ.get('CONTENT_LENGTH', ''))
            except ValueError:
                cl = None
            self._req_body = InputWrapper(self.environ['wsgi.input'], cl)
        return self._req_body

    def add_cookie(self, name, value, **attrs):
        self.response_cookies.append((name, value, attrs))

    def add_header(self, name, value):
        self.response_headers.append((name, value))

    def send_code(self, code, text=None, content_type=None):
        if isinstance(text, str): text = text.encode('utf-8')
        if content_type is None: content_type = 'text/plain; charset=utf-8'
        status_line = '%s %s' % (code, http_phrase(code))
        if text is None: text = status_line.encode('utf-8')
        self.start_response(status_line, [
            ('Content-Type', content_type),
            ('Content-Length', str(len(text)))
        ])
        return [text]

    def send_redirect(self, code, url):
        self.start_response('%s %s' % (code, http_phrase(code)), [
            ('Location', url),
            ('Content-Length', '0')
        ])
        return []

    @property
    def static_root(self):
        return self.parent.static_root

    def open_static(self, path, mime_types=None):
        if mime_types is None: mime_types = MIME_TYPES
        info, headers = {}, []
        ext = posixpath.splitext(path)[1]
        try:
            info['mime'] = mime_types[ext]
            headers.append(('Content-Type', info['mime']))
        except KeyError:
            pass
        try:
            fp = open(join_paths(self.static_root, path), 'rb')
        except IOError:
            return (None, None, None)
        try:
            status = os.fstat(fp.fileno())
            info['length'] = status.st_size
            info['mtime'] = int(status.st_mtime)
            headers.append(('Content-Length', str(info['length'])))
            headers.append(('Last-Modified', format_http_date(info['mtime'])))
        except Exception:
            pass
        return (fp, info, headers)

    def send_static(self, filelike, blksize=None, mime_types=None):
        headers, last_modified = [], None
        if isinstance(filelike, str):
            # File is closed by the server.
            filelike, info, headers = self.open_static(filelike, mime_types)
            if filelike is None:
                return self.send_code(404)
            last_modified = info.get('mtime')
        if last_modified is not None:
            value = self.environ.get('HTTP_IF_MODIFIED_SINCE')
            if value:
                try:
                    pvalue = parse_http_date(value)
                except ValueError:
                    pass
                else:
                    if last_modified <= pvalue:
                        self.start_response('304 Not Modified', headers)
                        return []
        self.start_response('200 OK', headers)
        wrapper = self.environ.get('wsgi.file_wrapper',
                                   wsgiref.util.FileWrapper)
        if blksize is None:
            return wrapper(filelike)
        else:
            return wrapper(filelike, blksize)

    def _export(self, path, route, base, join):
        if route and self.route:
            if not base.endswith('/'): base += '/'
            base = join(base, make_relative(self.route))
        if path:
            if not base.endswith('/'): base += '/'
            return join(base, make_relative(path))
        else:
            return base

    def export_path(self, path, route=False):
        return self._export(path, route, self.environ.get('SCRIPT_NAME', ''),
                            posixpath.join)

    def export_url(self, url, route=False):
        return self._export(url, route,
                            wsgiref.util.application_uri(self.environ),
                            urllib.parse.urljoin)

class FixedApplication(Application):
    code = None
    location = None
    text = None
    content_type = None

    @classmethod
    def create(cls, code, **kwds):
        kwds['code'] = code
        return type('<anonymous:%s>' % cls.__name__, (cls,), kwds)

    def process(self):
        if self.location is not None:
            return self.send_redirect(self.code, self.location)
        else:
            return self.send_code(self.code, self.text,
                                  self.content_type)

class StaticApplication(Application):
    subroot = None
    strip_prefix = None
    blksize = None
    mime_types = None

    @classmethod
    def create(cls, subroot=None, **kwds):
        if subroot is None: subroot = ''
        kwds.update(subroot=subroot)
        return type('<anonymous:%s>' % cls.__name__, (cls,), kwds)

    @property
    def static_root(self):
        return posixpath.join(self.parent.static_root, self.subroot)

    def process(self):
        path = self.path if self.strip_prefix else self.route + self.path
        return self.send_static(path, self.blksize, self.mime_types)

class WSGIApplication(Application):
    wrapped = None

    @classmethod
    def wrap(cls, wrapped, **kwds):
        kwds['wrapped'] = staticmethod(wrapped)
        return type('<anonymous:%s>' % cls.__name__, (cls,), kwds)

    def process(self):
        self.environ['SCRIPT_NAME'] = self.script_name + self.route
        return self.wrapped(self.environ, self.start_response)

class Router(Application):
    routes = None
    fallback = None

    @classmethod
    def create(cls, routes, fallback, **kwds):
        kwds.update(routes=routes, fallback=fallback)
        return type('<anonymous:%s>' % cls.__name__, (cls,), kwds)

    def process(self):
        path = self.path
        for routepath, extend, method, callback in self.routes:
            if method is not None and self.method != method:
                continue
            elif not extend:
                if path != routepath: continue
            elif not path.startswith(routepath):
                continue
            elif not routepath.endswith('/'):
                lrp = len(routepath)
                if len(path) > lrp and path[lrp] != '/': continue
            return self._process_route(routepath, callback)
        return self._process_fallback()

    def _process_route(self, routepath, callback):
        if not self.path.startswith(routepath):
            raise RuntimeError('Invalid route key %r for PATH_INFO %r' %
                               (key, self.path))
        truncpath = routepath[:-1] if routepath.endswith('/') else routepath
        self.route += truncpath
        self.path = self.path[len(truncpath):]
        return callback(self)

    def _process_fallback(self):
        return self.fallback(self)

class RouteBuilder:
    def __init__(self):
        self.routes = []
        self.fallback_route = None

    def add(self, path, handler, method='GET'):
        if path.endswith('/*'):
            ent = (path[:-1], True, method, handler)
        elif path.endswith('*'):
            raise ValueError('Invalid route path: ' + path)
        else:
            ent = (path, False, method, handler)
        self.routes.append(ent)

    def fallback(self, handler):
        self.fallback_route = handler

    def fixed(self, code, **kwds):
        return FixedApplication.create(code, **kwds)

    def static(self, subroot=None, **kwds):
        return StaticApplication.create(subroot, **kwds)

    def wsgi(self, app, **kwds):
        return WSGIApplication.wrap(app, **kwds)

    def build(self, cls=None, **kwds):
        if cls is None: cls = Router
        return cls.create(self.routes, self.fallback_route, **kwds)

    def build_wsgi(self, cls=None, **kwds):
        ret = self.build(cls)
        return ApplicationWrapper.create(ret, **kwds)

    def __call__(self, path, handler=None, method='GET'):
        def callback(handler):
            self.add(path, handler, method)
            return handler
        if handler is not None:
            callback(handler)
        else:
            return callback

def run_app(app):
    import sys
    import wsgiref.simple_server
    import argparse
    # Parse arguments
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='',
                   help='The IP address to bind to (defaults to all '
                       'interfaces)')
    p.add_argument('--port', default=8080, type=int,
                   help='The port to bind to (default 8080)')
    res = p.parse_args()
    # Create server
    httpd = wsgiref.simple_server.make_server(res.host, res.port, app)
    # Print status message
    display_host = res.host if res.host else '*'
    sys.stderr.write('Serving HTTP on %s:%s...\n' % (display_host, res.port))
    # Main loop
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write('\n')
