# Copyright (c) Microsoft. All rights reserved.

# Licensed under the MIT license. See LICENSE.md file in the project root
# for full license information.
# ==============================================================================

"""
Unit tests for evaluation operations, each operation is tested for
the forward and the backward pass
"""

from __future__ import division
import numpy as np
import pytest
from .ops_test_utils import sanitize_dtype_cntk, _test_binary_op, AA, I, precision, PRECISION_TO_TYPE,\
        unittest_helper

TARGET_OUT_PAIRS = [
    # (target_vector, output_vector)
    ([[0., 0., 0., 1]], [[1., 2., 3., 4.]]),
    ([[0., 0., 0.5, 0.5]], [[1., 2., 3., 4.]]),
    ([[0., 0.4, 0.3, 0.3]], [[2., 1., 1., 4.]])
]

@pytest.mark.parametrize("target_vector, output_vector", TARGET_OUT_PAIRS)
def test_op_cross_entropy_with_softmax(output_vector, target_vector, device_id, precision):
    dt = PRECISION_TO_TYPE[precision]

    o = AA(output_vector, dtype=dt)
    t = AA(target_vector, dtype=dt)

    ox = o - o.max()  # subtract max to avoid overflow
    exp_x = np.exp(ox)
    s_max = exp_x / np.sum(exp_x) # softmax function

    expected_forward = np.asarray(-np.sum(t * np.log(s_max, dtype=dt), dtype=dt))
    expected_forward.shape = (1,1,1,1) + expected_forward.shape

    s = np.sum(t, dtype=dt)
    backward = np.subtract(s_max * s, t)
    backward.shape = (1,1) + backward.shape

    expected_backward = {
        'left_arg':  backward,
        'right_arg': [[-1*o]]
    }

    from .. import cross_entropy_with_softmax
    _test_binary_op(precision, device_id, cross_entropy_with_softmax,
                    output_vector, target_vector,
                    expected_forward, expected_backward)

TARGET_OUT_PAIRS_WITH_AXIS = [
    # (target_vector, output_vector, axis)
    ([[0., 0., 0., 1]],
     [[1., 2., 3., 4.]], -1),
    ([[0., 0., 0.5, 0.5]],
     [[1., 2., 3., 4.]], 1),
    ([[0., 0.4, 0.3, 0.3]],
     [[2., 1., 1., 4.]], 1),
    ([[0., 0., 0., 1],
      [0., 0., 1., 0.]],
     [[1., 2., 3., 4.],
      [1., 2., 3., 5.]], 1),
    ([[0., 0., 0., 1],
      [0., 1., 0., 0.]],
     [[1., 2., 3., 4.],
      [1., 7., 3., 5.]], 1)
]

@pytest.mark.parametrize("target_vector, output_vector, axis", TARGET_OUT_PAIRS_WITH_AXIS)
def test_op_cross_entropy_with_softmax_and_axis(output_vector, target_vector, axis, device_id, precision):
    dt = PRECISION_TO_TYPE[precision]

    x = AA(output_vector, dtype=dt)
    t = AA(target_vector, dtype=dt)

    expected_forward = []
    expected_backward_left = []
    expected_backward_right = []

    for sample, target in zip(x, t):
        ox = sample - sample.max()  # subtract max to avoid overflow
        exp_x = np.exp(ox)
        s_max = exp_x / np.sum(exp_x) # softmax function
        forward = np.asarray(-np.sum(target * np.log(s_max, dtype=dt), dtype=dt))
        expected_forward.append(forward.tolist())

        s = np.sum(target, dtype=dt)
        backward = np.subtract(s_max * s, target)

        expected_backward_left.append(backward.tolist())
        expected_backward_right.append(-1*sample)

    expected_forward = [[np.reshape(AA(expected_forward, dtype=dt), (x.shape[0], 1))]]
    expected_backward_left = AA(expected_backward_left, dtype=dt)

    expected_backward = {
        'left_arg':  [[expected_backward_left]],
        'right_arg': [[expected_backward_right]]
    }

    from .. import cross_entropy_with_softmax
    _test_binary_op(precision, device_id, cross_entropy_with_softmax,
                    output_vector, target_vector,
                    expected_forward, expected_backward, op_param_dict={'axis': axis})

@pytest.mark.parametrize("target_vector, output_vector", TARGET_OUT_PAIRS)
def test_op_squared_error(output_vector, target_vector, device_id, precision):
    dt = PRECISION_TO_TYPE[precision]

    o = AA(output_vector, dtype=dt)
    t = AA(target_vector, dtype=dt)

    expected_forward = AA([[np.sum((t - o)**2)]])

    backward = 2 * np.subtract(o, t)
    expected_backward = {
        'left_arg':  [[backward]],
        'right_arg': [[-1*backward]]
    }

    from .. import squared_error
    _test_binary_op(precision, device_id, squared_error,
                    output_vector, target_vector,
                    expected_forward, expected_backward)

TARGET_OUT_PAIRS_CLASSIFICATION = [
    # (target_vector, output_vector, topN)
    ([[1., 0., 0., 0.]], [[1., 2., 3., 4.]], 1),
    ([[0., 0., 0., 1.]], [[1., 2., 3., 4.]], 1),
    ([[0., 1., 0., 0.]], [[1., 2., 3., 4.]], 3),
    ([[1., 0., 0., 0.]], [[1., 2., 3., 4.]], 3),
]

@pytest.mark.parametrize("target_vector, output_vector, topN", TARGET_OUT_PAIRS_CLASSIFICATION)
def test_op_classification_error(output_vector, target_vector, topN, device_id, precision):
    dt = PRECISION_TO_TYPE[precision]

    o = AA(output_vector, dtype=dt)
    t = AA(target_vector, dtype=dt)

    # loop topN times and compare positions between 1 in target and maximum in output
    temp_o = np.copy(o)
    max_in_different_position = False
    for i in range(topN):
        max_in_different_position = np.argmax(t) != np.argmax(temp_o)
        if not max_in_different_position:
            break
        temp_o[...,np.argmax(temp_o)] = 0.0

    expected_forward = AA([int(max_in_different_position)], dtype=dt)

    if topN == 1:
        expected_forward = [[[expected_forward]]]

    zero_backward = np.zeros_like(t, dtype=dt)
    left_backward = np.copy(zero_backward)
    
    zero_backward[..., np.argmax(o)] = -1.
    right_backward = zero_backward

    output_var = I(shape=o.shape,
          dtype=sanitize_dtype_cntk(precision),
          needs_gradient=True,
          name='output_var')

    target_var = I(shape=t.shape,
          dtype=sanitize_dtype_cntk(precision),
          needs_gradient=True,
          name='target_var')
    
    from .. import classification_error

    input_op_input = classification_error(output_var, target_var, topN=topN)

    o.shape = (1, 1) + o.shape
    t.shape = (1, 1) + t.shape

    forward_input = {output_var: o, target_var: t}

    # No backward pass expected for classification_error since it is only used in evaluation
    unittest_helper(input_op_input,
                    forward_input, expected_forward, expected_backward=None,
                    device_id=device_id, precision=precision)

TARGET_OUT_PAIRS_CLASSIFICATION_WITH_AXIS = [
    # (target_vector, output_vector, axis)
    ([[0., 1., 0., 0.],
      [0., 1., 0., 0.]],
     [[1., 2., 3., 4.],
      [1., 5., 3., 4.]], 1),
    ([[0., 1., 0., 0.],
      [0., 0., 1., 0.],
      [0., 1., 0., 0.]],
     [[1., 2., 3., 4.],
      [6., 2., 7., 4.],
      [1., 5., 3., 4.]], 1),
    ([[0., 0., 0.5, 0.5],
      [0., 0., 1., 0.],
      [0., 1., 0., 0.]],
     [[1., 2., 3., 4.],
      [6., 2., 7., 4.],
      [1., 5., 3., 4.]], 1),
]

@pytest.mark.parametrize("target_vector, output_vector, axis", TARGET_OUT_PAIRS_CLASSIFICATION_WITH_AXIS)
def test_op_classification_error_with_axis(output_vector, target_vector, axis, device_id, precision):
    dt = PRECISION_TO_TYPE[precision]

    x = AA(output_vector, dtype=dt)
    t = AA(target_vector, dtype=dt)

    forward = []
    expected_backward_left = []
    expected_backward_right = []

    for sample, target in zip(x, t):
        max_in_different_position = np.argmax(target) != np.argmax(sample)
        forward.append([int(max_in_different_position)])

        zero_backward = np.zeros_like(target, dtype=dt)

        expected_backward_left.append(zero_backward)
        expected_backward_right.append(zero_backward)

    forward = np.mean(forward)

    expected_forward = AA([[forward]], dtype=dt)
    expected_backward_left = AA([[expected_backward_left]], dtype=dt)
    expected_backward_right = AA([[expected_backward_right]], dtype=dt)

    expected_backward = {
        'left_arg':  expected_backward_left,
        'right_arg': expected_backward_right
    }

    from .. import classification_error
    _test_binary_op(precision, device_id, classification_error,
                    output_vector, target_vector,
                    expected_forward, expected_backward, op_param_dict={'axis':axis})

TARGET_BINARY_CE_OUT_PAIRS = [
    # (target_vector, output_vector, weights)
    ([[0., 1.0, 0.0, 0.0]], [[0.9, 0.9, 0.0001, 0.0001]], [[1.], [1.], [1.], [1.]]),
    #([[0., 1.0, 0.0, 0.0]], [[0.9, 0.9, 0.0001, 0.0001]], [[1.], [2.], [3.], [4.]]),
    #([[0., 0., 1., 1]], [[0.2, 0.4, 0.6, 0.8]], [[1.0],[2.0],[3.0],[4.0]]),
    #([[0., 0., 1.0, 0.]], [[0.8, 0.2, 0.75, 0.3]], [[1.5],[2.5],[3.5],[4.5]]),
]

@pytest.mark.parametrize("target_vector, output_vector, weight", TARGET_BINARY_CE_OUT_PAIRS)
def _test_op_binary_cross_entropy(output_vector, target_vector, weight, device_id):
    precision = 'float'
    dt = PRECISION_TO_TYPE[precision]

    x = AA(output_vector, dtype=dt)
    t = AA(target_vector, dtype=dt)

    forward = -np.sum((t*np.log(x))+(1-t)*np.log(1-x))

    expected_forward = AA([[forward]], dtype=dt)

    expected_forward.shape = (1,1) + expected_forward.shape

    expected_backward_left = -np.sum((t/x)+(1-t)/(1-x))

    expected_backward_right = -np.sum(np.log(x)-np.log(1-x))

    expected_backward = {
        'left_arg':  expected_backward_left,
        'right_arg': expected_backward_right
    }

    from .. import binary_cross_entropy
    _test_binary_op(precision, device_id, binary_cross_entropy,
                    output_vector, target_vector,
                    expected_forward, expected_backward)

@pytest.mark.parametrize("target_vector, output_vector, weight", TARGET_BINARY_CE_OUT_PAIRS)
def _test_op_weighted_binary_cross_entropy(output_vector, target_vector, weight, device_id, precision):
    dt = PRECISION_TO_TYPE[precision]

    x = AA(output_vector, dtype=dt)
    t = AA(target_vector, dtype=dt)
    w = AA(weight, dtype=dt)

    forward = -np.sum((t*np.log(x))+(1-t)*np.log(1-x))

    expected_forward = AA([[forward]], dtype=dt)
    expected_forward.shape = (1,1) + expected_forward.shape

    expected_backward_left = -np.sum((t/x)+(1-t)/(1-x))
    expected_backward_right = -np.sum(np.log(x)-np.log(1-x))

    expected_backward = {
        'left_arg':  expected_backward_left,
        'right_arg': expected_backward_right
    }

    a = I(shape=x.shape[1:],
          dtype=sanitize_dtype_cntk(precision),
          needs_gradient=True,
          name='a')

    b = I(shape=t.shape[1:],
          dtype=sanitize_dtype_cntk(precision),
          needs_gradient=True,
          name='b')

    weight_variable = I(shape=w.shape[1:],
                     dtype=sanitize_dtype_cntk(precision),
                     needs_gradient=True,
                     name='weight')

    from .. import weighted_binary_cross_entropy
    input_op_input = weighted_binary_cross_entropy(a, b, weight_variable)
 
    forward_input = {a: x, b: t, weight_variable: w}

    expected_backward = {a: expected_backward_left,
                         b: expected_backward_right}

    unittest_helper(input_op_input,
                    forward_input, expected_forward, expected_backward,
                    device_id=device_id, precision=precision)