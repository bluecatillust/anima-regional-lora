from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Iterable

import torch
import torch.nn.functional as F


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


def build_vertical_masks(
    height: int,
    split: float,
    feather: float,
    *,
    device: torch.device,
    dtype: torch.dtype,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Build complementary top/bottom masks with an optional soft boundary."""

    return build_horizontal_masks(height, split, feather, device=device, dtype=dtype)


def _prepare_custom_mask(
    custom_mask,
    height: int,
    width: int,
    feather: float,
    *,
    device: torch.device,
    dtype: torch.dtype,
) -> torch.Tensor:
    if custom_mask is None:
        raise ValueError("Custom mask mode requires a mask image")

    mask = torch.as_tensor(custom_mask, device=device)
    if mask.ndim == 3:
        if mask.shape[0] in (1, 3, 4) and mask.shape[-1] not in (1, 3, 4):
            mask = mask[:3].to(torch.float32).mean(dim=0)
        else:
            mask = mask[..., :3].to(torch.float32).mean(dim=-1)
    elif mask.ndim != 2:
        raise ValueError(f"Custom mask must be a 2D or RGB image, got shape {tuple(mask.shape)}")

    mask = mask.to(torch.float32)
    if mask.numel() == 0:
        raise ValueError("Custom mask is empty")
    if float(mask.max()) > 1.0 or float(mask.min()) < 0.0:
        mask = mask / 255.0
    mask = torch.nan_to_num(mask, nan=0.0, posinf=1.0, neginf=0.0).clamp(0.0, 1.0)
    mask = F.interpolate(
        mask.view(1, 1, *mask.shape),
        size=(height, width),
        mode="bilinear",
        align_corners=False,
    )

    feather = float(min(max(feather, 0.0), 1.0))
    if feather > 0.0:
        radius = max(1, round(feather * min(height, width) / 2.0))
        kernel_size = radius * 2 + 1
        mask = F.pad(mask, (radius, radius, radius, radius), mode="replicate")
        mask = F.avg_pool2d(mask, kernel_size=kernel_size, stride=1)

    return mask[0, 0].to(dtype=dtype)


def build_spatial_masks(
    height: int,
    width: int,
    mode: str,
    split: float,
    feather: float,
    *,
    custom_mask=None,
    device: torch.device,
    dtype: torch.dtype,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Build complementary Region A/B masks for the selected layout mode."""

    if height < 1 or width < 1:
        raise ValueError("height and width must be positive")

    normalised_mode = str(mode or "Horizontal").strip().lower()
    if normalised_mode == "horizontal":
        region_a, _ = build_horizontal_masks(width, split, feather, device=device, dtype=dtype)
        region_a = region_a.view(1, width).expand(height, width)
    elif normalised_mode == "vertical":
        region_a, _ = build_vertical_masks(height, split, feather, device=device, dtype=dtype)
        region_a = region_a.view(height, 1).expand(height, width)
    elif normalised_mode == "custom mask":
        region_a = _prepare_custom_mask(
            custom_mask,
            height,
            width,
            feather,
            device=device,
            dtype=dtype,
        )
    else:
        raise ValueError(f"Unknown region layout mode: {mode}")

    region_b = torch.ones_like(region_a) - region_a
    return region_a, region_b


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
        mode: str = "Horizontal",
        custom_mask=None,
        previous_wrapper: Callable | None = None,
    ):
        if _normalise_path(left.filename) == _normalise_path(right.filename):
            raise ValueError("Region A and Region B LoRAs must be different")

        self.unet = unet
        self.left = left
        self.right = right
        self.split = float(split)
        self.feather = float(feather)
        self.mode = str(mode or "Horizontal")
        self.custom_mask = custom_mask
        self.previous_wrapper = previous_wrapper
        self._mask_cache = {}

        wrappers = unet.weight_wrapper_patches
        self.left_patches = collect_named_patches(wrappers, left.filename)
        self.right_patches = collect_named_patches(wrappers, right.filename)
        if not self.left_patches:
            raise ValueError(f"Region A LoRA has no online model patches: {left.filename}")
        if not self.right_patches:
            raise ValueError(f"Region B LoRA has no online model patches: {right.filename}")

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

    def _get_masks(self, output: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        height, width = output.shape[-2:]
        cache_key = (height, width, str(output.device), output.dtype)
        masks = self._mask_cache.get(cache_key)
        if masks is None:
            masks = build_spatial_masks(
                height,
                width,
                self.mode,
                self.split,
                self.feather,
                custom_mask=self.custom_mask,
                device=output.device,
                dtype=output.dtype,
            )
            self._mask_cache[cache_key] = masks
        return masks

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

        left_mask, right_mask = self._get_masks(left_output)
        mask_shape = [1] * (left_output.ndim - 2) + list(left_mask.shape)
        left_mask = left_mask.view(mask_shape)
        right_mask = right_mask.view(mask_shape)
        return left_output * left_mask + right_output * right_mask
