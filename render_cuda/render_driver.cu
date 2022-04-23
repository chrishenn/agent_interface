/**
Authors: Christian Henn, Qianli Liao
**/

#include <torch/types.h>

#include <cuda.h>
#include <cuda_runtime.h>

#include <vector>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cassert>
#include <iostream>

// define for error checking
//#define CUDA_ERROR_CHECK

#define CudaCheckError() __cudaCheckError( __FILE__, __LINE__ )
inline void __cudaCheckError( const char *file, const int line )
{
#ifdef CUDA_ERROR_CHECK
    do{
        cudaError err = cudaGetLastError();
        if ( cudaSuccess != err )
        {
            fprintf( stderr, "cudaCheckError() failed at %s:%i : %s\n",
                     file, line, cudaGetErrorString( err ) );
            exit( -1 );
        }

        err = cudaDeviceSynchronize();
        if( cudaSuccess != err )
        {
            fprintf( stderr, "cudaCheckError() with sync failed at %s:%i : %s\n",
                     file, line, cudaGetErrorString( err ) );
            exit( -1 );
        }
    } while(0);
#endif

    return;
}




const int BUFF_W = 1920;
const int BUFF_H = 1080;
const int BUFF_D = 3;

const int Z_MAX = 268435455;


__global__ void render_kernel(
        const u_int8_t** img_ptrs,
        const int* img_sizes,
        const int* depths,
        const int* locs_abs,

        int* z_buffer,
        int* f_buffer,
        int* lock_buffer
){

    // each block takes one image at img_ptr_i - of size img_size0 x img_size1 x 3
    const auto img_i = blockIdx.x;

    const auto img_ptr_i = img_ptrs[img_i];

    const auto img_size_0 = img_sizes[img_i * 2 + 0];
    const auto img_size_1 = img_sizes[img_i * 2 + 1];

    // convert to per-pixel depth when rendering 3D
    const auto im_depth = depths[img_i];

    const auto im_start_y = locs_abs[img_i * 2 + 0];
    const auto im_start_x = locs_abs[img_i * 2 + 1];


    // loop over pixels in block's image at img_ptr in x and y, for all 3 channels
    for (int im_row = threadIdx.x; im_row < img_size_0; im_row += blockDim.x){

        auto buff_y = im_start_y + im_row;
        if ( buff_y < 0 ) continue;
        if ( buff_y >= BUFF_H ) break;

        for (int im_col = 0; im_col < img_size_1; im_col++){

            auto buff_x = im_start_x + im_col;
            if ( buff_x < 0 ) continue;
            if ( buff_x >= BUFF_W ) break;

            // If my thread's z-depth is < the current value at my loc in z_buff: update z_buff, write my pixel value to f_buff
            // z-buff comparison and write must be atomic on this pixel in buffs
            bool holding_lock;
            do {
                holding_lock = (atomicCAS(&lock_buffer[buff_y * BUFF_W + buff_x], 0, -1) == 0);

                if (holding_lock)
                {
                    // z_buff is H x W
                    auto curr_z = z_buffer[buff_y * BUFF_W + buff_x];

                    if (im_depth < curr_z) {

                        z_buffer[buff_y * BUFF_W + buff_x] = im_depth;

                        // write pixel at this buff_loc to f_buff
                        // #pragma unroll
                        for (int chan = 0; chan < BUFF_D; chan++) {

                            auto lin_im_loc = (im_row * img_size_1 * BUFF_D) + (im_col * BUFF_D) + chan;
                            auto val = img_ptr_i[lin_im_loc];

                            // f_buff is H x W x D
                            auto lin_buff_loc = (buff_y * BUFF_W * BUFF_D) + (buff_x * BUFF_D) + chan;
                            f_buffer[lin_buff_loc] = val;
                        }
                    }
                    atomicExch(&lock_buffer[buff_y * BUFF_W + buff_x], 0);
                }

            } while (!holding_lock);
        }
    }

}

__global__ void transform_locs(
        const u_int8_t* child_mat,
        const int child_mat_size0,
        const int child_mat_size1,

        const int* locs_rel,
        int* locs_abs

){
    // locs_rel and locs_abs have width == 2

    // for each parent with id == row. cannot be visited in parallel.
    for (int row = 0; row < child_mat_size0; row++){
        auto curr_offs_0 = locs_abs[row * 2 + 0];
        auto curr_offs_1 = locs_abs[row * 2 + 1];

        // col gives id of child of curr object, if child_mat[row][col]==1. Can be visited in parallel
        for (int col = threadIdx.x; col < child_mat_size1; col += blockDim.x){

            if (!child_mat[row * child_mat_size1 + col]) continue;

            // abs loc of child = child_rel_offs + parent_abs_loc
            auto target_rel_0 = locs_rel[col * 2 + 0];
            auto target_rel_1 = locs_rel[col * 2 + 1];

            target_rel_0 += curr_offs_0;
            target_rel_1 += curr_offs_1;

            locs_abs[col * 2 + 0] = target_rel_0;
            locs_abs[col * 2 + 1] = target_rel_1;
        }
    }
}



__host__ std::vector<torch::Tensor> render_call(
    std::vector<torch::Tensor> imgs,
    torch::Tensor img_sizes,
    torch::Tensor child_mat,
    torch::Tensor locs_rel,
    torch::Tensor locs_abs,
    torch::Tensor depths,

    torch::Tensor z_buffer,
    torch::Tensor f_buffer,
    torch::Tensor lock_buffer
) {

    using namespace torch::indexing;
    auto device_id = child_mat.get_device();
    cudaSetDevice(device_id);

    // convert std::vector of imgs into an array of device pointers, to pass to device code
    u_int8_t** img_ptrs;
    cudaMalloc((void**) &img_ptrs, imgs.size() * sizeof(u_int8_t*));

    u_int8_t** tmp_d_ptrs = (u_int8_t**) malloc(imgs.size() * sizeof(u_int8_t*));
    for (int i = 0; i < imgs.size(); i++){
        tmp_d_ptrs[i] = imgs[i].data_ptr<u_int8_t>();
    }
    cudaMemcpy(img_ptrs, tmp_d_ptrs, imgs.size() * sizeof(u_int8_t*), cudaMemcpyHostToDevice);

    // refresh persistent buffers
    z_buffer.fill_(Z_MAX);
    f_buffer.fill_(0);
    lock_buffer.fill_(0);

    // transform relative locs to abs locs within the f_buff
    auto threads = child_mat.size(1);
    transform_locs<<<1,threads>>>(
        child_mat.data_ptr<u_int8_t>(),
        child_mat.size(0),
        child_mat.size(1),

        locs_rel.data_ptr<int>(),
        locs_abs.data_ptr<int>()
    );

    // render imgs onto f_buff
    auto n_threads = 256;
    render_kernel<<<imgs.size(),n_threads>>>(
        img_ptrs,
        img_sizes.data_ptr<int>(),
        depths.data_ptr<int>(),
        locs_abs.data_ptr<int>(),

        z_buffer.data_ptr<int>(),
        f_buffer.data_ptr<int>(),
        lock_buffer.data_ptr<int>()
    );

    return {};
}



