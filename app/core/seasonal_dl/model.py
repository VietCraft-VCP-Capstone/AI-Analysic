"""Mạng nơ-ron dự báo phân vị (P10/P50/P90) — Kiến trúc Temporal Fusion + Lunar-Shift Attention.

Lấy cảm hứng từ Temporal Fusion Transformer (Google/Amazon Forecast) & DeepAR:
  1. Temporal Encoder (Causal 1D-CNN + GRU) trên chuỗi 52 tuần quá khứ + covariate lịch.
  2. Static Gated Residual Network (GRN) mã hóa đặc tính chuỗi (độ biến động CV, động lượng YoY).
  3. Lunar-Shift Attention trên lân cận ±3 tuần quanh lag-52: tự động dịch đỉnh mùa vụ khi
     Tết Âm lịch / Trung thu xê dịch giữa các năm.
  4. Shared Horizon Decoder (GRN) dự báo đa phân vị P10/P50/P90 bằng Pinball Loss.

Thiên kiến quy nạp: Khởi đầu tại aligned_lag (≈ lag-52), chỉ hiệu chỉnh khi dữ liệu chứng minh có lợi.
"""
from __future__ import annotations

import torch
from torch import nn
import torch.nn.functional as F

from app.core.seasonal_dl.features import (
    FEATURE_DIM,
    H,
    L,
    LAG_RADIUS,
    LAG_WIN,
    N_COV,
    N_STATIC,
    QUANTILES,
)


class GatedResidualNetwork(nn.Module):
    """GRN chuẩn Temporal Fusion Transformer với ELU + GLU gating + LayerNorm."""

    def __init__(self, d_in: int, d_hidden: int, d_out: int, dropout: float = 0.15):
        super().__init__()
        self.proj = nn.Linear(d_in, d_out) if d_in != d_out else nn.Identity()
        self.fc1 = nn.Linear(d_in, d_hidden)
        self.fc2 = nn.Linear(d_hidden, d_out * 2)
        self.drop = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(d_out)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        res = self.proj(x)
        h = F.elu(self.fc1(x))
        h = self.drop(h)
        a, b = self.fc2(h).chunk(2, dim=-1)
        gated = a * torch.sigmoid(b)
        return self.norm(res + gated)


class QuantileForecaster(nn.Module):
    def __init__(self, hidden: int = 48, dropout: float = 0.15):
        super().__init__()
        self.hidden = hidden

        # 1. Temporal Encoder: Causal Conv1D + GRU trên (B, L, 1 + N_COV)
        self.conv1 = nn.Conv1d(1 + N_COV, hidden, kernel_size=3, padding=2)
        self.gru = nn.GRU(hidden, hidden, num_layers=1, batch_first=True)
        self.enc_norm = nn.LayerNorm(hidden)

        # 2. Static Context GRN
        self.static_grn = GatedResidualNetwork(N_STATIC, hidden, hidden, dropout=dropout)

        # 3. Lunar-Shift Attention trên lân cận ±3 tuần quanh lag-52
        # Input: cov_future(4) + cov_lag(4) + diff(4) + c_static(hidden)
        attn_in = N_COV * 3 + hidden
        self.lunar_attn = nn.Sequential(
            nn.Linear(attn_in, hidden),
            nn.Tanh(),
            nn.Dropout(dropout),
            nn.Linear(hidden, LAG_WIN),
        )
        # Khởi tạo thiên về offset 0 (lag-52) lúc bắt đầu
        nn.init.zeros_(self.lunar_attn[-1].weight)
        init_bias = torch.zeros(LAG_WIN)
        init_bias[LAG_RADIUS] = 2.0
        self.lunar_attn[-1].bias.data.copy_(init_bias)

        # 4. Shared Horizon Decoder GRN
        # Input: enc_last(hidden) + enc_recent4(hidden) + static(hidden) +
        #        aligned_lag(1) + lag52(1) + recent_4w(1) + h_norm(1) + cov_future(4) + cov_diff(4)
        dec_in = hidden * 3 + 4 + N_COV * 2
        self.decoder_grn = GatedResidualNetwork(dec_in, hidden, hidden, dropout=dropout)
        self.out = nn.Linear(hidden, 3)  # (delta_p50, spread_lo, spread_hi)
        nn.init.zeros_(self.out.weight)
        nn.init.zeros_(self.out.bias)

        # Đăng ký vị trí horizon [0..1]
        h_pos = torch.linspace(0.0, 1.0, H).view(1, H, 1)
        self.register_buffer("h_pos", h_pos)

    def _unpack(self, x: torch.Tensor):
        B = x.shape[0]
        idx = 0
        y_past = x[:, idx:idx + L].view(B, L, 1)
        idx += L
        cov_past = x[:, idx:idx + L * N_COV].view(B, L, N_COV)
        idx += L * N_COV
        cov_future = x[:, idx:idx + H * N_COV].view(B, H, N_COV)
        idx += H * N_COV
        cov_lag = x[:, idx:idx + H * N_COV].view(B, H, N_COV)
        idx += H * N_COV
        lag_neighbors = x[:, idx:idx + H * LAG_WIN].view(B, H, LAG_WIN)
        idx += H * LAG_WIN
        static_stats = x[:, idx:idx + N_STATIC]
        return y_past, cov_past, cov_future, cov_lag, lag_neighbors, static_stats

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B = x.shape[0]
        y_past, cov_past, cov_future, cov_lag, lag_neighbors, static_stats = self._unpack(x)

        # 1. Encode lịch sử 52 tuần
        seq_in = torch.cat([y_past, cov_past], dim=-1).transpose(1, 2)  # (B, 1+N_COV, L)
        c_out = F.gelu(self.conv1(seq_in)[:, :, :L]).transpose(1, 2)    # (B, L, hidden)
        gru_out, _ = self.gru(c_out)                                    # (B, L, hidden)
        enc_last = self.enc_norm(gru_out[:, -1, :])                     # (B, hidden)
        enc_recent4 = self.enc_norm(gru_out[:, -4:, :].mean(dim=1))     # (B, hidden)

        # 2. Static context
        c_static = self.static_grn(static_stats)                        # (B, hidden)

        # 3. Lunar-Shift Attention
        cov_diff = cov_future - cov_lag                                 # (B, H, N_COV)
        c_static_exp = c_static.unsqueeze(1).expand(B, H, self.hidden)
        attn_in = torch.cat([cov_future, cov_lag, cov_diff, c_static_exp], dim=-1)
        attn_w = F.softmax(self.lunar_attn(attn_in), dim=-1)            # (B, H, LAG_WIN)
        aligned_lag = (attn_w * lag_neighbors).sum(dim=-1, keepdim=True)  # (B, H, 1)
        lag52 = lag_neighbors[:, :, LAG_RADIUS:LAG_RADIUS + 1]          # (B, H, 1)

        # 4. Shared Horizon Decoder
        recent_4w = static_stats[:, 2:3].unsqueeze(1).expand(B, H, 1)
        h_pos = self.h_pos.expand(B, H, 1)
        enc_last_exp = enc_last.unsqueeze(1).expand(B, H, self.hidden)
        enc_rec_exp = enc_recent4.unsqueeze(1).expand(B, H, self.hidden)

        dec_in = torch.cat([
            enc_last_exp,
            enc_rec_exp,
            c_static_exp,
            aligned_lag,
            lag52,
            recent_4w,
            h_pos,
            cov_future,
            cov_diff,
        ], dim=-1)
        dec_h = self.decoder_grn(dec_in)                                # (B, H, hidden)
        raw = self.out(dec_h)                                           # (B, H, 3)

        med = torch.clamp(aligned_lag.squeeze(-1) + raw[:, :, 0], min=0.0)
        lo = torch.clamp(med - F.softplus(raw[:, :, 1] - 0.5) - 1e-3, min=0.0)
        hi = med + F.softplus(raw[:, :, 2] - 0.5) + 1e-3
        return torch.stack([lo, med, hi], dim=-1)                       # (B, H, 3)


def pinball_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    q = torch.tensor(QUANTILES, dtype=pred.dtype, device=pred.device).view(1, 1, 3)
    err = target.unsqueeze(-1) - pred
    return torch.maximum(q * err, (q - 1.0) * err).mean()
