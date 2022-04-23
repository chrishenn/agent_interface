from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import Application, url

import os

import handlers






define("url", default='localhost', help="run on this url", type=str)
define("port", default=8888, help="run on the given port", type=int)

define("M_SEP", default=b';-MSEP-;', type=bytes)



def make_app():
    app = Application(
        handlers=[
            (r'/', handlers.BaseView),

            (r'/mouse/report', handlers.MouseClientReporter),
            (r'/mouse/move', handlers.MouseMoveHandler),
            (r'/mouse/click', handlers.MouseClickHandler),

            (r'/key/update', handlers.KeyHandler),

            url(r'/state/update', handlers.SendUpdatedState, name="get_frames"),
            (r'/state/add', handlers.StateAdd),
            (r'/state/rm', handlers.StateRm),
        ],

        template_path=os.path.join(os.path.dirname(__file__), 'templates'),
        static_path=os.path.join(os.path.dirname(__file__), 'static'),

        compiled_template_cache=False,
        # debug=True,
        debug=False,
        autoreload=False,
    )
    return app



def run_server():
    parse_command_line()

    app = make_app()
    http_server = HTTPServer(app)
    http_server.listen(options.port)
    print('Listening on http://localhost:%i' % options.port)
    IOLoop.current().start()

def run_server_multi():
    app = make_app()
    server = HTTPServer(app)
    # server.bind(options.port)
    server.listen(options.port)
    server.start(num_processes=2)
    IOLoop.current().start()


if __name__ == "__main__":
    run_server()
    # run_server_multi()


