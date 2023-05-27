
import faiss
import torch
import logging
import numpy as np
from tqdm import tqdm
from typing import Tuple
from argparse import Namespace
from torch.utils.data.dataset import Subset
from torch.utils.data import DataLoader, Dataset
from local_features_utils import retrieve_locations_descriptors, match_features

# Compute R@1, R@5, R@10, R@20
RECALL_VALUES = [1, 5, 10, 20]

# eval_ds.database_num
def test(args: Namespace, eval_ds: Dataset, model: torch.nn.Module) -> Tuple[np.ndarray, str]:      # restituisce l'array con le recall e un stringa che riporta i valori
    """Compute descriptors of the given dataset and compute the recalls."""
    
    model = model.eval()                                        # si mette il modello in evaluation mode
    with torch.no_grad():                                       # all'interno del ciclo, il gradient è disabilitato (requires_grad=False)
        logging.debug("Extracting database descriptors for evaluation/testing")
        database_subset_ds = Subset(eval_ds, list(range(eval_ds.database_num)))             # subset del dataset da valutare non considerando le immagini di query
        database_dataloader = DataLoader(dataset=database_subset_ds, num_workers=args.num_workers,
                                         batch_size=args.infer_batch_size, pin_memory=(args.device == "cuda"))  # creazione del dataloader in grado di iterare sul dataset
        all_descriptors = np.empty((len(eval_ds), args.fc_output_dim), dtype="float32")     # ritorna un vettore non inizializzato con una riga per ogni sample da valutare
        
        for images, indices in tqdm(database_dataloader, ncols=100):                        # e un numero di colonne pari alla dimensione di descrittori
            global_descriptors, _, _, _, _, _ = model(images.to(args.device))                                     # mette le immagini su device e ne calcola il risultato del MODELLO -> i descrittori
            global_descriptors = global_descriptors.cpu().numpy()                                         # porta i descrittori su cpu e li traforma da tensori ad array
            # local_descriptors = local_descriptors.cpu().numpy() 
            # attn_scores = attn_scores.cpu().numpy() 
            all_descriptors[indices.numpy(), :] = global_descriptors                               # riempie l'array mettendo ad ogni indice il descrittore calcolato
            # all_local_descriptors[indices.numpy(), :] = local_descriptors
            # all_att_prob[indices.numpy(), :] = attn_scores
        
        # database_local_descriptors = []
        # queries_att_prob = np.empty((eval_ds.queries_num, 1, 32, 32), dtype="float32")
        logging.debug("Extracting queries descriptors for evaluation/testing using batch size 1")
        queries_infer_batch_size = 1                                                        # sembra che venga valutata un'immagine per volta
        queries_subset_ds = Subset(eval_ds, list(range(eval_ds.database_num, eval_ds.database_num+eval_ds.queries_num)))        # in questo caso, crea un subset con sole query
        queries_dataloader = DataLoader(dataset=queries_subset_ds, num_workers=args.num_workers,
                                        batch_size=queries_infer_batch_size, pin_memory=(args.device == "cuda"))        # crea il dataloader associato a questo secondo subset
        for images, indices in tqdm(queries_dataloader, ncols=100):
            global_descriptors, _, _, _, local_descriptors, attn_scores = model(images.to(args.device))             # fa lo stesso lavoro precedente, calcolando per ogni immagine di query il descrittore
            global_descriptors = global_descriptors.cpu().numpy()
            local_descriptors = local_descriptors.cpu().numpy() 
            attn_scores = attn_scores.cpu().numpy() 
            all_descriptors[indices.numpy(), :] = global_descriptors                               # riempie l'array mettendo ad ogni indice il descrittore calcolato
            # queries_local_descriptors[indices.numpy(), :] = local_descriptors
            # queries_att_prob[indices.numpy(), :] = attn_scores      # rimepiendo il vettore all_descriptors 
    
    queries_global_descriptors = all_descriptors[eval_ds.database_num:]    # divide i descrittori delle queries
    # queries_local_descriptors = all_local_descriptors[eval_ds.database_num:]
    # queries_att_prob = all_att_prob[eval_ds.database_num:]

    database_global_descriptors = all_descriptors[:eval_ds.database_num]   # dai descrittori del database di immagini da classificare
    # database_local_descriptors = all_local_descriptors[:eval_ds.database_num]
    # database_att_prob = all_att_prob[:eval_ds.database_num]
                                                            
    faiss_index = faiss.IndexFlatL2(args.fc_output_dim)    
    faiss_index.add(database_global_descriptors)                 
    del database_global_descriptors, all_descriptors            
    
    logging.debug("Calculating recalls")
    distances, predictions = faiss_index.search(queries_global_descriptors, max(RECALL_VALUES))    # effettua la ricerca con i descrittori delle query con i valori di recall specificati
                                                            # questa parte quindi è svolta unicamente da questa libreria, che calcola la distanza euclidea (quindi la vicinanza)
                                                            # per ogni k (preso da RECALL_VALUES) immagini con le immagini di query. Più k è alto è più ho possibilità di prendere la 
                                                            # più vicina (lo si vede dopo)

    # print(predictions)
    #### For each query, check if the predictions are correct
    positives_per_query = eval_ds.get_positives()           # per ogni query, restituisce le immagini più vicine alla query di 25 mt
    recalls = np.zeros(len(RECALL_VALUES))                  # vettore di recalls iniziaizzato a zero
    for query_index, preds in enumerate(predictions):       # per ogni predizione, prende indice e relativa predizione
        
        # I used this approach to obtain the query and image descriptors due to Ram issues on colab
        if query_index % 10 == 0:
            print(f"\tRe-ranking: {query_index} out of {predictions.shape[0]}") 
        query_image, _ = queries_subset_ds[query_index]
        query_image = query_image.unsqueeze(0).to(args.device)

        _, _, _, _, queries_local_descriptors, queries_att_prob = model(query_image.to(args.device))
        database_local_descriptors = []
        database_att_prob = []
        for i, image_index in enumerate(preds):
            database_image, _ = database_subset_ds[image_index]
            database_image = database_image.unsqueeze(0).to(args.device)
            _, _, _, _, local_descriptors, attn_scores = model(database_image.to(args.device)) 
            local_descriptors = local_descriptors.detach().cpu()
            attn_scores = attn_scores.detach().cpu()
            database_local_descriptors.append(local_descriptors)
            database_att_prob.append(attn_scores) 
        reraked_preds = RerankByGeometricVerification(preds, distances[query_index], queries_local_descriptors.detach().cpu(), 
                                    queries_att_prob.detach().cpu(), database_local_descriptors, database_att_prob)
        for i, n in enumerate(RECALL_VALUES):               # per ogni valore delle recall values (sono 5 valori)
            # for j in range(20):
            print(f"reranked : {reraked_preds}")
            print(f"predictions : {predictions[query_index]}")
            print(f"positive : {positives_per_query[query_index]}")
            if np.any(np.in1d(reraked_preds[:n], positives_per_query[query_index])):    # controlla che ogni valore nel primo 1Darray (quindi penso descrittore, non immagine) sia contenuto 
                                                                                # nel secondo. Quindi per ogni n controlla se le predizioni fino ad n (le n più vicine) contengono 
                                                                                # la relativa immagine di query (np.any -> almeno 1)
                recalls[i:] += 1                                                # se si, aumenta la relativa recall
                break                                                           # ed esce perché tanto l'ha già trovata. Quindi si favoriscono recall più basse
    # Divide by queries_num and multiply by 100, so the recalls are in percentages
    recalls = recalls / eval_ds.queries_num * 100                               # valori di recall espressi in percentuale (cioè quante query in percentuale sono cadute in quel valore di recall)                                                                                    
    recalls_str = ", ".join([f"R@{val}: {rec:.1f}" for val, rec in zip(RECALL_VALUES, recalls)])    # valori di recall in stringa
    return recalls, recalls_str


def RerankByGeometricVerification(query_predictions, distances, query_descriptors, query_attention_prob, 
                    images_local_descriptors, images_attention_prob):
    # ranks_before_gv[i] = np.argsort(-similarities)      # tieni conto di questo!!!
    ransac_seed = 0
    descriptor_matching_threshold = 1.2
    ransac_residual_threshold = 30.0
    use_ratio_test = False

    for i in range(20):
      print(f"[{query_predictions[i]}, -, {distances[i]}]")
    query_locations, query_descriptors = retrieve_locations_descriptors(query_descriptors, query_attention_prob)

    # num_to_rerank = 100
    inliers_and_initial_scores = []                   # in 0 avrà l'indice della predizione, in 1 avrà gli outliers, in 2 avrà gli scores (già calcolati)
    for i, preds in enumerate(query_predictions):


        
        database_image_locations, database_image_descriptors = retrieve_locations_descriptors(images_local_descriptors[i].squeeze(0), 
                                                                    images_attention_prob[i].squeeze(0))

        inliers = match_features(
            query_locations.detach().numpy(),
            query_descriptors.detach().numpy(),
            database_image_locations.detach().numpy(),
            database_image_descriptors.detach().numpy(),
            ransac_seed=ransac_seed,
            descriptor_matching_threshold=descriptor_matching_threshold,
            ransac_residual_threshold=ransac_residual_threshold,
            use_ratio_test=use_ratio_test)

        inliers_and_initial_scores.append([preds, inliers, distances[i]])
        # print(f"inliers e distance : {inliers_and_initial_scores}")

    inliers_and_initial_scores = sorted(inliers_and_initial_scores, key=lambda x : (x[1], -x[2]), reverse=True)
        # così il ranking è fatto dando la precedenza agli inliers
        # parte di ricalcolo della recall una volta ottenuti gli inliers

    # print(f"inliers e distance : {inliers_and_initial_scores}")
    for x in inliers_and_initial_scores:
      print(x)

    change = 0
    new_rank = [x[0] for x in inliers_and_initial_scores]
    for i in range(20):
      if new_rank[i] != query_predictions[i]:
        change += 1
    print(change)




    return new_rank
