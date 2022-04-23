import asyncio
import collections
import json
import os
import uuid
import logging

import tornado
import tornado.queues
import tornado.locks
from tornado.web import RequestHandler
from tornado.options import options
from tornado import log as log

from multiprocessing import Lock

from run_agent import int2bstr

M_SEP_UTF = ';-MSEP-;'
T_SEP_UTF = ';-TYPE-;'
ID_SEP_UTF = ';-ID-;'

M_SEP = b';-MSEP-;'
ID_SEP = b';-ID-;'


## this handlers file supports overwriting the entire frame with every update.

class ProgramState():
    ''' store program state '''

    def __init__(self):

        self.frame = None
        self.n_frames = 0

        self.frames = list()

        # cond is notified whenever the message cache is updated
        self.cond = tornado.locks.Condition()

        # self.state = collections.OrderedDict()
        # self.del_buff = tornado.queues.Queue()

        # holds buffered mouse locations 
        # self.mouse_q = tornado.queues.Queue()







# Each handler has access to a common record of the shapes drawn in the browser (program state), via the 'prog_state'
class BaseView(RequestHandler):
    prog_state = ProgramState()
    
    def get(self):
        self.render('index.html')





class MouseClientReporter(RequestHandler):

    # /mouse/report GET
    async def get(self):
        ## client python process calls /mouse/report GET to get new mouse locations

        locs_clicks = list()

        loc = await BaseView.prog_state.mouse_q.get()
        BaseView.prog_state.mouse_q.task_done()
        locs_clicks.append( loc )

        while BaseView.prog_state.mouse_q.qsize():
            locs_clicks.append( BaseView.prog_state.mouse_q.get_nowait() )
            BaseView.prog_state.mouse_q.task_done()

        self.write(';--;'.join(locs_clicks))

class MouseMoveHandler(RequestHandler):

    # /mouse/move POST
    async def post(self):
        ## here we add mouse locations to BaseView.mouse_q

        x = int( self.request.arguments['x'][0].decode() )
        y = int( self.request.arguments['y'][0].decode() )

        BaseView.prog_state.mouse_q.put_nowait( str( (x,y) ) )

class MouseClickHandler(RequestHandler):

    # /mouse/click POST
    async def post(self):
        ## here we add mouse click-codes to BaseView.mouse_q

        button = int( self.request.arguments['button'][0].decode() )

        if button == 0: click_str = "left click"
        elif button == 1: click_str = "middle click"
        elif button == 2: click_str = "right click"
        else: click_str = "unknown click code"
        BaseView.prog_state.mouse_q.put_nowait( click_str )



def str2bool(str):
    if str == 'false': return False
    if str == 'true': return True

class KeyHandler(RequestHandler):

    # /key/update POST
    def post(self):

        shiftKey = str2bool( self.request.arguments['shiftKey'][0].decode() )
        ctrlKey = str2bool( self.request.arguments['ctrlKey'][0].decode() )
        altKey = str2bool( self.request.arguments['altKey'][0].decode() )
        Key = self.request.arguments['Key'][0].decode()

        ## if 'Key' contains a modifier string ('Shift','Control','Alt'), only shift/ctrl/alt are pressed
        if len(Key) > 1:
            return

        font = '48px serif'
        del_uuid = bytes( str(uuid.uuid1().int), 'utf-8')
        draw_uuid = bytes( str(uuid.uuid1().int), 'utf-8')

        del_char_rect = ' '.join( ['del', T_SEP_UTF, 'rect', T_SEP_UTF, '[', '0','0','300','300', ']'] )
        draw_char = ' '.join( ['draw', T_SEP_UTF, 'text', T_SEP_UTF, '[', Key, '100','100',font, ']'] )
        del_char_rect = bytes( del_char_rect, 'utf-8')
        draw_char = bytes( draw_char, 'utf-8')

        BaseView.prog_state.state[del_uuid] = del_char_rect
        BaseView.prog_state.state[draw_uuid] = draw_char

        BaseView.prog_state.push_del_pair(draw_uuid, del_uuid)
        BaseView.prog_state.cond.notify_all()




async def generate(prog_state, handler):

    while True:

        frame = prog_state.frame

        while not frame:
            wait_future = BaseView.prog_state.cond.wait()
            try: await wait_future
            except asyncio.CancelledError: return

            frame = BaseView.prog_state.frame

            if handler.request.connection.stream.closed(): return

            yield frame




class SendUpdatedState_multipart(BaseView):

    # /state/update POST
    async def get(self):

        sent = 0
        frame_bnd = "--framebnd"

        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0')
        self.set_header('Connection', 'close')
        self.set_header('Content-Type', 'multipart/x-mixed-replace;boundary='+frame_bnd)
        self.set_header('Pragma', 'no-cache')

        while True:

            curr_frame = BaseView.prog_state.n_frames
            frame = BaseView.prog_state.frame

            if not frame or sent >= curr_frame:
                await BaseView.prog_state.cond.wait()
                frame = BaseView.prog_state.frame

            self.write("Content-type: image/jpeg\r\n")
            self.write("Content-length: %s\r\n\r\n" % len(frame))
            self.write(frame)
            self.write(frame_bnd + '\n')

            await self.flush()

            sent = curr_frame

class SendUpdatedState(BaseView):

    # /state/update GET
    async def get(self):

        # cursor = int( self.get_argument('cursor') )
        #
        # curr_frame = BaseView.prog_state.n_frames
        # frame = BaseView.prog_state.frame
        #
        # if not frame or cursor >= curr_frame:
        #     await BaseView.prog_state.cond.wait()
        #     frame = BaseView.prog_state.frame
        #
        # self.write(frame)
        # await self.flush()


        cursor = int(self.get_argument('cursor'))
        new_frames = BaseView.prog_state.frames[cursor:]

        while not new_frames:
            await BaseView.prog_state.cond.wait()
            new_frames = BaseView.prog_state.frames[cursor:]

        self.write(new_frames[0])
        await self.flush()




class StateAdd(BaseView):

    # /state/add POST
    async def post(self):

        message = self.request.body

        # BaseView.prog_state.frame = message
        # BaseView.prog_state.n_frames += 1
        # BaseView.prog_state.cond.notify_all()

        BaseView.prog_state.frames.append(message)
        BaseView.prog_state.cond.notify_all()


class StateRm(BaseView):
    ''' State updates to remove objects are handled here. '''

    # /state/rm POST
    async def post(self):

        message = self.request.body

        for draw_uuid in message.split(ID_SEP):

            # if draw_uuid in BaseView.prog_state.state:

                # delete message for object at 'draw_uuid' gets new key 'del_uuid'
                # del_uuid = bytes( str(uuid.uuid1().int), 'utf-8')
                # del_mess = BaseView.prog_state.state[draw_uuid]
                # del_mess = del_mess.replace(b'draw', b'del')
                #
                # BaseView.prog_state.state[del_uuid] = del_mess

                # buffer the deletion of the pair of draw_ and del_ keys
            BaseView.prog_state.push_buff_del(draw_uuid)

            # else:
            #     log.app_log.error("UUID TO DEL NOT IN PROG_STATE")

        BaseView.prog_state.cond.notify_all()



