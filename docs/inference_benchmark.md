# Inference benchmark

Measured on 2026-10-24 using the local Windows 11 machine, Intel Iris Xe,
ONNX Runtime 1.24.4, DirectML, fixed 384x384 input, batch size 1, and a
zero-valued frame:

| Provider | p50 | p95 | p99 | Result |
| --- | ---: | ---: | ---: | --- |
| DirectML / RF-DETR Nano | 104.9 ms | 112.5 ms | 112.7 ms | Below the 20 Hz target |

The provider was confirmed as `DmlExecutionProvider`, with CPU fallback
available. This is an inference-only benchmark and does not establish detector
accuracy or end-to-end timing.

The ONNX export succeeded at 384x384 using RF-DETR Nano with
`patch_size=16`. The previous partial-load warning disappeared with this
configuration. The exported model still requires a parity set before gameplay
accuracy is accepted.

Because accuracy is the priority, the configured resolution was not reduced to
chase the 20 Hz target.
