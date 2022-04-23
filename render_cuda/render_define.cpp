#include <torch/script.h>

#include <vector>
#include <iostream>
#include <string>

std::vector<torch::Tensor> render_call(
    std::vector<torch::Tensor> imgs,
    torch::Tensor img_sizes,
    torch::Tensor child_mat,
    torch::Tensor locs_rel,
    torch::Tensor locs_abs,
    torch::Tensor depths,

    torch::Tensor z_buffer,
    torch::Tensor f_buffer,
    torch::Tensor lock_buffer
);

#define CHECK_CUDA(x) AT_ASSERTM(x.is_cuda(), #x " must be a CUDA tensor")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x " must be contiguous")
#define CHECK_INPUT(x) CHECK_CUDA(x); CHECK_CONTIGUOUS(x)

std::vector<torch::Tensor> render(
    std::vector<torch::Tensor> imgs,
    torch::Tensor img_sizes,
    torch::Tensor child_mat,
    torch::Tensor locs_rel,
    torch::Tensor locs_abs,
    torch::Tensor depths,

    torch::Tensor z_buffer,
    torch::Tensor f_buffer,
    torch::Tensor lock_buffer
    )
{
    for (int i = 0; i < imgs.size(); i++) { CHECK_INPUT(imgs[i]); }
    CHECK_INPUT(img_sizes);
    CHECK_INPUT(child_mat);
    CHECK_INPUT(locs_rel);
    CHECK_INPUT(locs_abs);
    CHECK_INPUT(depths);

    CHECK_INPUT(z_buffer);
    CHECK_INPUT(f_buffer);
    CHECK_INPUT(lock_buffer);

    return render_call(
        imgs,
        img_sizes,
        child_mat,
        locs_rel,
        locs_abs,
        depths,

        z_buffer,
        f_buffer,
        lock_buffer
    );
}

TORCH_LIBRARY(render_op, m) {
    m.def("render_kernel", render);
}