
import torch
import logging
import torchvision
from torch import nn

from model.layers import Flatten, L2Norm, GeM
from backbone import vit, cvt, cct

CHANNELS_NUM_IN_LAST_CONV = {           # questi dipendono dall'architettura della rete
        "resnet18": 512,
        "resnet50": 2048,
        "resnet101": 2048,
        "resnet152": 2048,
        "vgg16": 512,
        "vit224": 224,
        "vit384": 384,
        "cvt224": 224,
        "cvt384": 384,
        "cct224": 224,
        "cct384": 384
    }


class GeoLocalizationNet(nn.Module):                        # questa è la rete principale
    def __init__(self, backbone, fc_output_dim, layers = 2):            # l'oggetto della classe parent è creato in funzione della backbone scelta
        super().__init__()
        self.backbone, features_dim = get_backbone(backbone, layers)
        self.aggregation = nn.Sequential(                   # container sequenziale di layers, che sono appunto eseguiti in sequenza come una catena
                L2Norm(),                                   # questi sono le classi definite in layers
                GeM(),
                Flatten(),
                nn.Linear(features_dim, fc_output_dim),     # applica la trasformazione y = x @ A.T + b dove A sono i parametri della rete in quel punto 
                L2Norm()                                    # e b è il bias aggiunto se è passato bias=True al modello. I pesi e il bias sono inizializzati
            )                                               # random dalle features in ingresso
        self.backbone_name = backbone
    
    def forward(self, x):
        if self.backbone_name in ["vit224", "vit384", "cvt224", "cvt384", "cct224", "cct384"]:
            x = self.backbone(x)    # con transformers ritorna feature di dim [32, num_classes]
            print(x.shape)
        else:
            x = self.backbone(x)    # con resnet18 esce [32, 512, 7, 7]
            x = self.aggregation(x) # con resnet18 esce [32, 512]
        return x


def get_backbone(backbone_name, layers = 2):                            # backbone_name è uno degli argomenti del programma
    if backbone_name.startswith("resnet"):
        if backbone_name == "resnet18":
            backbone = torchvision.models.resnet18(pretrained=True)     # loading del modello già allenato
        elif backbone_name == "resnet50":
            backbone = torchvision.models.resnet50(pretrained=True)
        elif backbone_name == "resnet101":
            backbone = torchvision.models.resnet101(pretrained=True)
        elif backbone_name == "resnet152":
            backbone = torchvision.models.resnet152(pretrained=True)
        
        for name, child in backbone.named_children():               # ritorna un iteratore che permette di iterare sui moduli nella backbone
                                                                    # restituendo una tupla con nome e modulo per ogni elemento
            if name == "layer3":  # Freeze layers before conv_3
                break                                               # fa il freeze di tutti i layers precedenti in modo da non 
            for params in child.parameters():                       # perdere informazioni durante il transfer learning
                params.requires_grad = False                        # freeza i parametri del modello in modo che questi non cambino durante l'ottimizzazione   
        logging.debug(f"Train only layer3 and layer4 of the {backbone_name}, freeze the previous ones")
        layers = list(backbone.children())[:-2]                     # rimuove gli utlimi due layers della backbone (avg pooling and FC layer) in modo
                                                                    # da poterci attaccare i successivi del nuovo modello (aggregation)
        backbone = torch.nn.Sequential(*layers)                         # crea una backbone dopo la manipolazione dei layers


    elif backbone_name == "vgg16":                                  # qui fa la stessa cosa con questa backbone
        backbone = torchvision.models.vgg16(pretrained=True)
        layers = list(backbone.features.children())[:-2]  # Remove avg pooling and FC layer
        for layer in layers[:-5]:
            for p in layer.parameters():
                p.requires_grad = False
        logging.debug("Train last layers of the VGG-16, freeze the previous ones")

        backbone = torch.nn.Sequential(*layers)                         # crea una backbone dopo la manipolazione dei layers

    elif backbone_name == "vit224": # Vision Transformer Lite            224x224 
        backbone = vit.vision_transformer_lite(layers, CHANNELS_NUM_IN_LAST_CONV[backbone_name]  )
    elif backbone_name == "cvt224": # Convolutional Vision Transformer   224x224 
        backbone = cvt.convolutional_vision_transformer(layers, CHANNELS_NUM_IN_LAST_CONV[backbone_name]  )
    elif backbone_name == "cct284": # Convolutional Compact Transformer  224x224 
        backbone = cct.convolutional_compact_transformer(layers, CHANNELS_NUM_IN_LAST_CONV[backbone_name]  )
    elif backbone_name == "vit384": # Vision Transformer Lite            384x384 
        backbone = vit.vision_transformer_lite(layers, CHANNELS_NUM_IN_LAST_CONV[backbone_name]  )
    elif backbone_name == "cvt384": # Convolutional Vision Transformer   384x384 
        backbone = cvt.convolutional_vision_transformer(layers, CHANNELS_NUM_IN_LAST_CONV[backbone_name]  )
    elif backbone_name == "cct384": # Convolutional Compact Transformer  384x384 
        backbone = cct.convolutional_compact_transformer(layers, CHANNELS_NUM_IN_LAST_CONV[backbone_name]  )
   
    features_dim = CHANNELS_NUM_IN_LAST_CONV[backbone_name]         # prende la dimensione corretta dell'utlimo layer in modo da poterla
                                                                    # mettere come dimensione di input per il linear layer successivo                                     
    return backbone, features_dim

