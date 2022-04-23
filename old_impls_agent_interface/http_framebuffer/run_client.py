import base64
import os
import uuid

from tornado import httpclient, httputil, options

import logging
import re
import time

import numpy as np
import multiprocessing as mp


######## Global Seperator Strings
M_SEP = b';-MSEP-;'
T_SEP = b';-TYPE-;'
ID_SEP = b';-ID-;'

M_SEP_UTF = ';-MSEP-;'
T_SEP_UTF = ';-TYPE-;'
ID_SEP_UTF = ';-ID-;'


######## Test Images
IMG_DIR = os.path.split(__file__)[0] + '/images/'
IMG_NAMES = ['puppy.jpg', 'puppy.jpeg', 'puppy.bmp', 'puppy.png']




def offset_locstr(xy):
    offset_x = np.random.randint(0, 1500)
    offset_y = np.random.randint(0, 1500)
    offset_x = np.add(xy[:, 0], offset_x)
    offset_y = np.add(xy[:, 1], offset_y)
    offset_xy = np.stack([offset_x, offset_y], 1)

    locstr = re.sub(r'[\[\]\s+]', ' ', str(offset_xy)).strip(' ')
    locstr = locstr.split()
    return locstr


def send_circle(xy):
    # <uuid> ID_SEP <mode> T_SEP circle T_SEP [loc_x loc_y radius]  ...

    message = ''
    locstr = offset_locstr(xy)
    radius = np.random.randint(5, 50)
    uuids = list()
    for i in range(0, len(locstr)-1, 2):
        o_uuid = str(uuid.uuid1().int)
        uuids.append(o_uuid)
        message = (' ').join( [message, o_uuid, ID_SEP_UTF, 'draw', T_SEP_UTF, 'circle', T_SEP_UTF, '[', locstr[i], locstr[i+1], str(radius), ']', M_SEP_UTF] )

    return message, uuids


def send_rect(xy):
    # <uuid> ID_SEP <mode> T_SEP rect T_SEP [loc_x loc_y xWidth yHeight]  ...

    message = ''
    locstr = offset_locstr(xy)
    width = np.random.randint(20, 80)
    height = np.random.randint(20, 80)
    uuids = list()
    for i in range(0, len(locstr)-1, 2):
        o_uuid = str(uuid.uuid1().int)
        uuids.append(o_uuid)
        message = (' ').join( [message, o_uuid, ID_SEP_UTF, 'draw', T_SEP_UTF, 'rect',T_SEP_UTF,'[', locstr[i], locstr[i + 1], str(width), str(height), ']', M_SEP_UTF] )

    return message, uuids

def send_text(xy):
    # <uuid> ID_SEP <mode> T_SEP text T_SEP [text_str loc_x loc_y font] ...

    message = ''
    locstr = offset_locstr(xy)
    strings = ['tab', 'lab', 'nab', 'hab']
    font = '48px serif'
    j = 0
    uuids = list()
    for i in range(0, len(locstr) - 1, 2):
        string = strings[j]
        j+=1
        j%=len(strings)
        o_uuid = str(uuid.uuid1().int)
        uuids.append(o_uuid)
        message = (' ').join( [message, o_uuid, ID_SEP_UTF, 'draw', T_SEP_UTF, 'text', T_SEP_UTF, '[', string, locstr[i], locstr[i + 1], font, ']', M_SEP_UTF] )

    return message, uuids


def send_image_via_localpath(xy):
    '''
        <uuid> ID_SEP <mode> T_SEP image T_SEP [img_path loc_x loc_y [xWidth yHeight]] ...

        xWidth and yHeight can be omitted or replaced by 'null'; the image will print at native size.
        If one of dWidth or DHeight are included, the other must be included as well.
        jpeg, png, and bmp known to be supported though more formats probably are.
        This method may provide higher latency for displaying images.
    '''

    message = ''
    width = np.random.randint(20, 120)
    height = np.random.randint(20, 120)

    j = 0
    uuids = list()
    locstr = offset_locstr(xy)
    for i in range(0, len(locstr) - 1, 2):

        img_path = IMG_DIR + IMG_NAMES[j]
        j += 1
        j %= len(IMG_NAMES)

        o_uuid = str(uuid.uuid1().int)
        uuids.append(o_uuid)
        message = (' ').join( [message, o_uuid, ID_SEP_UTF, 'draw', T_SEP, 'im_path', T_SEP_UTF,'[', img_path, locstr[i], locstr[i + 1], str(width),str(height),']', M_SEP_UTF] )

    return message, uuids


def send_image_via_request(xy):
    ## <uuid> ID_SEP <mode> T_SEP blob T_SEP [base64_img_blob x y width, height] ...

    ## must be a byte string.
    ## This method may provide lower latency for displaying images.
    ## The header 'data:image/jpeg;base64,' for base64-encoded blob will work for any image format (jpeg, png, and bmp so far).

    message = b''

    width = np.random.randint(20, 120)
    height = np.random.randint(20, 120)
    width = bytes(str(width), 'utf-8')
    height = bytes(str(height), 'utf-8')

    j = 0
    locstr = offset_locstr(xy)
    uuids = list()
    for i in range(0, len(locstr) - 1, 2):

        img_path = IMG_DIR + IMG_NAMES[j]
        j += 1
        j %= len(IMG_NAMES)

        with open(img_path, 'rb') as f:
            blob = base64.b64encode( f.read() )

        x,y = bytes(str(locstr[i]), 'utf-8'), bytes(str(locstr[i+1]), 'utf-8')

        ## specifying the correct extension doesn't seem to matter
        o_uuid = bytes( str(uuid.uuid1().int), 'utf-8')
        uuids.append(o_uuid)
        sub_message = (b' ').join( [o_uuid, ID_SEP, b'draw', T_SEP, b'im_blob',T_SEP, b'[', b'data:image/jpeg;base64,'+blob, x,y, width,height, b']', M_SEP] )

        message = (b'').join( [message, sub_message] )

    return message, uuids


def update_state(client):
    ''' Each message (string) includes at least one object descriptor. Object descriptors can be chained together into a
        message with the M_SEP seperator, as in:
            message = "uuid ID_SEP mode T_SEP type T_SEP [data ...]    M_SEP    uuid ID_SEP mode T_SEP type T_SEP [data ...]  ... "

        Any mixture of objects can be included in each message, except images sent via request, which sends byte-strings.
        A message can contain any number of object descr's.
        A message string can be a standard python string, or a python byte-string (but not a combination of both).

        A message sent to /state/rm POST will erase objects, listed by their uuid's, separated by ID_SEP, as in:
            message = "uuid ID_SEP uuid ID_SEP ... "

        Only mode 'draw' is supported.

        DO NOT CHANGE THE SEPERATORS; THEY ARE DEFINED AS STRINGS IN THE SERVER, CLIENT, AND BROWSER-SIDE CODE AND MUST MATCH
        ID_SEP: seperator between an object's unique uuid and other data
        T_SEP:  type seperator, between the object type descriptor and the object-data
        M_SEP:  message seperators, between object descriptors in a message string
    '''

    x = np.linspace(0, 200, 3, dtype=np.int)
    y = np.linspace(0, 200, 3, dtype=np.int)

    xy = np.meshgrid(x, y)
    xy = np.stack([xy[0].ravel(), xy[1].ravel()], 1)

    uuids = list()
    while True:
        time.sleep(0.1)

        for shape_fn in ['send_image_via_request', 'send_circle', 'send_rect', 'send_text']:
        # for shape_fn in ['send_image_via_request']:
        # for shape_fn in ['send_circle', 'send_rect', 'send_text']:
        # for shape_fn in ['send_circle']:
        # for shape_fn in ['send_text']:

            for i in range(4):
                message, m_uuids = eval(shape_fn)(xy)
                uuids.extend(m_uuids)

                req_url = 'http://localhost:8888/state/add'
                req = httpclient.HTTPRequest(req_url, method='POST', body=message, request_timeout=1000000000000000000)
                client.fetch(req, raise_error=True)

                time.sleep(0.05)

            if len(uuids) > 50:

                ## utf-8 strings and byte-strings cannot be concatenated. Separate them out
                b_str, utf_str = list(), list()
                for uuid in uuids:
                    if isinstance(uuid, str): utf_str.append(uuid)
                    else: b_str.append(uuid)

                utf_str = ID_SEP_UTF.join(utf_str)
                b_str = ID_SEP.join(b_str)

                for del_message in [utf_str, b_str]:
                    if del_message:
                        req_url = 'http://localhost:8888/state/rm'
                        req = httpclient.HTTPRequest(req_url, method='POST', body=del_message, request_timeout=1000000000000000000)
                        client.fetch(req, raise_error=True)

                uuids = list()




def poll_mouse(client):
    ## get latest mouse moves; client process asks for any new mouse locs
    ## client.fetch will block until server returns new mouse moves
    req_url = 'http://127.0.0.1:8888/mouse/report'

    while True:
        req = httpclient.HTTPRequest(req_url, method='GET', body=None, request_timeout=0)
        resp = client.fetch(req, raise_error=True)
        locs = resp.body.decode()
        print(locs)




if __name__ == "__main__":

    client = httpclient.HTTPClient(force_instance=True)
    # update_state(client)
    # poll_mouse(client)

    update_proc = mp.Process(target=update_state, args=(client,))
    update_proc.start()

    mouse_proc = mp.Process(target=poll_mouse, args=(client,))
    mouse_proc.start()







