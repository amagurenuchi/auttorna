"""Export a trusted RF-DETR checkpoint to the fixed-shape runtime model."""

from pathlib import Path
import sys


def export_model(weights: str | Path = "weights.pt", output: str | Path = "model.onnx",
                 variant: str = "nano", labels: list[str] | None = None,
                 resolution: int = 384, patch_size: int = 16) -> Path:
    labels = labels or ["receptor", "arrow"]
    try:
        import torch
    except ImportError as error:
        raise RuntimeError("Install export dependencies with: python -m pip install -e '.[export]'") from error
    try:
        from rfdetr import RFDETRBase, RFDETRLarge, RFDETRMedium, RFDETRNano, RFDETRSmall
    except ImportError as error:
        raise RuntimeError("Install export dependencies with: python -m pip install -e '.[export]'") from error
    architectures = {"nano": RFDETRNano, "small": RFDETRSmall, "medium": RFDETRMedium, "base": RFDETRBase, "large": RFDETRLarge}
    if variant not in architectures:
        raise ValueError(f"unsupported RF-DETR variant: {variant}")
    weights_path = Path(weights).expanduser().resolve()
    if not weights_path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {weights_path}")
    block_size = patch_size * 4
    shape = ((int(resolution) + block_size - 1) // block_size) * block_size
    print(f"[onnx] exporting RF-DETR {variant} checkpoint: {weights_path}", flush=True)
    print(f"[onnx] input={shape}x{shape}, classes={len(labels)}, output={Path(output).expanduser().resolve()}", flush=True)
    kwargs = {"pretrain_weights": str(weights_path), "patch_size": patch_size, "num_classes": len(labels), "device": "cpu"}
    try:
        model = architectures[variant](trust_checkpoint=True, **kwargs)
    except TypeError:
        model = architectures[variant](**kwargs)
    wrapper = getattr(getattr(model, "model", None), "model", None)
    wrapper = getattr(wrapper, "model", None) or wrapper
    if wrapper is None:
        raise RuntimeError("RF-DETR did not expose an exportable torch module")
    wrapper.eval()
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros((1, 3, shape, shape), dtype=torch.float32)
    if hasattr(wrapper, "export"):
        wrapper.export()
    torch.onnx.export(wrapper, dummy, str(destination), input_names=["images"], opset_version=18,
                      do_constant_folding=True, external_data=True)
    print(f"[onnx] export complete: {destination}", flush=True)
    return destination
