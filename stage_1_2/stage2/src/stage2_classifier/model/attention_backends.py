import math
import torch
import torch.nn as nn
from typing import Literal
import torch.nn.functional as F

AttentionBackend = Literal["full", "sdpa", "flash_attn2", "flash_attn3"]


class FullAttention(nn.Module):
    def __init__(self, dropout=0.1):
        super().__init__()
        self.dropout = nn.Dropout(dropout)

    def forward(self, q, k, v, attn_mask=None):
        d = q.shape[-1]
        scores = torch.einsum("blhd,bshd->bhls", q, k) / math.sqrt(d)
        if attn_mask is not None:
            scores = scores.masked_fill(attn_mask, float("-inf"))
        attn = self.dropout(torch.softmax(scores, dim=-1))
        out = torch.einsum("bhls,bshd->blhd", attn, v)
        return out.contiguous(), attn


class SDPAAttention(nn.Module):
    def __init__(self, dropout=0.1):
        super().__init__()
        self.dropout = float(dropout)

    def forward(self, q, k, v, attn_mask=None):
        q = q.transpose(1, 2).contiguous()
        k = k.transpose(1, 2).contiguous()
        v = v.transpose(1, 2).contiguous()

        out = F.scaled_dot_product_attention(
            q, k, v,
            attn_mask=attn_mask,
            dropout_p=self.dropout if self.training else 0.0,
            is_causal=False,
        )

        return out.transpose(1, 2).contiguous(), None


class FlashAttn2Attention(nn.Module):
    def __init__(self, dropout=0.1):
        super().__init__()
        self.dropout = float(dropout)
        try:
            from flash_attn import flash_attn_func
        except Exception as exc:
            raise ImportError("flash_attn2 backend requires flash-attn. Use --attention_backend sdpa or full instead.") from exc
        self.flash_attn_func = flash_attn_func

    def forward(self, q, k, v, attn_mask=None):
        if attn_mask is not None:
            raise NotImplementedError("flash_attn2 wrapper currently expects no attention mask.")
        out = self.flash_attn_func(
            q.contiguous(), k.contiguous(), v.contiguous(),
            dropout_p=self.dropout if self.training else 0.0,
            softmax_scale=None,
            causal=False,
        )
        return out.contiguous(), None


class FlashAttn3Attention(nn.Module):
    def __init__(self, dropout=0.1):
        super().__init__()
        self.dropout = float(dropout)
        try:
            from flash_attn_interface import flash_attn_func
        except Exception as exc:
            raise ImportError("flash_attn3 backend requires a FlashAttention-3 compatible install. Use --attention_backend sdpa/full if unavailable.") from exc
        self.flash_attn_func = flash_attn_func

    def forward(self, q, k, v, attn_mask=None):
        if attn_mask is not None:
            raise NotImplementedError("flash_attn3 wrapper currently expects no attention mask.")
        out = self.flash_attn_func(
            q.contiguous(), k.contiguous(), v.contiguous(),
            dropout_p=self.dropout if self.training else 0.0,
            softmax_scale=None,
            causal=False,
        )
        if isinstance(out, tuple):
            out = out[0]
        return out.contiguous(), None


def build_attention_backend(name, dropout):
    if name == "full":
        return FullAttention(dropout)
    if name == "sdpa":
        return SDPAAttention(dropout)
    if name == "flash_attn2":
        return FlashAttn2Attention(dropout)
    if name == "flash_attn3":
        return FlashAttn3Attention(dropout)
    raise ValueError(f"Unsupported attention backend: {name}")