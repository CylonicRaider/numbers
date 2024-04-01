#!/usr/bin/env python3
# -*- coding: ascii -*-

import os, inspect
import wsgif

THIS_DIR = os.path.abspath(os.path.dirname(inspect.getfile(lambda: None)))

route = wsgif.RouteBuilder()

@route('/')
def handle_root(app):
    return app.send_code(200, 'Hello World!')

route.fallback(route.fixed(404))

application = route.build_wsgi(static_root=os.path.join(THIS_DIR, 'www'))

if __name__ == '__main__': wsgif.run_app(application)
