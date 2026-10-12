from __future__ import annotations

import logging

import gradio as gr

from backend.args import dynamic_args
from modules import scripts
from modules.processing import StableDiffusionProcessing
from networks import available_network_aliases, available_networks

from regional_lora.core import RegionSpec, RegionalLoraModelWrapper


logger = logging.getLogger("anima_regional_lora")


def _resolve_lora(name: str) -> str:
    name = name.strip()
    item = available_network_aliases.get(name) or available_networks.get(name)
    if item is None:
        raise ValueError(f'LoRA "{name}" was not found. Refresh the LoRA list and check its alias.')
    return item.filename


class Script(scripts.Script):
    sorting_priority = 20

    def title(self):
        return "Anima Regional LoRA (experimental)"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Accordion("Anima Regional LoRA (experimental)", open=False):
            enabled = gr.Checkbox(False, label="Enable two-pass Regional LoRA")
            gr.Markdown(
                "Both LoRAs must also be present in the prompt as normal `<lora:...:...>` tags. "
                "Set **Diffusion in Low Bits** to an option ending in **(fp16 LoRA)**."
            )
            with gr.Row():
                left_lora = gr.Textbox(label="Left LoRA alias or filename", placeholder="CharacterA")
                left_strength = gr.Slider(0.0, 2.0, value=1.0, step=0.05, label="Left strength")
            with gr.Row():
                right_lora = gr.Textbox(label="Right LoRA alias or filename", placeholder="CharacterB")
                right_strength = gr.Slider(0.0, 2.0, value=1.0, step=0.05, label="Right strength")
            split = gr.Slider(0.1, 0.9, value=0.5, step=0.01, label="Left/right boundary")
            feather = gr.Slider(0.0, 0.3, value=0.05, step=0.01, label="Boundary feather")

        self.infotext_fields = [
            (enabled, "Anima Regional LoRA"),
            (left_lora, "Regional LoRA left"),
            (left_strength, "Regional LoRA left strength"),
            (right_lora, "Regional LoRA right"),
            (right_strength, "Regional LoRA right strength"),
            (split, "Regional LoRA boundary"),
            (feather, "Regional LoRA feather"),
        ]
        return [enabled, left_lora, left_strength, right_lora, right_strength, split, feather]

    def process_before_every_sampling(
        self,
        p: StableDiffusionProcessing,
        enabled: bool,
        left_lora: str,
        left_strength: float,
        right_lora: str,
        right_strength: float,
        split: float,
        feather: float,
        **kwargs,
    ):
        if not enabled:
            return
        if not dynamic_args.anima:
            logger.error("Anima Regional LoRA only supports Anima models")
            return
        if not dynamic_args.online_lora:
            logger.error(
                "Anima Regional LoRA requires on-the-fly LoRA. Select a "
                "'Diffusion in Low Bits' option ending in '(fp16 LoRA)' and reload the model."
            )
            return

        try:
            left_filename = _resolve_lora(left_lora)
            right_filename = _resolve_lora(right_lora)
            unet = p.sd_model.forge_objects.unet.clone()
            previous_wrapper = unet.model_options.get("model_function_wrapper")
            wrapper = RegionalLoraModelWrapper(
                unet=unet,
                left=RegionSpec(left_filename, left_strength),
                right=RegionSpec(right_filename, right_strength),
                split=split,
                feather=feather,
                previous_wrapper=previous_wrapper,
            )
            unet.set_model_unet_function_wrapper(wrapper)
            p.sd_model.forge_objects.unet = unet
            left_count, right_count = wrapper.match_counts
            p.extra_generation_params.update(
                {
                    "Regional LoRA passes": 2,
                    "Regional LoRA left patches": left_count,
                    "Regional LoRA right patches": right_count,
                }
            )
            logger.info(
                "Enabled two-pass Anima Regional LoRA: left=%s (%d patches), right=%s (%d patches)",
                left_lora,
                left_count,
                right_lora,
                right_count,
            )
        except Exception as exc:
            logger.error("Could not enable Anima Regional LoRA: %s", exc)
