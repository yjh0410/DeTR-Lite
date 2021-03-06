"""
This is the code for practice I wrote when I was learning Transfomer. 
It is not recommended to use this code. 
It is possible that some factors such as random initialization will reduce the performance of the model, 
and the implementation of this code for practice is not optimal.
"""


import torch
import torch.nn as nn


# FFN
class FeedForward(nn.Module):
    def __init__(self, dim, hidden_dim, dropout = 0., act='relu'):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, hidden_dim),
            nn.GELU() if act =='gelu' else nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, dim),
            nn.Dropout(dropout)
        )
        self.norm = nn.LayerNorm(dim)
    def forward(self, x):
        return self.norm(self.net(x)) + x


# MultiHeadAttention
class MultiHeadAttention(nn.Module):
    def __init__(self, 
                 dim,
                 heads=8, 
                 dim_head = 64,
                 dropout = 0.):
        super().__init__()
        inner_dim = dim_head *  heads
        self.dim_head = dim_head
        self.heads = heads
        self.scale = dim_head ** -0.5     # 1 / sqrt(d_k)

        self.attend = nn.Softmax(dim = -1)
        self.to_q = nn.Linear(dim, inner_dim, bias = False) # W_q, W_k, W_v
        self.to_k = nn.Linear(dim, inner_dim, bias = False) # W_q, W_k, W_v
        self.to_v = nn.Linear(dim, inner_dim, bias = False) # W_q, W_k, W_v

        self.to_out = nn.Sequential(
            nn.Linear(inner_dim, dim),
            nn.Dropout(dropout)
        )
        self.norm = nn.LayerNorm(dim)

    def forward(self, query, key, value):
        B, NQ = query.shape[:2]
        B, NK = key.shape[:2]
        B, NV = value.shape[:2]
        # Input：x -> [B, N, C_in]
        # [B, N, h*d] -> [B, N, h, d] -> [B, h, N, d]
        q = self.to_q(query).view(B, NQ, self.heads, self.dim_head).permute(0, 2, 1, 3).contiguous()
        k = self.to_k(key).view(B, NK, self.heads, self.dim_head).permute(0, 2, 1, 3).contiguous()
        v = self.to_v(value).view(B, NV, self.heads, self.dim_head).permute(0, 2, 1, 3).contiguous()

        # Q*K^T / sqrt(d_k) : [B, h, N, d] X [B, h, d, N] = [B, h, N, N]
        dots = torch.matmul(q, k.transpose(-1, -2)) * self.scale
        # softmax
        attn = self.attend(dots)
        # softmax(Q*K^T / sqrt(d_k)) * V ：[B, h, N, N] X [B, h, N, d] = [B, h, N, d]
        out = torch.matmul(attn, v)
        # [B, h, N, d] -> [B, N, h*d]=[B, N, C_out], C_out = h*d
        out = out.permute(0, 2, 1, 3).contiguous().view(B, NQ, -1)
        
        return self.norm(self.to_out(out)) + query


# Transformer Encoder Layer
class TransformerEncoderLayer(nn.Module):
    def __init__(self, 
                 dim,            # hidden_dim
                 heads, 
                 dim_head,
                 mlp_dim=2048,
                 dropout = 0.,
                 act='relu'):
        super().__init__()
        self.attn = MultiHeadAttention(dim, heads, dim_head, dropout)
        self.ffn = FeedForward(dim, mlp_dim, dropout, act)

    def forward(self, x, pos=None):
        # x -> [B, N, d_in]
        q = k = x if pos is None else x + pos
        v = x
        x = self.attn(q, k, v)
        x = self.ffn(x)

        return x


# Transformer Encoder
class TransformerEncoder(nn.Module):
    def __init__(self, 
                 dim,            # hidden_dim
                 depth,          # num_encoder
                 heads,
                 dim_head,
                 mlp_dim=2048,
                 dropout = 0.,
                 act='relu'):
        super().__init__()
        # build encoder
        self.encoders = nn.ModuleList([
                                TransformerEncoderLayer(
                                    dim, 
                                    heads, 
                                    dim_head, 
                                    mlp_dim, 
                                    dropout, 
                                    act) for _ in range(depth)])

    def forward(self, x, pos=None):
        for m in self.encoders:
            x = m(x, pos)
        
        return x


# Transformer Decoder Layer
class TransformerDecoderLayer(nn.Module):
    def __init__(self,
                 dim,            # hidden_dim
                 heads,
                 dim_head,
                 mlp_dim=2048,
                 dropout = 0.,
                 act='relu'):
        super().__init__()
        self.attn_0 = MultiHeadAttention(dim, heads, dim_head, dropout)
        self.ffn_0 = FeedForward(dim, mlp_dim, dropout, act)
        self.attn_1 = MultiHeadAttention(dim, heads, dim_head, dropout)
        self.ffn_1 = FeedForward(dim, mlp_dim, dropout, act)

    def forward(self, tgt, memory, pos=None, query_pos=None):
        # memory is the output of the last encoder
        # x -> [B, N, d_in]
        q0 = k0 = tgt if query_pos is None else tgt + query_pos
        v0 = tgt
        tgt = self.attn_0(q0, k0, v0)
        tgt = self.ffn_0(tgt)

        q = tgt if query_pos is None else tgt + query_pos
        k = memory if pos is None else memory + pos
        v = memory
        tgt = self.attn_1(q, k, v)
        tgt = self.ffn_1(tgt)

        return tgt


# Transformer Decoder
class TransformerDecoder(nn.Module):
    def __init__(self, 
                 dim,            # hidden_dim
                 depth,          # num_decoder
                 heads,
                 dim_head,
                 mlp_dim=2048,
                 dropout = 0.,
                 act='relu',
                 return_intermediate=False):
        super().__init__()
        # build encoder
        self.return_intermediate = return_intermediate
        self.decoders = nn.ModuleList([
                                TransformerDecoderLayer(
                                    dim, 
                                    heads, 
                                    dim_head, 
                                    mlp_dim, 
                                    dropout, 
                                    act) for _ in range(depth)])

    def forward(self, tgt, memory, pos=None, query_pos=None):
        intermediate = []
        for m in self.decoders:
            tgt = m(tgt, memory, pos, query_pos)
            if self.return_intermediate:
                intermediate.append(tgt)

        if self.return_intermediate:
            # [M, B, N, d]
            return torch.stack(intermediate)

        return tgt.unsqueeze(0) # [B, N, C] -> [1, B, N, C]


# Transformer
class Transformer(nn.Module):
    def __init__(self, 
                 dim,            # hidden_dim
                 num_encoders,
                 num_decoders,
                 num_heads,
                 dim_head,
                 mlp_dim = 2048,
                 dropout = 0.,
                 act = 'relu',
                 return_intermediate = False):
        super().__init__()
        self.encoder = TransformerEncoder(
            dim = dim,
            depth = num_encoders,
            heads = num_heads,
            dim_head = dim_head,
            mlp_dim = mlp_dim,
            dropout = dropout,
            act = act
        )
        self.decoder = TransformerDecoder(
            dim = dim,
            depth = num_decoders,
            heads = num_heads,
            dim_head = dim_head,
            mlp_dim = mlp_dim,
            dropout = dropout,
            act = act,
            return_intermediate = return_intermediate
        )

    def forward(self, x, query_embed=None, pos_embed=None):
        bs, c, h, w = x.size()
        # [B, C, H, W] -> [B, C, HW] -> [B, HW, C]
        x = x.flatten(2).permute(0, 2, 1)
        pos_embed = pos_embed.flatten(2).permute(0, 2, 1)
        # [N, C] -> [1, N, C] -> [B, N, C]
        query_embed = query_embed.unsqueeze(0).repeat(bs, 1, 1)

        tgt = torch.zeros_like(query_embed)
        # encoder
        memory = self.encoder(x, pos_embed)
        # decoder
        tgt = self.decoder(tgt, memory, pos_embed, query_embed)

        return tgt, memory.permute(0, 2, 1).view(bs, c, h, w)


def build_transformer(args):
    return Transformer(
        dim=args.hidden_dim,
        num_encoders=args.num_encoders,
        num_decoders=args.num_decoders,
        num_heads=args.num_heads,
        dim_head=args.hidden_dim // args.num_heads,
        mlp_dim=args.mlp_dim,
        dropout=args.dropout,
        return_intermediate=args.aux_loss
    )