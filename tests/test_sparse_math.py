"""Test the sparse math code from ptwt.sparse_math."""
# Written by moritz ( @ wolter.tech ) in 2021
import numpy as np
import pytest
import scipy.signal
import torch
from scipy import misc
from src.ptwt.sparse_math import (
    construct_conv2d_matrix,
    construct_conv_matrix,
    construct_strided_conv2d_matrix,
    construct_strided_conv_matrix,
    sparse_kron,
)


def test_kron():
    """Test the implementation by evaluation.

    The example is taken from
    https://de.wikipedia.org/wiki/Kronecker-Produkt
    """
    a = torch.tensor([[1, 2], [3, 2], [5, 6]]).to_sparse()
    b = torch.tensor([[7, 8], [9, 0]]).to_sparse()
    sparse_result = sparse_kron(a, b)
    dense_result = torch.kron(a.to_dense(), b.to_dense())
    err = torch.sum(torch.abs(sparse_result.to_dense() - dense_result))
    condition = np.allclose(sparse_result.to_dense().numpy(), dense_result.numpy())
    print("error {:2.2f}".format(err), condition)
    assert condition


@pytest.mark.parametrize(
    "test_filter", [torch.rand([2]), torch.rand([3]), torch.rand([4])]
)
@pytest.mark.parametrize("input_signal", [torch.rand([8]), torch.rand([9])])
@pytest.mark.parametrize("padding", ["full", "same", "valid"])
def test_conv_matrix(
    test_filter: torch.Tensor, input_signal: torch.Tensor, padding: str
):
    """Test the 1d sparse convolution matrix code."""
    conv_matrix = construct_conv_matrix(test_filter, len(input_signal), padding)
    mm_conv_res = torch.sparse.mm(conv_matrix, input_signal.unsqueeze(-1)).squeeze()
    conv_res = scipy.signal.convolve(input_signal.numpy(), test_filter.numpy(), padding)
    error = np.sum(np.abs(conv_res - mm_conv_res.numpy()))
    print("1d conv matrix error", padding, error, len(test_filter), len(input_signal))
    assert np.allclose(conv_res, mm_conv_res.numpy())


@pytest.mark.parametrize(
    "test_filter",
    [
        torch.tensor([1.0, 0]),
        torch.rand([2]),
        torch.rand([3]),
        torch.rand([4]),
    ],
)
@pytest.mark.parametrize(
    "input_signal",
    [
        torch.tensor([0.0, 1, 2, 3, 4, 5, 6, 7]),
        torch.rand([8]),
        torch.rand([9]),
    ],
)
@pytest.mark.parametrize("mode", ["valid", "same"])
def test_strided_conv_matrix(test_filter, input_signal, mode):
    """Test the strided 1d sparse convolution matrix code."""
    strided_conv_matrix = construct_strided_conv_matrix(
        test_filter, len(input_signal), 2, mode
    )
    mm_conv_res = torch.sparse.mm(
        strided_conv_matrix, input_signal.unsqueeze(-1)
    ).squeeze()
    if mode == "same":
        height_offset = len(input_signal) % 2
        padding = (len(test_filter) // 2, len(test_filter) // 2 - 1 + height_offset)
        input_signal = torch.nn.functional.pad(input_signal, padding)

    torch_conv_res = torch.nn.functional.conv1d(
        input_signal.unsqueeze(0).unsqueeze(0),
        test_filter.flip(0).unsqueeze(0).unsqueeze(0),
        stride=2,
    ).squeeze()
    error = torch.sum(torch.abs(mm_conv_res - torch_conv_res))
    print(
        "filter shape {:2}".format(tuple(test_filter.shape)[0]),
        "signal shape {:2}".format(tuple(input_signal.shape)[0]),
        "error {:2.2e}".format(error.item()),
    )
    assert np.allclose(mm_conv_res.numpy(), torch_conv_res.numpy())


@pytest.mark.parametrize(
    "filter_shape",
    [
        (2, 2),
        (3, 3),
        (3, 2),
        (2, 3),
        (5, 3),
        (3, 5),
        (2, 5),
        (5, 2),
        (4, 4),
    ],
)
@pytest.mark.parametrize(
    "size",
    [
        (5, 5),
        (10, 10),
        (16, 16),
        (8, 16),
        (16, 8),
        (16, 7),
        (7, 16),
        (15, 15),
    ],
)
@pytest.mark.parametrize("mode", ["same", "full", "valid"])
def test_conv_matrix_2d(filter_shape, size, mode):
    """Test the validity of the 2d convolution matrix code.

    It should be equivalent to signal convolve2d.
    """
    test_filter = torch.rand(filter_shape)
    test_filter = test_filter.unsqueeze(0).unsqueeze(0)
    face = misc.face()[256 : (256 + size[0]), 256 : (256 + size[1])]
    face = np.mean(face, -1).astype(np.float32)
    res_scipy = scipy.signal.convolve2d(face, test_filter.squeeze().numpy(), mode=mode)

    face = torch.from_numpy(face)
    face = face.unsqueeze(0).unsqueeze(0)
    conv_matrix2d = construct_conv2d_matrix(
        test_filter.squeeze(), size[0], size[1], mode=mode
    )
    res_flat = torch.sparse.mm(conv_matrix2d, face.T.flatten().unsqueeze(-1))
    res_mm = torch.reshape(res_flat, [res_scipy.shape[1], res_scipy.shape[0]]).T

    diff_scipy = np.mean(np.abs(res_scipy - res_mm.numpy()))
    print(
        str(size).center(8),
        filter_shape,
        mode.center(5),
        "scipy-error %2.2e" % diff_scipy,
        np.allclose(res_scipy, res_mm.numpy()),
    )
    assert np.allclose(res_scipy, res_mm)


@pytest.mark.slow
@pytest.mark.parametrize("filter_shape", [(3, 3), (2, 2), (4, 4), (3, 2), (2, 3)])
@pytest.mark.parametrize(
    "size",
    [
        (14, 14),
        (8, 16),
        (16, 8),
        (17, 8),
        (8, 17),
        (7, 7),
        (7, 8),
        (8, 7),
    ],
)
@pytest.mark.parametrize("mode", ["full", "valid"])
def test_strided_conv_matrix_2d(filter_shape, size, mode):
    """Test strided convolution matrices with full and valid padding."""
    test_filter = torch.rand(filter_shape)
    test_filter = test_filter.unsqueeze(0).unsqueeze(0)
    face = misc.face()[256 : (256 + size[0]), 256 : (256 + size[1])]
    face = np.mean(face, -1)
    face = torch.from_numpy(face.astype(np.float32))
    face = face.unsqueeze(0).unsqueeze(0)

    if mode == "full":
        padding = (filter_shape[0] - 1, filter_shape[1] - 1)
    elif mode == "valid":
        padding = (0, 0)
    torch_res = torch.nn.functional.conv2d(
        face, test_filter.flip(2, 3), padding=padding, stride=2
    ).squeeze()

    strided_matrix = construct_strided_conv2d_matrix(
        test_filter.squeeze(), size[0], size[1], stride=2, mode=mode
    )
    res_flat_stride = torch.sparse.mm(strided_matrix, face.T.flatten().unsqueeze(-1))

    if mode == "full":
        output_shape = [
            int(np.ceil((filter_shape[1] + size[1] - 1) / 2)),
            int(np.ceil((filter_shape[0] + size[0] - 1) / 2)),
        ]
    elif mode == "valid":
        output_shape = [
            (size[1] - (filter_shape[1])) // 2 + 1,
            (size[0] - (filter_shape[0])) // 2 + 1,
        ]
    res_mm_stride = np.reshape(res_flat_stride, output_shape).T

    diff_torch = np.mean(np.abs(torch_res.numpy() - res_mm_stride.numpy()))
    print(
        str(size).center(8),
        filter_shape,
        mode.center(8),
        "torch-error %2.2e" % diff_torch,
        np.allclose(torch_res.numpy(), res_mm_stride.numpy()),
    )
    assert np.allclose(torch_res.numpy(), res_mm_stride.numpy())


@pytest.mark.parametrize("filter_shape", [(3, 3), (4, 4), (4, 3), (3, 4)])
@pytest.mark.parametrize(
    "size", [(7, 8), (8, 7), (7, 7), (8, 8), (16, 16), (8, 16), (16, 8)]
)
def test_strided_conv_matrix_2d_same(filter_shape, size):
    """Test strided conv matrix with same padding."""
    stride = 2
    test_filter = torch.rand(filter_shape)
    test_filter = test_filter.unsqueeze(0).unsqueeze(0)
    face = misc.face()[256 : (256 + size[0]), 256 : (256 + size[1])]
    face = np.mean(face, -1)
    face = torch.from_numpy(face.astype(np.float32))
    face = face.unsqueeze(0).unsqueeze(0)
    padding = _get_2d_same_padding(filter_shape, size)
    face_pad = torch.nn.functional.pad(face, padding)
    torch_res = torch.nn.functional.conv2d(
        face_pad, test_filter.flip(2, 3), stride=stride
    ).squeeze()
    strided_matrix = construct_strided_conv2d_matrix(
        test_filter.squeeze(),
        face.shape[-2],
        face.shape[-1],
        stride=stride,
        mode="same",
    )
    res_flat_stride = torch.sparse.mm(strided_matrix, face.T.flatten().unsqueeze(-1))
    output_shape = torch_res.shape
    res_mm_stride = np.reshape(res_flat_stride, (output_shape[1], output_shape[0])).T
    diff_torch = np.mean(np.abs(torch_res.numpy() - res_mm_stride.numpy()))
    print(
        str(size).center(8),
        filter_shape,
        tuple(output_shape),
        "torch-error %2.2e" % diff_torch,
        np.allclose(torch_res.numpy(), res_mm_stride.numpy()),
    )


def _get_2d_same_padding(filter_shape, input_size):
    height_offset = input_size[0] % 2
    width_offset = input_size[1] % 2
    padding = (
        filter_shape[1] // 2,
        filter_shape[1] // 2 - 1 + width_offset,
        filter_shape[0] // 2,
        filter_shape[0] // 2 - 1 + height_offset,
    )
    return padding
