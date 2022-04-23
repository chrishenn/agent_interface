from numba import njit, prange



###########################################################################################
###########################################################################################
###### CPU Rendering

@njit
def transform_rel_locs(imgs,child_mat,locs_rel,locs_abs,depths,z_buffer,f_buffer):

    ## row gives parent id. Must visit and process sequentially
    for row in range( child_mat.shape[0] ):
        curr_offs = locs_abs[row]

        ## col gives child of curr object, if col==1. Can be visited in parallel
        for col in range( child_mat.shape[1] ):
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

@njit(parallel=True)
def transform_and_render(imgs,img_sizes,child_mat,locs_rel,locs_abs,depths,z_buffer,f_buffer):
    z_buffer.fill(25555)
    f_buffer.fill(0)

    n_loops = len(imgs)

    ## row gives parent id. Must visit and process sequentially
    for row in range( child_mat.shape[0] ):
        curr_offs = locs_abs[row]

        ## col gives child of curr object, if col==1. Can be visited in parallel
        for col in range( child_mat.shape[1] ):
            if child_mat[row,col]:

                ## abs loc of child = child_rel_offs + parent_abs_loc
                locs_abs[col] = locs_rel[col] + curr_offs

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



if __name__ == "__main__":
    pass

    # print("cpu render: loading states from disk")
    # states = t.load('/home/chris/Documents/agent_interface/600_states.list')
    # states = to_numpy_state(states)
    # states = iter(states)
    #
    # z_buffer = np.empty(FRAME_SIZE, dtype=np.int32)
    # f_buffer = np.empty([*FRAME_SIZE,3], dtype=np.int32)