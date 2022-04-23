import torch as t
import random
import os
import PIL.Image as Image
import numpy as np
from run_agent import to_gpu




##################################################################################################################
#### Helpers

## (y,x)
FRAME_SIZE = (1080,1920)
IMG_DIR = os.path.join( os.path.split(__file__)[0], 'images' )

def get_rand_image():
    name = random.choice(os.listdir(IMG_DIR))
    img_path = os.path.join(IMG_DIR, name)

    with open(img_path, 'r') as f:
        img = Image.open(img_path)

    img = img.convert('RGB')
    img = img.resize([100,100], resample=3)
    img = np.array(img)
    return img

def rand_pair():
    offsets_x = (50, 900)
    offsets_y = (50, 500)
    return [random.randint(*offsets_x), random.randint(*offsets_y)]

def to_tensor(states):
    for i,state in enumerate(states):

        state_0 = tuple( [t.from_numpy(img) for img in state[0]] )
        others = tuple( [t.from_numpy(tem) for tem in state[1:]] )
        states[i] = tuple( [state_0, *others] )
    return states



##################################################################################################################
#### Data Generators
def build_test_state():

    offs_locs_x = (0, 900)
    offs_locs_y = (0, 500)
    n_obj = 21

    imgs = tuple(get_rand_image() for _ in range(n_obj))
    img_sizes = np.array([(img.shape[0],img.shape[1]) for img in imgs], dtype=np.int32)

    ## row 0 is always tree root. Children always have higher id than parent.
    child_mat = np.zeros([n_obj,n_obj], dtype=np.uint8)
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

    depths = [i for i in range(n_obj)]
    depths = np.array(depths, dtype=np.int32)

    return imgs,img_sizes,child_mat,locs_rel,locs_abs,depths

def gen_states(n_states=10):
    print('generating states')

    states = list()
    for i in range(n_states):
        if i%100==0: print('building state: ', i)
        state = build_test_state()
        states.append(state)

    states = to_tensor(states)
    print('saving states')
    t.save(states, '/home/chris/Documents/agent_interface/' + str(n_states) + '_small_states.list')

def gen_buffs(n_buffs=10):
    print("loading states from disk")
    states = t.load('/home/chris/Documents/agent_interface/' + str(n_buffs) + '_states.list')
    states = to_gpu(states)

    z_buffer = t.empty(FRAME_SIZE, dtype=t.int32).cuda()
    f_buffer = t.empty([*FRAME_SIZE,3], dtype=t.int32).cuda()
    lock_buffer = t.empty(FRAME_SIZE, dtype=t.int32).cuda()

    buffs = list()
    for i,state in enumerate(states):
        if i%100==0: print('creating buff', i)

        t.ops.render_op.render_kernel(*state, z_buffer, f_buffer, lock_buffer)

        f_buffer_cpu = f_buffer.cpu()
        buffs.append(f_buffer_cpu)

    t.save(buffs, '/home/chris/Documents/agent_interface/'+str(n_buffs)+'_buffs.list')

if __name__ == "__main__":
    gen_states(600)