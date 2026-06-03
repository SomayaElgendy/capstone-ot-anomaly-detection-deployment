from typing import List, Optional
import torch
import torch.nn as nn
import torch.nn.functional as F
from .attn import AnomalyAttention, AttentionLayer
from .embed import DataEmbedding

class EncoderLayer(nn.Module):
    def __init__(self, attention: AttentionLayer, d_model: int, d_ff: Optional[int] = None, dropout: float = 0.1, activation: str = "relu"):
        super().__init__()
        d_ff = d_ff or (4 * d_model)
        self.attention = attention
        self.conv1 = nn.Conv1d(in_channels=d_model, out_channels=d_ff, kernel_size=1)
        self.conv2 = nn.Conv1d(in_channels=d_ff, out_channels=d_model, kernel_size=1)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        self.activation = F.relu if activation == "relu" else F.gelu

    def forward(self, x: torch.Tensor, attn_mask=None):
        new_x, attn, mask, sigma = self.attention(x, x, x, attn_mask=attn_mask)
        x = x + self.dropout(new_x)
        y = x = self.norm1(x)
        y = self.dropout(self.activation(self.conv1(y.transpose(-1, 1))))
        y = self.dropout(self.conv2(y).transpose(-1, 1))
        return self.norm2(x + y), attn, mask, sigma

class Encoder(nn.Module):
    def __init__(self, attn_layers: List[EncoderLayer], norm_layer: Optional[nn.Module] = None):
        super().__init__()
        self.attn_layers = nn.ModuleList(attn_layers)
        self.norm = norm_layer

    def forward(self, x: torch.Tensor, attn_mask=None):
        series_list = []
        prior_list = []
        sigma_list = []
        for attn_layer in self.attn_layers:
            x, series, prior, sigma = attn_layer(x, attn_mask=attn_mask)
            series_list.append(series)
            prior_list.append(prior)
            sigma_list.append(sigma)
        if self.norm is not None:
            x = self.norm(x)
        return x, series_list, prior_list, sigma_list

class AnomalyTransformer(nn.Module):
    def __init__(self, win_size: int, enc_in: int, c_out: int, d_model: int = 512, n_heads: int = 8, e_layers: int = 3, d_ff: int = 512, dropout: float = 0.0, activation: str = "gelu", output_attention: bool = True):
        super().__init__()
        self.output_attention = output_attention
        self.embedding = DataEmbedding(enc_in, d_model, dropout)
        self.encoder = Encoder(
            [
                EncoderLayer(
                    AttentionLayer(
                        AnomalyAttention(win_size=win_size, mask_flag=False, attention_dropout=dropout, output_attention=output_attention),
                        d_model=d_model,
                        n_heads=n_heads,
                    ),
                    d_model=d_model,
                    d_ff=d_ff,
                    dropout=dropout,
                    activation=activation,
                )
                for _ in range(e_layers)
            ],
            norm_layer=nn.LayerNorm(d_model),
        )
        self.projection = nn.Linear(d_model, c_out, bias=True)

    def forward(self, x: torch.Tensor, padding_mask=None):
        enc_out = self.embedding(x)
        enc_out, series, prior, sigmas = self.encoder(enc_out, attn_mask=padding_mask)
        enc_out = self.projection(enc_out)
        if self.output_attention:
            return enc_out, series, prior, sigmas
        return enc_out