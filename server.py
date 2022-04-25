import concurrent.futures
import functools
import signal
import time

import psutil
import torch.multiprocessing as mp

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import Application, url
from tornado import log
from tornado.process import task_id

import os

import server_handlers




def make_app(shared_obj):

    app = Application(
        url='localhost',

        handlers=[
            (r'/', handlers.BaseView, dict(shared_obj=shared_obj)),

            (r'/mouse/move', handlers.MouseMoveHandler),
            (r'/mouse/click', handlers.MouseClickHandler),

            (r'/key/update', handlers.KeyHandler),

            url(r'/state/update', handlers.SendUpdatedState, name="get_frames"),
        ],

        template_path=os.path.join(os.path.dirname(__file__), 'templates'),
        static_path=os.path.join(os.path.dirname(__file__), 'static'),

        compiled_template_cache=False,
        # debug=True,
        debug=False,
        autoreload=False,
    )
    return app


def run_server(shared_obj, n_srv_proc):

    exec = concurrent.futures.ProcessPoolExecutor(max_workers=n_srv_proc)
    ioloop = IOLoop.current()
    ioloop.set_default_executor(exec)

    port = 8888
    app = make_app(shared_obj)
    http_server = HTTPServer(app)
    http_server.listen(port)

    print('Listening on http://localhost:%i' % port)
    ioloop.start()




