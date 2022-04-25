import functools
import cv2

from tornado.ioloop import IOLoop
from tornado.web import RequestHandler





class BaseView(RequestHandler):

    def initialize(self, shared_obj):
        BaseView.mouse_q, BaseView.key_q, BaseView.frame_q, BaseView.event_end = shared_obj
        BaseView.ioloop = IOLoop.current()
    
    def get(self):
        self.render('index.html')






def put_on_blocking_q(queue, value):
    try: queue.put_nowait(value)
    except Exception as e:
        print('MouseHandler: on queue.put_nowait, caught exception', type(e), ' : ', e)
        # print('raising', e)
        # raise e

def str2bool(str):
    if str == 'false': return False
    if str == 'true': return True

class MouseMoveHandler(RequestHandler):

    # /mouse/move POST
    async def post(self):

        x = int( self.request.arguments['x'][0].decode() )
        y = int( self.request.arguments['y'][0].decode() )

        vals = (x,y)
        await BaseView.ioloop.run_in_executor(None, functools.partial(put_on_blocking_q, BaseView.mouse_q, vals) )

class MouseClickHandler(RequestHandler):

    # /mouse/click POST
    async def post(self):

        button = int( self.request.arguments['button'][0].decode() )

        vals = (button,)
        await BaseView.ioloop.run_in_executor(None, functools.partial(put_on_blocking_q, BaseView.mouse_q, vals) )

class KeyHandler(RequestHandler):

    # /key/update POST
    async def post(self):

        shiftKey = str2bool( self.request.arguments['shiftKey'][0].decode() )
        ctrlKey = str2bool( self.request.arguments['ctrlKey'][0].decode() )
        altKey = str2bool( self.request.arguments['altKey'][0].decode() )
        Key = self.request.arguments['Key'][0].decode()

        vals = (Key, shiftKey, ctrlKey, altKey)
        await BaseView.ioloop.run_in_executor(None, functools.partial(put_on_blocking_q, BaseView.key_q, vals) )







def get_and_proc(frame_q):
    ## blocking get runs on aux thread
    try:
        frame = frame_q.get()
        success, blob = cv2.imencode('.jpg', frame)
        if success: message = bytes(blob)
        else: message = None
        return message
    except Exception as e:
        print('UpdatedStateHandler: on frame_q.get, caught exception', type(e), ' : ', e)
        # print('raising', e)
        # raise e

class SendUpdatedState(RequestHandler):

    # /state/update GET
    async def get(self):
        frame_bnd = "--framebnd"

        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0')
        self.set_header('Connection', 'close')
        self.set_header('Content-Type', 'multipart/x-mixed-replace;boundary=' + frame_bnd)
        self.set_header('Pragma', 'no-cache')
        self.write(frame_bnd + '\n')

        try:

            while True:
                message = await BaseView.ioloop.run_in_executor(None, functools.partial(get_and_proc, BaseView.frame_q))

                if message is not None and message is not False:
                    self.write("Content-type: image/jpeg\r\n")
                    self.write("Content-length: %s\r\n\r\n" % len(message))
                    self.write(message)
                    self.write(frame_bnd + '\n')
                    await self.flush()

        except Exception as e:
            print('UpdatedStateHandler: caught exception:', type(e), ' : ', e)
            # print('raising', e)
            # raise e








