import base64
import functools
import os, random
import uuid
from io import BytesIO

from tornado import httpclient, httputil, options
from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop

import logging
import re
import time

import numpy as np
from numba import njit, prange
import PIL.Image as Image
import multiprocessing as mp
import pickle
import cv2

import matplotlib.pyplot as plt
import torch as t


## (y,x)
FRAME_SIZE = (1080,1920)
IMG_DIR = os.path.join( os.path.split(__file__)[0], 'images' )








###########################################################################################
###########################################################################################

def offset_locstr(xy):
    offset_x = np.random.randint(0, 1500)
    offset_y = np.random.randint(0, 1500)
    offset_x = np.add(xy[:, 0], offset_x)
    offset_y = np.add(xy[:, 1], offset_y)
    offset_xy = np.stack([offset_x, offset_y], 1)

    locstr = re.sub(r'[\[\]\s+]', ' ', str(offset_xy)).strip(' ')
    locstr = locstr.split()
    return locstr

def get_rand_image(IMG_DIR):
    name = random.choice(os.listdir(IMG_DIR))
    img_path = os.path.join(IMG_DIR, name)

    with open(img_path, 'r') as f:
        img = Image.open(img_path)

    img = img.convert('RGB')
    img = img.resize([400,400], resample=3)
    img = np.array(img)
    return img

def rand_pair():
    offsets_x = (50, 900)
    offsets_y = (50, 500)
    return [random.randint(*offsets_x), random.randint(*offsets_y)]

def int2bstr(int_data):
    return bytes( str(int_data), 'utf-8')

###########################################################################################
###########################################################################################

class Node():
    def __init__(self, img, message=None, o_uuid=None, offs_x=0, offs_y=0, abs_depth=0):
        self.children = list()

        self.message = message
        self.o_uuid = o_uuid

        self.offs_x = offs_x
        self.offs_y = offs_y

        self.abs_depth = abs_depth
        self.img = img

    def add_children(self, children):
        self.children.extend(children)

    def gen_message(self, message, o_uuid):
        # check if message exists. If not, generate it and return
        pass

    def set_offsets(self, offsets):
        self.offs_x = offsets[0]
        self.offs_y = offsets[1]

    def set_abs_depth(self, abs_depth):
        self.abs_depth = abs_depth

def render_process_recursive(stree, z_buffer, f_buffer, x_off_accum, y_off_accum):
    ## calc absolute x,y offsets for my coord frame
    abs_x, abs_y = stree.offs_x + x_off_accum, stree.offs_y + y_off_accum

    if stree.img is not None:

        crop_y_start = -abs_y if -abs_y > 0 else 0
        crop_x_start = -abs_x if -abs_x > 0 else 0

        crop_y_end = FRAME_SIZE[0] - abs_y if (abs_y+stree.img.shape[0]) - FRAME_SIZE[0] > 0 else stree.img.shape[0]
        crop_x_end = FRAME_SIZE[1] - abs_x if (abs_x+stree.img.shape[1]) - FRAME_SIZE[1] > 0 else stree.img.shape[1]

        buff = z_buffer[abs_y : abs_y+stree.img.shape[0], abs_x : abs_x+stree.img.shape[1]]

        imbuff_mask = buff > stree.abs_depth

        z_buffer[abs_y: abs_y + stree.img.shape[0], abs_x: abs_x + stree.img.shape[1]][imbuff_mask] = stree.abs_depth

        f_buffer[abs_y: abs_y + stree.img.shape[0], abs_x: abs_x + stree.img.shape[1]][imbuff_mask] = stree.img[crop_y_start:crop_y_end, crop_x_start:crop_x_end][imbuff_mask]

    for child in stree.children: render_process_recursive(child, z_buffer, f_buffer, abs_x, abs_y)

def render_state_recursive(tree):

    z_buffer = np.full(FRAME_SIZE, 255, dtype=np.uint8)
    f_buffer = np.zeros([*FRAME_SIZE,3],dtype=np.uint8)

    render_process_recursive(tree, z_buffer, f_buffer, 0, 0)

    return z_buffer, f_buffer

def build_test_state_recursive():
    depths = (0,20)

    ## base node sits at top left of canvas at (x,y)=(0,0)
    tree = Node(None,None)

    new_children = [Node(get_rand_image(),abs_depth=random.randint(*depths)) for _ in range(4)]
    tree.add_children(new_children)

    for child in tree.children:
        child.set_offsets(rand_pair())

        new_children = [Node(get_rand_image(),abs_depth=random.randint(*depths)) for _ in range(4)]
        [child.set_offsets( rand_pair() ) for child in new_children]
        child.add_children(new_children)

    return tree

###########################################################################################
###########################################################################################

def build_test_state():
    IMG_DIR = os.path.join( os.path.split(__file__)[0], 'images')

    # imgs, locs, depths, z_buffer, f_buffer
    offs_locs_x = (0, 900)
    offs_locs_y = (0, 500)
    n_obj = 21

    imgs = tuple(get_rand_image(IMG_DIR) for _ in range(n_obj))

    ## row 0 is always tree root. Children always have higher id than parent.
    child_mat = np.zeros([n_obj,n_obj])
    child_mat[0][ [1,2,3,4] ] = 1

    child_mat[1][ [5,6,7,8] ] = 1
    child_mat[2][ [9,10,11,12] ] = 1
    child_mat[3][ [13,14,15,16] ] = 1
    child_mat[4][ [17,18,19,20] ] = 1

    locs = [[random.randint(*offs_locs_y), random.randint(*offs_locs_x)] for _ in range(n_obj)]
    locs_rel = np.array(locs, dtype=np.int32)
    locs_rel[0] = 0

    locs_abs = np.zeros_like(locs_rel) - 1
    locs_abs[0] = 0

    # depths = [random.randint(*depths) for _ in range(n_obj)]
    depths = [i for i in range(n_obj)]
    depths = np.array(depths, dtype=np.int32)

    z_buffer = np.full(FRAME_SIZE, 255, dtype=np.uint8)
    f_buffer = np.zeros([*FRAME_SIZE,3],dtype=np.uint8)

    return imgs,child_mat,locs_rel,locs_abs,depths,z_buffer,f_buffer

@njit
def transform_rel_locs(imgs,child_mat,locs_rel,locs_abs,depths,z_buffer,f_buffer):

    ## row gives parent id. Must visit and process sequentially
    for row in range( child_mat.shape[0] ):
        curr_offs = locs_abs[row]

        ## col gives child of curr object, if col==1. Can be visited in parallel
        for col in prange( child_mat.shape[1] ):
            if child_mat[row,col]:

                ## abs loc of child = child_rel_offs + parent_abs_loc
                locs_abs[col] = locs_rel[col] + curr_offs

    return imgs,child_mat,locs_rel,locs_abs,depths,z_buffer,f_buffer

@njit(parallel=True)
def render_state_parallel(imgs,child_mat,locs_rel,locs_abs,depths,z_buffer,f_buffer):

    n_loops = len(imgs)

    for loop in range(n_loops):

        img = imgs[loop]
        abs_depth = depths[loop]
        abs_y, abs_x = locs_abs[loop][0], locs_abs[loop][1]

        for i in prange(img.shape[0]):
            for j in prange(img.shape[1]):

                if (abs_y + i < f_buffer.shape[0]) and (abs_x + j < f_buffer.shape[1]):

                    if z_buffer[abs_y + i, abs_x + j] > abs_depth:
                        z_buffer[abs_y + i, abs_x + j] = abs_depth
                        f_buffer[abs_y + i, abs_x + j] = img[i,j]

    return z_buffer, f_buffer

###########################################################################################
###########################################################################################




def agent_loop():

    ## init http client
    client = httpclient.HTTPClient(force_instance=True)
    mouse_url = 'http://127.0.0.1:8888/mouse/report'
    state_add_url = 'http://localhost:8888/state/add'
    state_rm_url = 'http://localhost:8888/state/rm'
    curr_uuid = None

    ## init program state-tree
    state = build_test_state()

    ## init ML agent
    pass

    ## main loop
    while True:
        # # block until we get a response
        # req = httpclient.HTTPRequest(req_url, method='GET', body=None, request_timeout=0)
        # resp = client.fetch(req, raise_error=True)
        #
        # # string of new mouse locations and clicks
        # locs_clicks = resp.body.decode()
        # locs_clicks = locs_clicks.split(';--;')
        # # print(locs_clicks)

        state = transform_rel_locs(*state)
        z_buffer, f_buffer = render_state_parallel(*state)

        # z_buffer[z_buffer > 20] = 21
        # z_buffer, f_buffer = Image.fromarray(z_buffer), Image.fromarray(f_buffer)
        # plt.figure(); plt.imshow(z_buffer); plt.show(block=False)
        # plt.figure(); plt.imshow(f_buffer); plt.show(block=False)

        ## send f_buffer and state to agent
        pass

        ## receive changes to state from agent; update state
        pass

        ## clear existing state and then write new state (TODO: enforce ordering by putting both calls in one message)
        if curr_uuid is not None:
            del_message = curr_uuid
            req = httpclient.HTTPRequest(state_rm_url, method='POST', body=del_message, request_timeout=1000000000000000000)
            client.fetch(req)

        ## send new state to browser.
        pil_img = Image.fromarray(f_buffer)
        buff = BytesIO()
        pil_img.save(buff, format="JPEG")
        blob = base64.b64encode( buff.getvalue() )

        o_uuid = int2bstr(uuid.uuid1().int)
        width, height = int2bstr( f_buffer.shape[1] ), int2bstr( f_buffer.shape[0] )
        draw_message = (b' ').join( [o_uuid, ID_SEP, b'draw', T_SEP, b'im_blob',T_SEP, b'[', b'data:image/jpeg;base64,'+blob, b'0',b'0', width,height, b']'] )
        req = httpclient.HTTPRequest(state_add_url, method='POST', body=draw_message, request_timeout=1000000000000000000)
        client.fetch(req)

        curr_uuid = o_uuid

        print('stop')

    # ask for mouse moves - wait till they show up

    # when mouse loc/click arrives, process it
    ##  pass mouse interaction (which object is hovered or clicked) to ML agent
    ##  render program state and pass to ML agent

    ##  (possibly) receive program state updates from agent
    ##  update engine program state

    ##  send program state updates to server
    ##  server sends updated state to browser
    ##  browser renders state exactly as the engine did










def test_renderer():

    client = httpclient.HTTPClient(force_instance=True)
    mouse_url = 'http://127.0.0.1:8888/mouse/report'
    state_add_url = 'http://localhost:8888/state/add'
    state_rm_url = 'http://localhost:8888/state/rm'

    print("loading tests from disk")
    states = t.load('/home/chris/Documents/agent_interface/state200_save.list')

    for i,state in enumerate(states):
        if i%100==0: print('running test: ', i)

        state = states[i]

        ## render state
        state = transform_rel_locs(*state)
        z_buffer, f_buffer = render_state_parallel(*state)

        ## cv2
        _, blob = cv2.imencode('.jpg', f_buffer)

        # draw_message = bytes(blob)
        draw_message = base64.b64encode(blob)
        draw_message = b'data:image/jpeg;base64,' + draw_message

        req = httpclient.HTTPRequest(state_add_url, method='POST', body=draw_message, request_timeout=0.1)
        client.fetch(req)

        # z_buffer[z_buffer > 22] = 22
        # z_buffer, f_buffer = Image.fromarray(z_buffer), Image.fromarray(f_buffer)
        # plt.figure(); plt.imshow(z_buffer); plt.show(block=False)
        # plt.figure(); plt.imshow(f_buffer); plt.show(block=False)

        # print('stop')





def gen_states():
    n_loops = 302

    states = list()
    for i in range(n_loops):
        if i%100==0: print('building test: ', i)
        state = build_test_state()
        states.append(state)

    t.save(states, '/home/chris/Documents/agent_interface/state300_save.list')

def gen_messages():
    print("loading tests from disk")
    states = t.load('/home/chris/Documents/agent_interface/state200_save.list')

    messages = list()
    for i,state in enumerate(states):
        state = states[i]

        state = transform_rel_locs(*state)
        z_buffer, f_buffer = render_state_parallel(*state)

        _, blob = cv2.imencode('.jpg', f_buffer)

        # draw_message = bytes(blob)
        draw_message = base64.b64encode(blob)
        draw_message = b'data:image/jpeg;base64,' + draw_message
        messages.append(draw_message)

    return messages


async def test_renderer_async(client, states):
    state_add_url = 'http://localhost:8888/state/add'

    for i,state in enumerate(states):
        if i%100==0: print('running test: ', i)

        state = transform_rel_locs(*state)
        z_buffer, f_buffer = render_state_parallel(*state)

        _, blob = cv2.imencode('.jpg', f_buffer)
        # draw_message = bytes(blob)
        draw_message = base64.b64encode(blob)
        draw_message = b'data:image/jpeg;base64,' + draw_message

        req = httpclient.HTTPRequest(state_add_url, method='POST', body=draw_message, request_timeout=1)
        await client.fetch(req)

async def test_messages_async(client, messages):
    state_add_url = 'http://localhost:8888/state/add'

    for i,message in enumerate(messages):
        if i%100==0: print('running test: ', i)

        req = httpclient.HTTPRequest(state_add_url, method='POST', body=message, request_timeout=1)
        await client.fetch(req)

def run_renderer_async():
    AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
    client = httpclient.AsyncHTTPClient(force_instance=True)

    print("loading tests from disk")
    states = t.load('/home/chris/Documents/agent_interface/state200_save.list')

    io_loop = IOLoop.current()
    io_loop.run_sync( functools.partial(test_renderer_async, client, states) )

def run_messages_async():
    AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
    client = httpclient.AsyncHTTPClient(force_instance=True)

    print("generating messages")
    messages = gen_messages()

    io_loop = IOLoop.current()
    io_loop.run_sync(functools.partial(test_messages_async, client, messages))

if __name__ == "__main__":
    # gen_states()
    # gen_messages()

    # agent_loop()
    # test_renderer()
    # run_renderer_async()
    run_messages_async()








