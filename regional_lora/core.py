from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Iterable

import torch


def _normalise_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def collect_named_patches(weight_wrapper_patches: dict, filename: str) -> list:
    """Return every online LoRA patch belonging to ``filename``.

    Forge stores one OnlineLoRAPatch per affected model weight.  The same LoRA
    therefore appears many times in ``weight_wrapper_patches``.
    """

    wanted = _normalise_path(filename)
    matches = []
    seen = set()
    for patches in weight_wrapper_patches.values():
        for patch in patches:
            if id(patch) in seen:
                continue
            name = getattr(patch, "name", None)
            if name and _normalise_path(name) == wanted:
                matches.append(patch)
                seen.add(id(patch))
    return matches


def build_horizontal_masks(
    width: int,
    split: float,
    feather: float,
    *,
    device: torch.device,
    dtype: torch.dtype,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Build complementary left/right masks with an optional soft boundary."""

    if width < 1:
        raise ValueError("width must be positive")
    split = float(min(max(split, 0.0), 1.0))
    feather = float(min(max(feather, 0.0), 1.0))
    x = (torch.arange(width, device=device, dtype=torch.float32) + 0.5) / width

    if feather <= 0.0:
        left = (x < split).to(dtype=dtype)
    else:
        left = ((split + feather / 2.0 - x) / feather).clamp(0.0, 1.0).to(dtype=dtype)

    right = torch.ones_like(left) - left
    return left, right


@dataclass(frozen=True)
class RegionSpec:
    filename: str
    strength: float


class RegionalLoraModelWrapper:
    """Run the diffusion model once per LoRA and blend predictions spatially.

    Only the selected online LoRA patches are toggled. Other globally loaded
    LoRAs keep their original strengths in both passes.
    """

    def __init__(
        self,
        *,
        unet,
        left: RegionSpec,
        right: RegionSpec,
        split: float = 0.5,
        feather: float = 0.05,
        previous_wrapper: Callable | None = None,
    ):
        if _normalise_path(left.filename) == _normalise_path(right.filename):
            raise ValueError("left and right LoRAs must be different")

        self.unet = unet
        self.left = left
        self.right = right
        self.split = float(split)
        self.feather = float(feather)
        self.previous_wrapper = previous_wrapper

        wrappers = unet.weight_wrapper_patches
        self.left_patches = collect_named_patches(wrappers, left.filename)
        self.right_patches = collect_named_patches(wrappers, right.filename)
        if not self.left_patches:
            raise ValueError(f"left LoRA has no online model patches: {left.filename}")
        if not self.right_patches:
            raise ValueError(f"right LoRA has no online model patches: {right.filename}")

    @property
    def match_counts(self) -> tuple[int, int]:
        return len(self.left_patches), len(self.right_patches)

    def _all_regional_patches(self) -> Iterable:
        yield from self.left_patches
        yield from self.right_patches

    @staticmethod
    def _strength(patch) -> float:
        return float(patch.patch[0][0])

    @staticmethod
    def _set_strength(patches: Iterable, strength: float) -> None:
        for patch in patches:
            patch.patch[0][0] = float(strength)

    def _invoke(self, model_function: Callable, kwargs: dict) -> torch.Tensor:
        if self.previous_wrapper is not None:
            return self.previous_wrapper(model_function, kwargs)
        return model_function(kwargs["input"], kwargs["timestep"], **kwargs["c"])

    def __call__(self, model_function: Callable, kwargs: dict) -> torch.Tensor:
        originals = [(patch, self._strength(patch)) for patch in self._all_regional_patches()]
        try:
            self._set_strength(self.left_patches, self.left.strength)
            self._set_strength(self.right_patches, 0.0)
            left_output = self._invoke(model_function, kwargs)

            self._set_strength(self.left_patches, 0.0)
            self._set_strength(self.right_patches, self.right.strength)
            right_output = self._invoke(model_function, kwargs)
        finally:
            for patch, strength in originals:
                patch.patch[0][0] = strength

        if left_output.shape != right_output.shape:
            raise RuntimeError("regional LoRA passes returned different shapes")
        if left_output.ndim < 4:
            raise RuntimeError(f"expected an image-like model output, got {left_output.shape}")

        left_mask, right_mask = build_horizontal_masks(
            left_output.shape[-1],
            self.split,
            self.feather,
            device=left_output.device,
            dtype=left_output.dtype,
        )
        mask_shape = [1] * left_output.ndim
        mask_shape[-1] = left_output.shape[-1]
        left_mask = left_mask.view(mask_shape)
        right_mask = right_mask.view(mask_shape)
        return left_output * left_mask + right_output * right_mask
