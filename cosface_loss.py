
# Based on https://github.com/MuggleWang/CosFace_pytorch/blob/master/layer.py

import torch
import torch.nn as nn
from torch.nn import Parameter
import math

# SphereFace: devo moltiplicare m all'angolo theta
# ArcFace: devo sommare m all'angolo theta
# CosFace: devo sommare m al coseno

# dim (int) = dimensione where cosine similarity is computed. default = 1
# eps (float) = small value to avoid division by zero. default = 1e-8

def cosine_sim(x1: torch.Tensor, x2: torch.Tensor, dim: int = 1, eps: float = 1e-8) -> torch.Tensor:
    ip = torch.mm(x1, x2.t()) # prodotto tra x1 e x2
    w1 = torch.norm(x1, 2, dim) # x1 feature vector, L2, dim
    w2 = torch.norm(x2, 2, dim) # x2 weight vector, L2, dim
    return ip / torch.ger(w1, w2).clamp(min=eps)

# mm: performs a matrix multiplication of the matrices x1 and x2.t
# ger: outer product of w1 and w2. if w1 is a vector of size n and w2 is a vector of size m, then out must be a matrix of size (N x M)
# clamp: clamp all elements in input into a range [min, max]. In this case we have only min

# In the testing stage, the face recognition score of a testing face pair is usually calculated according to cosine similarity between the two feature vectors.
# This suggests that the norm of feature vector x is not contributing to the scoring function. Thus in training stage, we fix ||x|| = s. Consequently, the posterior
# probability merely relies on cosine of angle. 

class MarginCosineProduct(nn.Module): # CosFace
    """Implement of large margin cosine distance:
    Args:
        in_features: size of each input sample
        out_features: size of each output sample
        s: norm of input feature
        m: margin
    """
    def __init__(self, in_features: int, out_features: int, s: float = 30.0, m: float = 0.40):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.s = s
        self.m = m  # ho m una uguale per tutti e 3 i casi SphereFace, ArcFace e CosFace
        self.weight = Parameter(torch.Tensor(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)
    
    # tensor.zeros_like() = return a tensor filled with the scalar value 0, with the same size of input
    # equivale a torch.zeros(input.size(), dtype=input.dtype, layout=input.layout, device=input.device).
    # tensor.scatter(dim, index, src, reduce = None) = scrive tutti i valori dal tensore src dentro self agli indici specificati del tensore
    # tensor.view() = ritorna un nuovo tensor con gli stessi dati del self tensor ma con forma diversa

#     def forward(self, x, y):
#         with torch.no_grad():
#             self.w.data = F.normalize(self.w.data, dim=0)

#         cos_theta = F.normalize(x, dim=1).mm(self.w)
#         with torch.no_grad():
#             d_theta = torch.zeros_like(cos_theta)
#             d_theta.scatter_(1, y.view(-1, 1), -self.m, reduce='add')

#         logits = self.s * (cos_theta + d_theta)
#         loss = F.cross_entropy(logits, y)

#         return loss

    def forward(self, inputs: torch.Tensor, label: torch.Tensor) -> torch.Tensor:
        cosine = cosine_sim(inputs, self.weight) # calcola la cosine similarity, cos(theta)
        one_hot = torch.zeros_like(cosine) # tensor di 0 con la stessa dimensione di cosine
        one_hot.scatter_(1, label.view(-1, 1), 1.0)
        # dim = 1 ottiene un tensor colonna, con indici le label, valori tutti 1 che andrà a moltiplicare per m, e sottrarrà il tutto a cosine
        output = self.s * (cosine - one_hot * self.m) # perché non usa add ma si crea one_hot?
        return output
    
    def __repr__(self):
        return self.__class__.__name__ + '(' \
               + 'in_features=' + str(self.in_features) \
               + ', out_features=' + str(self.out_features) \
               + ', s=' + str(self.s) \
               + ', m=' + str(self.m) + ')'

#################### ArcFace (ArcFace) ###############################################

class ArcFace(nn.Module):
    """Implement of large margin cosine distance:
    Args:
        in_features: size of each input sample
        out_features: size of each output sample
        s: norm of input feature
        m: margin
    """
    def __init__(self, in_features: int, out_features: int, s: float = 64.0, m: float = 0.5): # modificati da s = 30, m = 0.4
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.s = s
        self.m = m
        self.weight = Parameter(torch.Tensor(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)
    
    # tensor.where(condition, x, y) ritorna un tensor di element selezionati da x o y, dipendente dalla condizione
    # tensor.acos(input, *, out = None) = calcola l'inverso del coseno per ogni elemento in input
    # tensor.cos(input, *, out = None) = calcola il coseno per ogni elemento in input
    # tensor.no_grad(): context-manager that disabled gradient calculation. Disabling gradient calculation is useful for inference, when you are sure that you will not call tensor.backward().
    #                   It will reduce memory consuption for computations that would otherwise have requires_grad=True

    def forward(self, inputs: torch.Tensor, label: torch.Tensor) -> torch.Tensor:
        cos_theta = cosine_sim(inputs, self.weight) # calcola la cosine similarity, cos(theta)

        with torch.no_grad():
            theta_m = torch.acos(cos_theta.clamp(-1+1e-5, 1-1e-5)) # clamp serve? non lo faccio già nella cosine_sim?
            theta_m.scatter_(1, label.view(-1, 1), self.m, reduce='add')
            theta_m.clamp_(1e-5, 3.14159)
            d_theta = torch.cos(theta_m) - cos_theta

        logits = self.s * (cos_theta + d_theta)
        # loss = F.cross_entropy(logits, label)
        # return loss
        return logits
    
    def __repr__(self):
        return self.__class__.__name__ + '(' \
               + 'in_features=' + str(self.in_features) \
               + ', out_features=' + str(self.out_features) \
               + ', s=' + str(self.s) \
               + ', m=' + str(self.m) + ')'

#################### SphereFace (A-softmax) ###############################################

class SphereFace(nn.Module):
    """Implement of large margin cosine distance:
    Args:
        in_features: size of each input sample
        out_features: size of each output sample
        s: norm of input feature
        m: margin
    """
    def __init__(self, in_features: int, out_features: int, s: float = 30.0, m: float = 1.5): # modificati da s = 30, m = 0.4
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.s = s
        self.m = m # m >= 1
        self.weight = Parameter(torch.Tensor(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)
    
    # tensor.where(condition, x, y) ritorna un tensor di element selezionati da x o y, dipendente dalla condizione
    # tensor.acos(input, *, out = None) = calcola l'inverso del coseno per ogni elemento in input
    # tensor.cos(input, *, out = None) = calcola il coseno per ogni elemento in input

    def forward(self, inputs: torch.Tensor, label: torch.Tensor) -> torch.Tensor:
        cos_theta = cosine_sim(inputs, self.weight) # calcola la cosine similarity, cos(theta)

        with torch.no_grad():
            m_theta = torch.acos(cos_theta.clamp(-1.+1e-5, 1.-1e-5))
            m_theta.scatter_(1, label.view(-1, 1), self.m, reduce = 'multiply')

            k = (m_theta / math.pit).floor()
            sign = -2 * torch.remainder(k, 2) + 1 # (-1)**k
            phi_theta = sign * torch.cos(m_theta) - 2. * k
            d_theta = phi_theta - cos_theta

        logits = self.s * (cos_theta + d_theta)
        return logits

    def __repr__(self):
        return self.__class__.__name__ + '(' \
               + 'in_features=' + str(self.in_features) \
               + ', out_features=' + str(self.out_features) \
               + ', s=' + str(self.s) \
               + ', m=' + str(self.m) + ')'


# IMPLEMENTAZIONE COSFACE, ARCFACE e SPHERE FACE: https://opensphere.world/

#################### CosFace ##############################################################

# class CosFace(nn.Module):
#     """reference1: <CosFace: Large Margin Cosine Loss for Deep Face Recognition>
#        reference2: <Additive Margin Softmax for Face Verification>
#     """
#     def __init__(self, feat_dim, num_class, s=64., m=0.35):
#         super(CosFace, self).__init__()
#         self.feat_dim = feat_dim
#         self.num_class = num_class
#         self.s = s
#         self.m = m
#         self.w = nn.Parameter(torch.Tensor(feat_dim, num_class))
#         nn.init.xavier_normal_(self.w)

#     def forward(self, x, y):
#         with torch.no_grad():
#             self.w.data = F.normalize(self.w.data, dim=0)

#         cos_theta = F.normalize(x, dim=1).mm(self.w)
#         with torch.no_grad():
#             d_theta = torch.zeros_like(cos_theta)
#             d_theta.scatter_(1, y.view(-1, 1), -self.m, reduce='add')

#         logits = self.s * (cos_theta + d_theta)
#         loss = F.cross_entropy(logits, y)

#         return loss

#################### ArcFace ##############################################################

# class ArcFace(nn.Module):
#     """ reference: <Additive Angular Margin Loss for Deep Face Recognition>
#     """
#     def __init__(self, feat_dim, num_class, s=64., m=0.5):
#         super(ArcFace, self).__init__()
#         self.feat_dim = feat_dim
#         self.num_class = num_class
#         self.s = s
#         self.m = m
#         self.w = nn.Parameter(torch.Tensor(feat_dim, num_class))
#         nn.init.xavier_normal_(self.w)

#     def forward(self, x, y):
#         with torch.no_grad():
#             self.w.data = F.normalize(self.w.data, dim=0)

#         cos_theta = F.normalize(x, dim=1).mm(self.w)
#         with torch.no_grad():
#             theta_m = torch.acos(cos_theta.clamp(-1+1e-5, 1-1e-5))
#             theta_m.scatter_(1, y.view(-1, 1), self.m, reduce='add')
#             theta_m.clamp_(1e-5, 3.14159)
#             d_theta = torch.cos(theta_m) - cos_theta

#         logits = self.s * (cos_theta + d_theta)
#         loss = F.cross_entropy(logits, y)

#         return loss

#################### SphereFace ##############################################################

# class SphereFace(nn.Module):
#     """ reference: <SphereFace: Deep Hypersphere Embedding for Face Recognition>"
#         It also used characteristic gradient detachment tricks proposed in
#         <SphereFace Revived: Unifying Hyperspherical Face Recognition>.
#     """
#     def __init__(self, feat_dim, num_class, s=30., m=1.5):
#         super(SphereFace, self).__init__()
#         self.feat_dim = feat_dim
#         self.num_class = num_class
#         self.s = s
#         self.m = m
#         self.w = nn.Parameter(torch.Tensor(feat_dim, num_class))
#         nn.init.xavier_normal_(self.w)

#     def forward(self, x, y):
#         # weight normalization
#         with torch.no_grad():
#             self.w.data = F.normalize(self.w.data, dim=0)

#         # cos_theta and d_theta
#         cos_theta = F.normalize(x, dim=1).mm(self.w)
#         with torch.no_grad():
#             m_theta = torch.acos(cos_theta.clamp(-1.+1e-5, 1.-1e-5))
#             m_theta.scatter_(
#                 1, y.view(-1, 1), self.m, reduce='multiply',
#             )
#             k = (m_theta / math.pi).floor()
#             sign = -2 * torch.remainder(k, 2) + 1  # (-1)**k
#             phi_theta = sign * torch.cos(m_theta) - 2. * k
#             d_theta = phi_theta - cos_theta

#         logits = self.s * (cos_theta + d_theta)
#         loss = F.cross_entropy(logits, y)

#         return loss
