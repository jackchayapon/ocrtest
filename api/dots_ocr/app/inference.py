import asyncio
import gc
import io
import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from PIL import Image, UnidentifiedImageError

from app.errors import ServiceError
from app.config import MODELS
from app.integrity import verify_snapshot
from app.prompt import LAYOUT_PROMPT
from app.schemas import parse_output


def decode_image(content, settings):
    if not content:
        raise ServiceError("IMAGE_REQUIRED", "Upload a nonempty image.")
    if len(content) > settings.max_upload_bytes:
        raise ServiceError("PAYLOAD_TOO_LARGE", "Image exceeds the upload limit.", 413)
    if content.startswith(b"%PDF-"):
        raise ServiceError(
            "UNSUPPORTED_MEDIA_TYPE",
            "PDF rendering is not implemented; upload a page image.",
            415,
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ServiceError(
                        "UNSUPPORTED_MEDIA_TYPE", "Use PNG, JPEG or WebP.", 415
                    )
                width, height = source.size
                if (
                    width * height > settings.max_pixels
                    or max(width, height) > settings.max_dimension
                ):
                    raise ServiceError(
                        "IMAGE_TOO_LARGE",
                        "Image exceeds the pixel or dimension limit.",
                        413,
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise ServiceError(
                        "ANIMATED_IMAGE", "Upload a single static image.", 415
                    )
                source.load()
                return source.convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ServiceError(
            "IMAGE_TOO_LARGE", "Image exceeds decoder limits.", 413
        ) from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise ServiceError(
            "INVALID_IMAGE", "The uploaded image cannot be decoded."
        ) from None


class TransformersReader:
    def __init__(self, settings):
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM, AutoProcessor

        self.torch, self.settings = torch, settings
        torch.set_num_threads(settings.cpu_threads)
        self.device = settings.device
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = settings.dtype
        if dtype == "auto":
            dtype = "bfloat16" if self.device.startswith("cuda") else "float32"
        self.dtype = dtype
        config = AutoConfig.from_pretrained(
            settings.model_dir, trust_remote_code=True, local_files_only=True
        )
        config.vision_config.attn_implementation = settings.attention
        self.processor = AutoProcessor.from_pretrained(
            settings.model_dir,
            trust_remote_code=True,
            local_files_only=True,
            use_fast=False,
            min_pixels=3136,
            max_pixels=settings.model_max_pixels,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            settings.model_dir,
            config=config,
            trust_remote_code=True,
            local_files_only=True,
            torch_dtype=getattr(torch, dtype),
            attn_implementation=settings.attention,
            device_map=self.device,
            low_cpu_mem_usage=True,
        ).eval()

    def read(self, image):
        from transformers import StoppingCriteria, StoppingCriteriaList

        settings, torch = self.settings, self.torch
        deadline = time.monotonic() + settings.inference_timeout_seconds

        class Deadline(StoppingCriteria):
            expired = False

            def __call__(self, input_ids, scores, **kwargs):
                self.expired = time.monotonic() >= deadline
                return self.expired

        stop = Deadline()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": LAYOUT_PROMPT},
                ],
            }
        ]
        prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.processor(
            text=[prompt], images=[image], padding=True, return_tensors="pt"
        )
        grid = inputs.image_grid_thw[0].tolist()
        patch = self.model.config.vision_config.patch_size
        model_size = (grid[2] * patch, grid[1] * patch)
        if model_size[0] * model_size[1] > settings.model_max_pixels:
            raise ServiceError(
                "PROCESSOR_LIMIT", "Processor exceeded the configured pixel limit.", 503
            )
        inputs = inputs.to(self.device)
        with torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=settings.max_new_tokens,
                do_sample=False,
                stopping_criteria=StoppingCriteriaList([stop]),
            )
        tokens = generated[0, inputs.input_ids.shape[1] :]
        raw = self.processor.decode(
            tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        if stop.expired:
            raise ServiceError(
                "INFERENCE_TIMEOUT", "Model inference exceeded its deadline.", 504
            )
        eos = self.model.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        if len(tokens) >= settings.max_new_tokens and int(tokens[-1]) not in eos:
            raise ServiceError(
                "OUTPUT_TRUNCATED", "Model output reached the token limit.", 502
            )
        return raw, model_size

    def close(self):
        del self.model
        del self.processor
        gc.collect()
        if self.device.startswith("cuda"):
            self.torch.cuda.empty_cache()


class VLLMReader:
    """Optional Linux CUDA runtime using the official vLLM model implementation."""

    def __init__(self, settings):
        from transformers import AutoTokenizer
        from vllm import LLM, SamplingParams

        if settings.device == "cpu":
            raise ValueError("This vLLM profile requires CUDA")
        self.device, self.dtype = (
            "cuda",
            "bfloat16" if settings.dtype == "auto" else settings.dtype,
        )
        self.settings = settings
        self.tokenizer = AutoTokenizer.from_pretrained(
            settings.model_dir, trust_remote_code=True, local_files_only=True
        )
        self.chat_template = json.loads(
            (settings.model_dir / "chat_template.json").read_text()
        )["chat_template"]
        self.parameters = SamplingParams(
            temperature=0, max_tokens=settings.max_new_tokens
        )
        self.model = LLM(
            model=str(settings.model_dir),
            trust_remote_code=True,
            dtype=self.dtype,
            max_model_len=settings.max_new_tokens + 4096,
            max_num_seqs=1,
            gpu_memory_utilization=settings.gpu_memory_utilization,
            enforce_eager=True,
            mm_processor_kwargs={
                "min_pixels": 3136,
                "max_pixels": settings.model_max_pixels,
            },
        )

    def read(self, image):
        from qwen_vl_utils.vision_process import smart_resize

        height, width = smart_resize(
            image.height,
            image.width,
            factor=28,
            min_pixels=3136,
            max_pixels=self.settings.model_max_pixels,
        )
        with image.resize((width, height)) as resized:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": LAYOUT_PROMPT},
                    ],
                }
            ]
            prompt = self.tokenizer.apply_chat_template(
                messages,
                chat_template=self.chat_template,
                tokenize=False,
                add_generation_prompt=True,
            )
            result = self.model.generate(
                {"prompt": prompt, "multi_modal_data": {"image": resized}},
                sampling_params=self.parameters,
                use_tqdm=False,
            )[0].outputs[0]
        if result.finish_reason == "length":
            raise ServiceError(
                "OUTPUT_TRUNCATED", "Model output reached the token limit.", 502
            )
        return result.text, (width, height)

    def close(self):
        # This method is verified against the pinned vLLM 0.17.1 profile.
        self.model.llm_engine.engine_core.shutdown()
        del self.model
        gc.collect()
        import torch

        if torch.distributed.is_initialized():
            torch.distributed.destroy_process_group()
        torch.cuda.empty_cache()


class Inference:
    def __init__(self, settings, loader=None):
        self.settings = settings
        self.loader = loader
        self.reader = None
        self.pending = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dots-ocr")
        self.load_seconds = None

    def initialize(self):
        started = time.monotonic()
        if self.loader:
            self.reader = self.loader(self.settings)
        else:
            identity = json.loads(
                (self.settings.model_dir / "snapshot-identity.json").read_text()
            )
            if identity != {
                "model": self.settings.model_id,
                "revision": self.settings.revision,
            }:
                raise ValueError("Snapshot identity mismatch")
            verify_snapshot(self.settings.model_dir, MODELS[self.settings.model_id])
            reader = (
                VLLMReader if self.settings.backend == "vllm" else TransformersReader
            )
            self.reader = reader(self.settings)
        self.load_seconds = time.monotonic() - started

    def submit(self, content):
        if self.pending is not None and not self.pending.done():
            raise ServiceError(
                "SERVICE_BUSY", "The model is still processing an earlier request.", 429
            )
        self.pending = asyncio.get_running_loop().run_in_executor(
            self.executor, self.read, content
        )
        self.pending.add_done_callback(
            lambda future: future.exception() if not future.cancelled() else None
        )
        return self.pending

    def close(self):
        if self.reader is not None:
            close = getattr(self.reader, "close", None)
            if close:
                close()
            self.reader = None

    def read(self, content):
        try:
            with closing(decode_image(content, self.settings)) as image:
                raw, model_size = self.reader.read(image)
                return parse_output(raw, image.size, model_size)
        except MemoryError:
            gc.collect()
            raise ServiceError(
                "RESOURCE_EXHAUSTED", "Inference memory is exhausted.", 503
            ) from None
        except ServiceError:
            raise
        except Exception as error:
            # CUDA exceptions are imported only after real inference is enabled.
            if type(error).__name__ == "OutOfMemoryError":
                gc.collect()
                import torch

                torch.cuda.empty_cache()
                raise ServiceError(
                    "RESOURCE_EXHAUSTED", "Accelerator memory is exhausted.", 503
                ) from None
            raise ServiceError(
                "MODEL_INFERENCE_FAILED", "The model could not process this image.", 502
            ) from None
