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


M_SEP_UTF = ';-MSEP-;'
T_SEP_UTF = ';-TYPE-;'
ID_SEP_UTF = ';-ID-;'

M_SEP = b';-MSEP-;'
ID_SEP = b';-ID-;'


class ProgramState():
    ''' store program state '''

    def __init__(self):

        # cond is notified whenever the message cache is updated
        self.cond = tornado.locks.Condition()

        self.state = collections.OrderedDict()
        self.del_pairs = tornado.queues.Queue()

        # holds buffered mouse locations 
        self.mouse_q = tornado.queues.Queue()

        self.max_buff_size = 200
        self.n_deleted = 0

    def push_del_pair(self, draw_uuid, del_uuid):

        self.del_pairs.put_nowait( (draw_uuid, del_uuid) )

        # check if unflushed buffer of deletions exceeds max_buff_size
        if self.del_pairs.qsize() >= self.max_buff_size:

            log.app_log.info("BUFFER FLUSH: START")

            # flush draw/del pairs in the older half of the deletions buffer
            for i in range( self.max_buff_size//2 ):

                del_pair = self.del_pairs.get_nowait()

                draw_uuid, del_uuid = del_pair
                self.state.pop(draw_uuid)
                self.state.pop(del_uuid)

                self.del_pairs.task_done()

            # half of the max_buffer_size of pairs was flushed, at two messages per pair
            self.n_deleted += self.max_buff_size

            log.app_log.info("BUFFER FLUSH: DONE")







# Each handler has access to a common record of the shapes drawn in the browser (program state), via the 'prog_state'
class BaseView(RequestHandler):
    prog_state = ProgramState()
    
    def get(self):
        self.render('index_old.html', messages=[])





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







class SendUpdatedState(BaseView):
    '''
    Each client requests the program state and passes an arg 'cursor' to indicate where in the buffer it has rendered up
    to; and therefore which new messages it needs.
    
    This handler waits on notification from the prog_state.cond that the prog_state.state has changed. Any 
    pending requests will then be served the updated program state parts needed by the requesting client.
    '''

    # /state/update POST
    async def post(self):

        # each tab or browser keeps track of how many messages it's received using a 'cursor'
        cursor = int( self.get_argument('cursor', None) )

        # the cursor does not keep track of how many messages have been debuffered - adjusted here by n_deleted
        new_messages = list( BaseView.prog_state.state.values() )[cursor - BaseView.prog_state.n_deleted:]

        while not new_messages:
            self.wait_future = BaseView.prog_state.cond.wait()
            try: await self.wait_future
            except asyncio.CancelledError: return

            # the buffer may flush while waiting above - make sure to adjust cursor by n_deleted here as well
            new_messages = list( BaseView.prog_state.state.values() )[cursor - BaseView.prog_state.n_deleted:]

        if self.request.connection.stream.closed(): return

        self.write( options.M_SEP.join(new_messages) )


class StateAdd(BaseView):
    ''' State updates to add objects are handled here. '''

    # /state/add POST
    async def post(self):

        message = self.request.body

        for sub_mess in message.split(M_SEP):
            if sub_mess:
                sub_mess = sub_mess.split(ID_SEP)

                # add uuid / object-descr pair to prog_state
                BaseView.prog_state.state[sub_mess[0].strip()] = sub_mess[1].strip()

        BaseView.prog_state.cond.notify_all()


class StateRm(BaseView):
    ''' State updates to remove objects are handled here. '''

    # /state/rm POST
    async def post(self):

        message = self.request.body

        for draw_uuid in message.split(ID_SEP):

            if draw_uuid in BaseView.prog_state.state:

                # delete message for object at 'draw_uuid' gets new key 'del_uuid'
                del_uuid = bytes( str(uuid.uuid1().int), 'utf-8')
                del_mess = BaseView.prog_state.state[draw_uuid]
                del_mess = del_mess.replace(b'draw', b'del')

                BaseView.prog_state.state[del_uuid] = del_mess

                # buffer the deletion of the pair of draw_ and del_ keys
                BaseView.prog_state.push_del_pair(draw_uuid, del_uuid)

            else:
                log.app_log.error("UUID TO DEL NOT IN PROG_STATE")

        BaseView.prog_state.cond.notify_all()


class ImageUploadHandler(BaseView):

    async def get(self, typechar):

        local_fname = self.request.path.replace(options.IMAGE_GET_URL, '')

        with open(local_fname, 'rb') as f:
            self.write(f.read())

