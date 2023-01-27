
import torch
import logging
import torchvision
from torch import nn

from model.layers import Flatten, L2Norm, GeM, SpatialAttention2d


CHANNELS_NUM_IN_LAST_CONV = {           # questi dipendono dall'architettura della rete
        "resnet18": 512,
        "resnet50": 2048,
        "resnet101": 2048,
        "resnet152": 2048,
        "vgg16": 512,
    }


class GeoLocalizationNet(nn.Module):                        # questa è la rete principale
    def __init__(self, backbone, fc_output_dim):            # l'oggetto della classe parent è creato in funzione della backbone scelta
        super().__init__()
        backbone_until_3, layers_4, features_dim = get_backbone(backbone)
        self.backbone_until_3 = backbone_until_3
        self.layers_4 = layers_4
        self.aggregation = nn.Sequential(                   # container sequenziale di layers, che sono appunto eseguiti in sequenza come una catena
                L2Norm(),                                   # questi sono le classi definite in layers
                GeM(),
                Flatten(),
                nn.Linear(features_dim, fc_output_dim),     # applica la trasformazione y = x @ A.T + b dove A sono i parametri della rete in quel punto 
                L2Norm()                                    # e b è il bias aggiunto se è passato bias=True al modello. I pesi e il bias sono inizializzati
            )                                               # random dalle features in ingresso
        self.self.localmodel = SpatialAttention2d(1024)     # 1024?
    
    def forward(self, x):
        feature_map = self.backbone_until_3(x)              # prima entra nella backbone
        x = self.layers_4(feature_map)
        global_features = self.aggregation(x)               # in realtà per le global features mancherebbe il cosFace

        feature_map = feature_map.detach()                  # separa il tensore dal computational graph ritornando un nuovo tensore che non richiede un gradiente
        # feature_map.requires_grad = False                 # è la stessa cosa? Evita al gradiente di non tornare indietro?
        local_feature, att_score = self.localmodel(feature_map)

        return feature_map, global_features


def get_backbone(backbone_name):                            # backbone_name è uno degli argomenti del programma
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
        layers_until_3 = list(backbone.children())[:-3]             # questo non è freezato, ragionare su sta cosa
        layers_4 = list(backbone.children())[-3]                    # rimuove gli utlimi due layers della backbone (avg pooling and FC layer) in modo
                                                                    # da poterci attaccare i successivi del nuovo modello (aggregation)
    
    elif backbone_name == "vgg16":                                  # qui fa la stessa cosa con questa backbone
        backbone = torchvision.models.vgg16(pretrained=True)
        layers = list(backbone.features.children())[:-2]            # Remove avg pooling and FC layer
        for layer in layers[:-5]:
            for p in layer.parameters():
                p.requires_grad = False
        logging.debug("Train last layers of the VGG-16, freeze the previous ones")
    
    backbone_until_3 = torch.nn.Sequential(*layers_until_3)         # backbone fino al layer 3, necessaria per recuperare la feature map
    # backbone = torch.nn.Sequential(*layers)                         # crea una backbone dopo la manipolazione dei layers
    
    features_dim = CHANNELS_NUM_IN_LAST_CONV[backbone_name]         # prende la dimensione corretta dell'utlimo layer in modo da poterla
                                                                    # mettere come dimensione di input per il linear layer successivo
    return backbone_until_3, layers_4, features_dim
