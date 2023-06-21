import torch.nn as nn
from .transformers import TransformerClassifier
from .tokenizer import Tokenizer
import logging


def convolutional_vision_transformer(fc_output_dim, layers):         # embedding_dim mettere 224
    if layers==2:
        return _cvt(num_layers=2, num_heads=2, mlp_ratio=1, embedding_dim=fc_output_dim, img_size=224)   # layers, attention head, Multi layer perceptron ratio, dimensione descrittori
    elif layers == 4:
        return _cvt(num_layers=4, num_heads=2, mlp_ratio=1, embedding_dim=fc_output_dim, img_size=224) 
    elif layers == 6:
        return _cvt(num_layers=6, num_heads=4, mlp_ratio=2, embedding_dim=fc_output_dim, img_size=224)
    elif layers == 7:
        return _cvt(num_layers=7, num_heads=4, mlp_ratio=2, embedding_dim=fc_output_dim, img_size=224)
    elif layers == 8:
        return _cvt(num_layers=8, num_heads=4, mlp_ratio=2, embedding_dim=fc_output_dim, img_size=224)
    else:
        raise ValueError(f"Wrong numbers of layers")

def _cvt(num_layers, num_heads, mlp_ratio, embedding_dim, img_size, kernel_size=4):

    model = CVT(num_layers=num_layers,
                num_heads=num_heads,
                mlp_ratio=mlp_ratio,
                embedding_dim=embedding_dim,
                kernel_size=kernel_size,
                img_size=img_size
                )

    return model

# CVT - Compact Vision Transformers: use Sequence Pooling that pools the entire sequence of toknes produced by the transformer

class CVT(nn.Module):
    def __init__(self,
                 img_size=224,
                 embedding_dim=224,
                 n_input_channels=3,
                 kernel_size=16,
                 dropout=0.,
                 attention_dropout=0.1,
                 stochastic_depth=0.1,
                 num_layers=14,
                 num_heads=6,
                 mlp_ratio=4.0,
                 positional_embedding='learnable'                       # dipende molto dal positional_embedding come Vit-Lite
                 ):
        super(CVT, self).__init__()

        assert img_size % kernel_size == 0, f"Image size ({img_size}) has to be" \
                                            f"divisible by patch size ({kernel_size})"

        self.tokenizer = Tokenizer(n_input_channels=n_input_channels,                       # canali input
                                   n_output_channels=embedding_dim,
                                   kernel_size=kernel_size,
                                   stride=kernel_size,
                                   padding=0,
                                   max_pool=False,
                                   activation=None,
                                   n_conv_layers=1,
                                   conv_bias=True)

        self.classifier = TransformerClassifier(
            sequence_length=self.tokenizer.sequence_length(n_channels=n_input_channels, height=img_size, width=img_size),
            embedding_dim=embedding_dim,
            seq_pool=True,              # questa è l'unica cosa che cambia da ViT
            dropout=dropout,
            attention_dropout=attention_dropout,
            stochastic_depth=stochastic_depth,
            num_layers=num_layers,
            num_heads=num_heads,
            mlp_ratio=mlp_ratio,
            positional_embedding=positional_embedding
        )

    def forward(self, x):
        x = self.tokenizer(x)
        x = self.classifier(x)
        return x
