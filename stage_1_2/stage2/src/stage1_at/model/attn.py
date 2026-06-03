import math
from math import sqrt
from typing import Optional
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

class TriangularCausalMask:
    def __init__(self, batch_size: int, seq_len: int, device: str = "cpu"):
        mask_shape = [batch_size, 1, seq_len, seq_len]
        with torch.no_grad():
            self._mask = torch.triu(torch.ones(mask_shape, dtype=torch.bool), diagonal=1).to(device)

    @property
    def mask(self):
        return self._mask

class AnomalyAttention(nn.Module):
    def __init__(self, win_size: int, mask_flag: bool = True, scale: Optional[float] = None, attention_dropout: float = 0.0, output_attention: bool = False):
        super().__init__()
        self.scale = scale
        self.mask_flag = mask_flag
        self.output_attention = output_attention
        self.dropout = nn.Dropout(attention_dropout)
        self.window_size = win_size

        # Distance prior used by the original Anomaly Transformer.
        distances = torch.zeros((win_size, win_size), dtype=torch.float32)
        for i in range(win_size):
            for j in range(win_size):
                distances[i, j] = abs(i - j)
        self.register_buffer("distances", distances)

    def forward(self, queries: torch.Tensor, keys: torch.Tensor, values: torch.Tensor, sigma: torch.Tensor, attn_mask: Optional[TriangularCausalMask]):
        batch_size, seq_len, n_heads, head_dim = queries.shape
        _, src_len, _, value_dim = values.shape
        scale = self.scale or 1.0 / sqrt(head_dim)

        scores = torch.einsum("blhe,bshe->bhls", queries, keys)

        padding_mask = None
        if attn_mask is not None and torch.is_tensor(attn_mask):
            padding_mask = attn_mask.float()
            key_mask = padding_mask.unsqueeze(1).unsqueeze(1)
            scores = scores.masked_fill(key_mask == 0, -1e9)
            attn_mask = None

        if self.mask_flag:
            if attn_mask is None:
                attn_mask = TriangularCausalMask(batch_size=batch_size, seq_len=seq_len, device=queries.device)
            scores.masked_fill_(attn_mask.mask, -np.inf)

        attn = scale * scores

        sigma = sigma.transpose(1, 2)  # [B, H, L]
        sigma = torch.sigmoid(sigma * 5.0) + 1e-5
        sigma = torch.pow(3.0, sigma) - 1.0
        sigma = sigma.unsqueeze(-1).repeat(1, 1, 1, self.window_size)  # [B,H,L,L]

        prior = self.distances.unsqueeze(0).unsqueeze(0).repeat(sigma.shape[0], sigma.shape[1], 1, 1).to(sigma.device)

        prior = 1.0 / (math.sqrt(2 * math.pi) * sigma) * torch.exp(-(prior**2) / (2 * (sigma**2)))

        if padding_mask is not None:
            key_mask = padding_mask.unsqueeze(1).unsqueeze(1)
            prior = prior * key_mask
            prior = prior / (torch.sum(prior, dim=-1, keepdim=True) + 1e-8)

        series = self.dropout(torch.softmax(attn, dim=-1))

        if padding_mask is not None:
            key_mask = padding_mask.unsqueeze(1).unsqueeze(1)
            query_mask = padding_mask.unsqueeze(1).unsqueeze(-1)
            series = series * key_mask
            series = series / (torch.sum(series, dim=-1, keepdim=True) + 1e-8)
            series = series * query_mask
            prior = prior * query_mask
            
        v = torch.einsum("bhls,bshd->blhd", series, values)
        if self.output_attention:
            return (v.contiguous(), series, prior, sigma)
        else:
            return (v.contiguous(), None)

class AttentionLayer(nn.Module):
    def __init__(self, attention: AnomalyAttention, d_model: int, n_heads: int, d_keys: Optional[int] = None, d_values: Optional[int] = None):
        super().__init__()
        d_keys = d_keys or (d_model // n_heads)
        d_values = d_values or (d_model // n_heads)

        self.norm = nn.LayerNorm(d_model)
        self.inner_attention = attention
        self.query_projection = nn.Linear(d_model, d_keys * n_heads)
        self.key_projection = nn.Linear(d_model, d_keys * n_heads)
        self.value_projection = nn.Linear(d_model, d_values * n_heads)
        self.sigma_projection = nn.Linear(d_model, n_heads)
        self.out_projection = nn.Linear(d_values * n_heads, d_model)

        self.n_heads = n_heads

    def forward(self, queries: torch.Tensor, keys: torch.Tensor, values: torch.Tensor, attn_mask: Optional[TriangularCausalMask]):
        batch_size, seq_len, _ = queries.shape
        _, src_len, _ = keys.shape
        n_heads = self.n_heads

        x = queries
        queries = self.query_projection(queries).view(batch_size, seq_len, n_heads, -1)
        keys = self.key_projection(keys).view(batch_size, src_len, n_heads, -1)
        values = self.value_projection(values).view(batch_size, src_len, n_heads, -1)
        sigma = self.sigma_projection(x).view(batch_size, seq_len, n_heads)
        
        out, series, prior, sigma = self.inner_attention(queries, keys, values, sigma, attn_mask)
        out = out.view(batch_size, seq_len, -1)

        return self.out_projection(out), series, prior, sigma