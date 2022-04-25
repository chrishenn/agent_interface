import functools, os, time
import logging
import signal
import psutil

import torch as t
import torch.multiprocessing as mp

import concurrent.futures

import tornado.process
from tornado.ioloop import IOLoop

import server
t.ops.load_library(os.path.join(os.path.split(__file__)[0], 'render_cuda/build/librender.so'))

## (y,x)
FRAME_SIZE = (1080,1920)
IMG_DIR = os.path.join( os.path.split(__file__)[0], 'images' )



###########################################################################################
###########################################################################################
###### Helpers

def to_gpu(states):

    for i,state in enumerate(states):

        state_0 = tuple( [img.cuda() for img in state[0]] )
        others = tuple( [tem.cuda() for tem in state[1:]] )
        states[i] = tuple( [state_0, *others] )
    return states

def to_numpy_state(states):

    for i,state in enumerate(states):

        state_0 = tuple( [img.numpy() for img in state[0]] )
        others = tuple( [tem.numpy() for tem in state[1:]] )
        states[i] = tuple( [state_0, *others] )
    return states

###########################################################################################
###########################################################################################
###### Agent Loop

def flush_q(queue):
    try:
        while True:
            queue.get_nowait()
    except: pass

async def get_blocking(queue):
    try:
        item = queue.get()
        return item
    except Exception as e:
        print('agent proc: on blocking_q.get(), caught exception', type(e), ' : ', e, '; raising')
        raise e

def print_loc(obj):
    print('agent proc: got mouse location:', obj)

def del_state(state):
    for item in state[1:]: del item
    for item in state[0]: del item


###### Main Agent Interface Loop
async def agent_loop(shared_obj):
    mouse_q, key_q, frame_q, event_end = shared_obj

    # print("gpu buffs test: loading buffs from disk")
    # buffs = t.load('/home/chris/Documents/agent_interface/100_buffs.list')
    # buffs = [buff.cuda() for buff in buffs]
    # buffs = iter(buffs)

    print("gpu render test: loading states from disk")
    states = t.load('/home/chris/Documents/agent_interface/100_states.list')
    states = to_gpu(states)
    states = iter(states)

    z_buffer = t.empty(FRAME_SIZE, dtype=t.int32).cuda()
    f_buffer = t.empty([*FRAME_SIZE,3], dtype=t.int32).cuda()
    lock_buffer = t.empty(FRAME_SIZE, dtype=t.int32).cuda()

    print('agent loop: waiting')
    # time.sleep(.5)
    print('agent loop: now running')

    ioloop = IOLoop.current()
    while True:

        ## can await mouse, key, or any other q to trigger agent update
        try:
            mouse_move = await get_blocking(mouse_q)
        except Exception as e:
            print('agent proc: caught exception', type(e), ' : ', e, '; raising')
            raise e

        ## much lower latency to run these synchronously
        try: state = next(states)
        except: break

        t.ops.render_op.render_kernel(*state, z_buffer, f_buffer, lock_buffer)
        f_buff_cpu = f_buffer.cpu().numpy()
        frame_q.put_nowait(f_buff_cpu)

        await ioloop.run_in_executor(None, functools.partial(flush_q, mouse_q))
        await ioloop.run_in_executor(None, functools.partial(print_loc, mouse_move))

    for state in states: del_state(state)
    del states
    del z_buffer
    del f_buffer
    del lock_buffer
    event_end.wait()


###### Shutdown helpers
def kill_child_processes(parent_pid, sig=signal.SIGTERM):

    try: parent = psutil.Process(parent_pid)
    except psutil.NoSuchProcess: return

    children = parent.children(recursive=True)
    for child_proc in children:
        try:
            child_proc.send_signal(sig)
            print('sent', str(sig), 'to proc', child_proc.pid)
        except: continue

def handle_sig(sig, _):
    kill_child_processes(os.getpid())


###### Launch agent proc pool, server proc, and configure error handling
## NOTE: inter-process pipes can break at the OS level - randomly - and only when submitting run_server to the executor.
# If this happens, close all programs and kill all python processes manually - rebooting will not fix.
def setup_run():
    t.cuda.set_device(0)

    n_logi_cores = tornado.process.cpu_count()
    n_cores = n_logi_cores // 2
    n_srv_proc = (n_cores*3) // 4

    n_agt_proc = 1

    thd_per_proc = 2
    t.set_num_threads(thd_per_proc)

    print('Detected', n_logi_cores, 'logical cores')
    print('Running server with', n_srv_proc, 'processes')
    print('Running agent with', n_agt_proc, 'processes')
    print('Restricting torch to', thd_per_proc, 'threads per proc')

    man = mp.Manager()

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)
    if os.name == "posix":
        signal.signal(signal.SIGTSTP, handle_sig)

    try:
        with man:

            ## if needed, we can register a LIFO queue with a custom Manager class
            shared_obj = (man.Queue(), man.Queue(), man.Queue(), man.Event())

            proc = mp.Process(target=run_server.run_server, args=(shared_obj, n_srv_proc))
            proc.start()

            ## run cuda on the main process - much faster than setting 'spawn' as start method
            exec = concurrent.futures.ProcessPoolExecutor(max_workers=n_agt_proc)
            ioloop = IOLoop.current()
            ioloop.set_default_executor(exec)
            ioloop.run_sync(functools.partial(agent_loop, shared_obj))

    except Exception as e:
        print('main proc: caught exception', type(e), ' : ', e)

        kill_child_processes(os.getpid(), signal.SIGKILL)

        try:
            proc.close()
            print('main proc: sent CLOSE to server proc')
        except: pass
        time.sleep(1)
        try:
            proc.terminate()
            print('main proc: sent TERMINATE to server proc')
        except: pass
        time.sleep(1)
        try:
            proc.kill()
            print('main proc: sent KILL to server proc')
        except: pass

        print('main proc: shutting down object manager')
        try:
            man.shutdown()
            print('main proc: SUCCESS object manager SHUTDOWN')
        except: print('main proc: FAIL object manager DID NOT SHUTDOWN')
        print('main proc: shutting down agent process pool')
        try:
            exec.shutdown()
            print('main proc: SUCCESS agent executor proc-pool SHUTDOWN')
        except: print('main proc: FAIL agent executor proc-pool DID NOT SHUTDOWN')

        print('main proc: stopping agent ioloop')
        try:
            ioloop.add_callback_from_signal(functools.partial(ioloop, ioloop.stop))
            ioloop.add_callback_from_signal(functools.partial(ioloop, ioloop.close))
            print('main proc: SUCCESS agent ioloop SHUTDOWN')
        except: pass

        ## NOTE: this will print an OSError when run in a debugger
        print('shutdown complete')
        exit(0)



if __name__ == "__main__":
    setup_run()











