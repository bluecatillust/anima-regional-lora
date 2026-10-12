from __future__ import annotations

import os
import sys
from types import SimpleNamespace
import unittest

import torch


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from regional_lora.core import RegionSpec, RegionalLoraModelWrapper, build_horizontal_masks


class FakePatch:
    def __init__(self, name: str, strength: float):
        self.name = name
        self.patch = [[strength]]


class CoreTests(unittest.TestCase):
    def test_masks_are_complementary(self):
        left, right = build_horizontal_masks(16, 0.5, 0.2, device=torch.device("cpu"), dtype=torch.float32)
        self.assertTrue(torch.allclose(left + right, torch.ones(16)))
        self.assertEqual(left[0], 1)
        self.assertEqual(right[-1], 1)

    def test_two_pass_blend_and_restore_strengths(self):
        left_name = os.path.join(os.getcwd(), "left.safetensors")
        right_name = os.path.join(os.getcwd(), "right.safetensors")
        left_patch = FakePatch(left_name, 0.25)
        right_patch = FakePatch(right_name, 0.75)
        unet = SimpleNamespace(weight_wrapper_patches={"a": [left_patch], "b": [right_patch]})
        wrapper = RegionalLoraModelWrapper(
            unet=unet,
            left=RegionSpec(left_name, 2.0),
            right=RegionSpec(right_name, 3.0),
            split=0.5,
            feather=0.0,
        )

        def model_function(x, timestep, **c):
            value = left_patch.patch[0][0] + right_patch.patch[0][0]
            return torch.full_like(x, value)

        output = wrapper(
            model_function,
            {"input": torch.zeros(1, 1, 2, 4), "timestep": torch.tensor([1.0]), "c": {}},
        )
        self.assertTrue(torch.equal(output[..., :2], torch.full((1, 1, 2, 2), 2.0)))
        self.assertTrue(torch.equal(output[..., 2:], torch.full((1, 1, 2, 2), 3.0)))
        self.assertEqual(left_patch.patch[0][0], 0.25)
        self.assertEqual(right_patch.patch[0][0], 0.75)


if __name__ == "__main__":
    unittest.main()
