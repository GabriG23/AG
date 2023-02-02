import torch
import numpy as np
import matplotlib.pyplot as plt
from scipy import spatial
from skimage import feature
from skimage import measure
from skimage import transform

def CalculateKeypointCenters(boxes):
   # Helper function to compute feature centers, from RF boxes.
    # print(boxes)
    # x = boxes[:, :2]
    # y = boxes[:, 2:]
    # print(y)
    return torch.divide(torch.add(boxes[:, :2], boxes[:, 2:]),2.0)





def CalculateReceptiveBoxes(height, width, rf, stride, padding):
    x, y = torch.meshgrid(torch.arange(width), torch.arange(height))
    coordinates = torch.reshape(torch.stack([x, y], axis=2), [-1, 2])               #  ho girato x e y rispetto alla repo per fare uscire gli stessi valori
    # [y,x,y,x]
    point_boxes = torch.tensor(torch.concat([coordinates, coordinates], 1), dtype=torch.float32)        

    # point_boxes pare avere tutte le combinazioni possibili di coordinate che prevedono [y, x e y, x]    # anche se noi abbiamo messo x,y
    # ricontrollare in caso di errori
    bias = torch.tensor([-padding, -padding, -padding + rf - 1, -padding + rf - 1])
    rf_boxes = stride * point_boxes + bias
    return rf_boxes             # checked con i valori della repo

    # rf_boxes: [N, 4] receptive boxes tensor. Here N equals to height x width.
    # Each box is represented by [ymin, xmin, ymax, xmax].

def retrieve_locations_descriptors(feature_map, attention_prob):
    # extracted_local_features = {
    # 'local_features': {
    #     'locations': np.array([]),
    #     'descriptors': np.array([]),
    #     'scales': np.array([]),
    #     'attention': np.array([]),
    #         }
    # }

    rf, stride, padding = [211.0, 16.0, 105.0]                  # hard coded on the backbone structure

    # feature_map = torch.rand([1, 64, 32, 32])
    # attention_prob = torch.rand([1, 1, 32, 32])

    #eventuale scaling dell'immagine
    # attention_prob = attention_prob.squeeze(0)         
    # feature_map = feature_map.squeeze(0)

    rf_boxes = CalculateReceptiveBoxes(feature_map.shape[1], feature_map.shape[2], rf, stride, padding)

    attention_prob = attention_prob.view(-1)
    feature_map = feature_map.view(-1, feature_map.shape[0])          

    abs_thres = 0.5

    indices = (attention_prob >= abs_thres).nonzero().squeeze(1) 
    scale = 1

    selected_boxes = torch.index_select(rf_boxes, 0, indices)
    selected_features = torch.index_select(feature_map, 0, indices)
    selected_scores = torch.index_select(attention_prob, 0, indices)
    scales = torch.ones_like(selected_scores, dtype=torch.float32) / scale                 # dalla repo. Tensore di 1  riscalati rispetto alla scala

    # print(scales)

    # qua dovrebbe esserci il calcolo per la nuova scala (ma a sto punto credo che basterebbe richiamare il pezzo precedente)
    # a questo punto abbiamo un concatenamento dei risultati a scale diverse, una roba del genere:
    
    #     output_boxes = tf.concat([output_boxes, boxes], 0)
    # output_local_descriptors = tf.concat(
    #     [output_local_descriptors, local_descriptors], 0)
    # output_scales = tf.concat([output_scales, scales], 0)
    # output_scores = tf.concat([output_scores, scores], 0)

    # a qquesto punto salva le feature locali in una struttura dati chiamata BoxList, utilizzata tipicamente per object detection
    # ed esegue una non max suppression usando iou (che è 1 di default) e il numero di features salvate che ha l'unico di scopo di
    # eseguire un'altra thresold per rimuovere le features trovate nel caso in cui queste superino le mille unità

    # a questo punto occorerebbe calcolare i keypoints seguendo la pipeline

    locations = CalculateKeypointCenters(selected_boxes)
    print(locations)
    return locations, selected_features


# extract_local_features()

    
def match_features(query_locations,
                  query_descriptors,
                  index_image_locations,
                  index_image_descriptors,
                  ransac_seed=None,
                  descriptor_matching_threshold=0.9,
                  ransac_residual_threshold=10.0,
                  query_im_array=None,
                  index_im_array=None,
                  query_im_scale_factors=None,
                  index_im_scale_factors=None,
                  use_ratio_test=False):


    NUM_TO_RERANK = 100                                         # numero massimo di immagini di cui fare il re-rank
    _NUM_RANSAC_TRIALS = 1000
    _MIN_RANSAC_SAMPLES = 3

    num_features_query = query_locations.shape[0]               # numero di query features (saranno 1024)
    num_features_database_image = index_image_locations.shape[0]
    if not num_features_query or not num_features_database_image:
        print(f"database images and query don't have the same dimension")

    local_feature_dim = query_descriptors.shape[1]              # queste dovrebbero essere 64
    if index_image_descriptors.shape[1] != local_feature_dim:
        print(f"Local feature dimensionality is not consistent for query and database images.")

    # Construct KD-tree used to find nearest neighbors.
    index_image_tree = spatial.cKDTree(index_image_descriptors)

#   if use_ratio_test:                                  Se viene usato il ratio test. Possiamo provarlo in seguito
#     distances, indices = index_image_tree.query(
#         query_descriptors, k=2, n_jobs=-1)
#     query_locations_to_use = np.array([
#         query_locations[i,]
#         for i in range(num_features_query)
#         if distances[i][0] < descriptor_matching_threshold * distances[i][1]
#     ])
#     index_image_locations_to_use = np.array([
#         index_image_locations[indices[i][0],]
#         for i in range(num_features_query)
#         if distances[i][0] < descriptor_matching_threshold * distances[i][1]
#     ])
#   else:
    _, indices = index_image_tree.query(query_descriptors, distance_upper_bound=descriptor_matching_threshold, n_jobs=-1)

    # Select feature locations for putative matches.
    query_locations_to_use = np.array([query_locations[i,] for i in range(num_features_query) if indices[i] != num_features_database_image])
    # prende la locations di tutte le query per cui l'indice i-esimo è diverso dal numero totale di features
    # quindi le prende tutte fino a che non è arrivato a quel numero(ma -1?)
    
    database_image_locations_to_use = np.array([index_image_locations[indices[i],] for i in range(num_features_query) 
                                if indices[i] != num_features_database_image])
    # qua fa più o meno la stessa cosa ma prende specifcatamente alcune localtion (che sono quelle in cui sono presenti i descrittori?)


    # If there are not enough putative matches, early return 0.
    if query_locations_to_use.shape[0] <= _MIN_RANSAC_SAMPLES:
        print(f"There are no enough putative matches")

    # Perform geometric verification using RANSAC.
    _, inliers = measure.ransac(
        (database_image_locations_to_use, query_locations_to_use),
        transform.AffineTransform,
        min_samples=_MIN_RANSAC_SAMPLES,
        residual_threshold=ransac_residual_threshold,
        max_trials=_NUM_RANSAC_TRIALS,
        random_state=ransac_seed)

    if inliers is None:
        inliers = []
    # se gli passiamo anche le immagini, ce le plotta
    elif query_im_array is not None and index_im_array is not None:
        if query_im_scale_factors is None:
            query_im_scale_factors = [1.0, 1.0]
        if index_im_scale_factors is None:
            index_im_scale_factors = [1.0, 1.0]
    inlier_idxs = np.nonzero(inliers)[0]
    _, ax = plt.subplots()
    ax.axis('off')
    ax.xaxis.set_major_locator(plt.NullLocator())
    ax.yaxis.set_major_locator(plt.NullLocator())
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    plt.margins(0, 0)
    feature.plot_matches(
        ax,
        query_im_array,
        index_im_array,
        query_locations_to_use * query_im_scale_factors,
        database_image_locations_to_use * index_im_scale_factors,
        np.column_stack((inlier_idxs, inlier_idxs)),
        only_matches=True)

    # match_viz_io = io.BytesIO()
    # plt.savefig(match_viz_io, format='jpeg', bbox_inches='tight', pad_inches=0)
    # match_viz_bytes = match_viz_io.getvalue()

    # return sum(inliers), match_viz_bytes
    return sum(inliers)