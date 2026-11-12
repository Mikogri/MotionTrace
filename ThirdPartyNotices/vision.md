# MotionTrace Vision — third-party components

Model repository metadata and license sources checked on 2026-09-18.
MotionTrace uses the Transformers implementation and downloads weights separately.
No upstream source files are modified or vendored by this integration.

## Weights

The pinned model cards declare the following licenses. This is distinct from the
licenses of the runtime and of the upstream reference implementations.

| Model | Revision | Model-card license | Author/source |
|---|---|---|---|
| X-CLIP base patch16 | d6184e3fd8780d04c85d0f1eabe5f94bf44d98f6 | MIT | [Microsoft](https://huggingface.co/microsoft/xclip-base-patch16/tree/d6184e3fd8780d04c85d0f1eabe5f94bf44d98f6) |
| Grounding DINO tiny | a2bb814dd30d776dcf7e30523b00659f4f141c71 | Apache-2.0 | [IDEA Research](https://huggingface.co/IDEA-Research/grounding-dino-tiny/tree/a2bb814dd30d776dcf7e30523b00659f4f141c71) |
| SAM 2.1 Hiera small | ee5bba1d82bb8749febdf90f45e84b687142ba03 | Apache-2.0 | [Meta](https://huggingface.co/facebook/sam2.1-hiera-small/tree/ee5bba1d82bb8749febdf90f45e84b687142ba03) |

Their README model cards are retained in each installed model directory. These
models do not require a paid inference API. Model license availability does not
constitute a guarantee about accuracy or suitability for measurement.

## Reference implementation attribution

The downloader additionally preserves these exact upstream documents in each
model's `upstream_notices` directory. None of the three pinned Hugging Face trees
contains a standalone LICENSE file, so the model card declaration and upstream
license provenance are both retained rather than conflated.

- Microsoft VideoX / X-CLIP: Copyright (c) Microsoft Corporation; MIT.
  [LICENSE](https://github.com/microsoft/VideoX/blob/1744b2159c3d11694f94dab4fcde8660c685e79a/LICENSE),
  [notice.md](https://github.com/microsoft/VideoX/blob/1744b2159c3d11694f94dab4fcde8660c685e79a/notice.md).
- IDEA Research GroundingDINO: Copyright 2023–present, IDEA Research; Apache-2.0.
  [LICENSE](https://github.com/IDEA-Research/GroundingDINO/blob/856dde20aee659246248e20734ef9ba5214f5e44/LICENSE).
- Meta SAM2: Apache-2.0.
  [LICENSE](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/LICENSE).
  Its dataset has a separate license; MotionTrace does not download the SA-V dataset.

No standalone NOTICE was found in the pinned GroundingDINO or SAM2 root trees.
The Microsoft notice is preserved verbatim. Any future modifications to upstream
files must carry their own change notices in addition to the original attribution.

## Runtime dependencies

The runtime has independent licenses; it is not collectively MIT or Apache-2.0.
The installation writes `dependencies.json` containing actual installed versions,
license expressions/metadata/classifiers, and hashes/paths for bundled license
documents. Those documents are copied to `dependency_notices` without changing
their content. Missing license metadata is left missing, not interpreted as a
license grant.

Primary dependencies have the following upstream license families:

| Component | License family / relevant additional terms |
|---|---|
| Python | PSF license and bundled third-party notices |
| PyTorch | BSD-style; bundled third-party notices and NVIDIA CUDA runtime terms |
| torchvision | BSD-3-Clause and bundled notices |
| Transformers | Apache-2.0 |
| huggingface-hub, tokenizers, safetensors | Apache-2.0 |
| NumPy, SciPy | BSD-3-Clause and bundled numerical library notices |
| OpenCV | Apache-2.0; opencv-python packaging has separate MIT license and bundled notices |
| Pillow | HPND/PIL license and bundled library notices |
| PyAV | BSD-3-Clause; linked FFmpeg libraries have their own license/build terms |

Consult the actual installed package documents before redistributing the Python
environment, especially CUDA, FFmpeg and bundled native libraries. The installer
uses published binary packages and does not copy the whole runtime into the WinUI
application directory. License texts from installed wheels remain alongside them.

Authoritative sources:
[PyTorch](https://github.com/pytorch/pytorch/blob/v2.8.0/LICENSE),
[torchvision](https://github.com/pytorch/vision/blob/v0.23.0/LICENSE),
[Transformers](https://github.com/huggingface/transformers/blob/v4.57.6/LICENSE),
[NumPy](https://github.com/numpy/numpy/blob/v1.26.4/LICENSE.txt),
[SciPy](https://github.com/scipy/scipy/blob/v1.15.3/LICENSE.txt),
[OpenCV packaging](https://github.com/opencv/opencv-python/blob/86/LICENSE.txt),
[Pillow](https://github.com/python-pillow/Pillow/blob/11.3.0/LICENSE),
[PyAV](https://github.com/PyAV-Org/PyAV/blob/v16.0.1/LICENSE.txt).
