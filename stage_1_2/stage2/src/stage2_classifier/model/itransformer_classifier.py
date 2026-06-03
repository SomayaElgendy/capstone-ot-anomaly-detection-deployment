from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.stage2_classifier.model.attention_backends import AttentionBackend, build_attention_backend


@dataclass
class Stage2ModelConfig:
    net_win: int = 120
    proc_win: int = 50
    net_features: int = 43
    proc_features: int = 14
    num_classes: int = 6
    d_model: int = 128
    n_heads: int = 8
    n_layers: int = 3
    d_ff: int = 256
    dropout: float = 0.1
    attention_backend: AttentionBackend = "full"


class DataEmbeddingInverted(nn.Module):
    def __init__(self, seq_len, d_model, dropout):
        super().__init__()
        self.value_embedding = nn.Linear(seq_len, d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask=None):
        if mask is not None:
            x = x * mask.unsqueeze(-1)
        x = x.permute(0, 2, 1)
        return self.dropout(self.value_embedding(x))


class AttentionLayer(nn.Module):
    def __init__(self, attention, d_model, n_heads):
        super().__init__()
        if d_model % n_heads != 0:
            raise ValueError(f"d_model={d_model} must be divisible by n_heads={n_heads}")

        self.n_heads = n_heads
        self.d_head = d_model // n_heads
        self.inner_attention = attention
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)

    def forward(self, x):
        b, l, _ = x.shape
        h = self.n_heads

        q = self.q_proj(x).view(b, l, h, self.d_head)
        k = self.k_proj(x).view(b, l, h, self.d_head)
        v = self.v_proj(x).view(b, l, h, self.d_head)

        out, attn = self.inner_attention(q, k, v, attn_mask=None)
        out = out.reshape(b, l, -1)
        return self.out_proj(out), attn


class EncoderLayer(nn.Module):
    def __init__(self, attention, d_model, d_ff, dropout):
        super().__init__()
        self.attention = attention
        self.conv1 = nn.Conv1d(d_model, d_ff, kernel_size=1)
        self.conv2 = nn.Conv1d(d_ff, d_model, kernel_size=1)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        new_x, attn = self.attention(x)
        x = x + self.dropout(new_x)

        y = self.norm1(x)
        y = self.dropout(F.gelu(self.conv1(y.transpose(1, 2))))
        y = self.dropout(self.conv2(y).transpose(1, 2))

        return self.norm2(x + y), attn


class Encoder(nn.Module):
    def __init__(self, layers, d_model):
        super().__init__()
        self.layers = nn.ModuleList(layers)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x):
        attns = []
        for layer in self.layers:
            x, attn = layer(x)
            attns.append(attn)
        return self.norm(x), attns


class ITransformerBranch(nn.Module):
    def __init__(self, seq_len, d_model, n_heads, n_layers, d_ff, dropout, attention_backend):
        super().__init__()
        self.embedding = DataEmbeddingInverted(seq_len, d_model, dropout)

        layers = [
            EncoderLayer(
                attention=AttentionLayer(
                    attention=build_attention_backend(attention_backend, dropout),
                    d_model=d_model,
                    n_heads=n_heads,
                ),
                d_model=d_model,
                d_ff=d_ff,
                dropout=dropout,
            )
            for _ in range(n_layers)
        ]

        self.encoder = Encoder(layers, d_model)

    def forward(self, x, mask=None):
        x = self.embedding(x, mask)
        x, _ = self.encoder(x)
        return x.mean(dim=1)


class Stage2ITransformerClassifier(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config

        self.network_branch = ITransformerBranch(
            seq_len=config.net_win,
            d_model=config.d_model,
            n_heads=config.n_heads,
            n_layers=config.n_layers,
            d_ff=config.d_ff,
            dropout=config.dropout,
            attention_backend=config.attention_backend,
        )

        self.process_branch = ITransformerBranch(
            seq_len=config.proc_win,
            d_model=config.d_model,
            n_heads=config.n_heads,
            n_layers=config.n_layers,
            d_ff=config.d_ff,
            dropout=config.dropout,
            attention_backend=config.attention_backend,
        )

        self.classifier = nn.Sequential(
            nn.LayerNorm(config.d_model * 2),
            nn.Linear(config.d_model * 2, config.d_model),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.d_model, config.num_classes),
        )

    def forward(self, x_net, x_proc, mask_net=None, mask_proc=None):
        h_net = self.network_branch(x_net, mask_net)
        h_proc = self.process_branch(x_proc, mask_proc)
        fused = torch.cat([h_net, h_proc], dim=-1)
        return self.classifier(fused)

    def get_config(self):
        return self.config.__dict__