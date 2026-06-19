"""TrackNetV2 — temporal ball detector for sports video.

Architecture: VGG-style encoder (9-ch input: 3 consecutive BGR frames) →
bottleneck → decoder with skip connections → single heatmap (H×W, sigmoid).

Input  : (B, 9, H, W)  — three 720p frames downscaled to INPUT_HW
Output : (B, 1, H, W)  — probability heatmap; peak = ball centre

Training target: Gaussian blob (σ=SIGMA_PX) centred on ball, binarised at 0.5.
At inference: argmax(heatmap) → (cx, cy); emit bbox of radius BALL_RADIUS_PX.
"""
from __future__ import annotations

import torch
import torch.nn as nn

# ── public constants (used by dataset + detector) ────────────────────────────
INPUT_HW    = (288, 512)   # H×W the model is trained at (16:9, keeps aspect)
SIGMA_PX    = 5            # Gaussian σ for heatmap target generation
BALL_RADIUS_PX = 15        # fixed radius for the output bbox at 720p


def _conv_bn_relu(in_ch: int, out_ch: int, **kw) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, **kw),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


class TrackNetV2(nn.Module):
    """Encoder-decoder with VGG-style blocks and skip connections.

    Encoder: 5 downsampling stages (MaxPool2d).
    Decoder: 4 upsampling stages (bilinear + conv).
    Skip connections from each encoder stage to the matching decoder stage.
    """

    def __init__(self, in_channels: int = 9) -> None:
        super().__init__()

        # Encoder
        self.enc1 = nn.Sequential(_conv_bn_relu(in_channels, 64), _conv_bn_relu(64, 64))
        self.enc2 = nn.Sequential(nn.MaxPool2d(2), _conv_bn_relu(64, 128), _conv_bn_relu(128, 128))
        self.enc3 = nn.Sequential(nn.MaxPool2d(2), _conv_bn_relu(128, 256), _conv_bn_relu(256, 256), _conv_bn_relu(256, 256))
        self.enc4 = nn.Sequential(nn.MaxPool2d(2), _conv_bn_relu(256, 512), _conv_bn_relu(512, 512), _conv_bn_relu(512, 512))
        self.enc5 = nn.Sequential(nn.MaxPool2d(2), _conv_bn_relu(512, 512), _conv_bn_relu(512, 512), _conv_bn_relu(512, 512))

        # Bottleneck
        self.bottleneck = nn.Sequential(
            nn.MaxPool2d(2),
            _conv_bn_relu(512, 512),
            _conv_bn_relu(512, 512),
        )

        # Decoder (upsampling + skip cat)
        self.up5 = nn.Sequential(_conv_bn_relu(1024, 512), _conv_bn_relu(512, 512))
        self.up4 = nn.Sequential(_conv_bn_relu(1024, 512), _conv_bn_relu(512, 256))
        self.up3 = nn.Sequential(_conv_bn_relu(512,  256), _conv_bn_relu(256, 128))
        self.up2 = nn.Sequential(_conv_bn_relu(256,  128), _conv_bn_relu(128, 64))
        self.up1 = nn.Sequential(_conv_bn_relu(128,  64),  _conv_bn_relu(64,  64))

        self.head = nn.Conv2d(64, 1, kernel_size=1)

        self._upsample = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        e5 = self.enc5(e4)
        b  = self.bottleneck(e5)

        d5 = self.up5(torch.cat([self._upsample(b),  e5], dim=1))
        d4 = self.up4(torch.cat([self._upsample(d5), e4], dim=1))
        d3 = self.up3(torch.cat([self._upsample(d4), e3], dim=1))
        d2 = self.up2(torch.cat([self._upsample(d3), e2], dim=1))
        d1 = self.up1(torch.cat([self._upsample(d2), e1], dim=1))

        return torch.sigmoid(self.head(d1))   # (B,1,H,W) in [0,1]
