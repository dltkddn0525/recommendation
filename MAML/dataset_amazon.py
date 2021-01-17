import numpy as np
import pandas as pd
import os
import json
import time
from gensim.models.doc2vec import Doc2Vec
from torch.utils.data import Dataset
import pickle

def load_data(path, feature_type):
    train_df = pd.read_csv(os.path.join(path, 'train.csv'), index_col=None, usecols=None)    
    test_df = pd.read_csv(os.path.join(path, 'test.csv'), index_col=None, usecols=None)

    # item ID = 2405 split: train 3 test 2
    item_2405 = test_df[test_df["itemID"] == 2405][:3]
    train_df = train_df.append(item_2405)
    test_df = test_df.drop(item_2405.index)

    # Inspect : at least 3 interaction per user for train, 2 per user for test
    # train_x_user, train_x_num_rating = inspect(train_df,3)
    # test_x_user, test_x_num_rating = inspect(test_df,2)
    # print(f"Inspectation : Train = {len(train_x_user)} Users, Test = {len(test_x_user)} Users")

    num_user = max(train_df["userID"]) + 1
    num_item = max(train_df["itemID"]) + 1

    test_negative = []
    train_ng_pool = []

    total_item = np.arange(0, num_item)

    for user in range(num_user):
        trn_positive_item = train_df[train_df['userID'] == user]['itemID'].tolist()
        tst_positive_item = test_df[test_df['userID'] == user]['itemID'].tolist()
        # train ng pool = Every item - user's train positive item
        train_ng_item_u = np.setdiff1d(total_item, trn_positive_item)
        # test ng item = Every item - user's train positive item & test positive item
        test_ng_item_u = np.setdiff1d(train_ng_item_u, tst_positive_item)
        train_ng_pool.append(train_ng_item_u.tolist())
        test_negative.append(test_ng_item_u.tolist())

    test_df = pd.DataFrame(test_df[['userID', 'itemID']])
    test_df['rating'] = 1

    doc2vec_model = Doc2Vec.load(os.path.join(path, 'doc2vecFile'))
    vis_vec = np.load(os.path.join(path, 'image_feature.npy'), allow_pickle=True).item()

    asin_dict = json.load(open(os.path.join(path, 'asin_sample.json'), 'r'))

    text_vec = {}
    for asin in asin_dict:
        text_vec[asin] = doc2vec_model.docvecs[asin]

    asin_i_dic = {}
    for index, row in train_df.iterrows():
        asin, i = row['asin'], int(row['itemID'])
        asin_i_dic[i] = asin

    t_features = []
    v_features = []
    for i in range(num_item):
        t_features.append(text_vec[asin_i_dic[i]])
        v_features.append(vis_vec[asin_i_dic[i]])
    if feature_type == "all":
        feature = np.concatenate((t_features, v_features), axis=1)
    elif feature_type == "img":
        feature = np.array(v_features)
    elif feature_type == "txt":
        feature = np.array(t_features)
    train_df = pd.DataFrame(train_df[["userID", "itemID"]])

    return train_df, test_df, train_ng_pool, test_negative, num_user, num_item, feature


class CustomDataset_amazon(Dataset):
    '''
    Train Batch [user, item_p, item_n, feature_p, feature_n]
    user = [N]
    item_p = [N]
    item_n = [N x num_neg]
    feature_p = [N x (vis_feature_dim + text_feature_dim)]
    featuer_n = [N x num_neg x (vis_feature_dim + text_feature_dim)]
    Test Batch [user, item, feature, label]
    N = number of positive + negative item for corresponding user
    user = [1]
    item = [N]
    feature = [N x (vis_feature_dim + text_feature_dim)]
    label = [N] 1 for positive, 0 for negative
    '''

    def __init__(self, dataset, feature, negative, num_neg=4, istrain=False, use_feature = True):
        super(CustomDataset_amazon, self).__init__()
        self.dataset = dataset # df
        self.feature = feature # numpy
        self.negative = np.array(negative) # list->np
        self.istrain = istrain
        self.num_neg = num_neg
        self.use_feature = use_feature

        if not istrain:
            self.make_testset()
        else:
            self.dataset = np.array(self.dataset)

    def make_testset(self):
        assert not self.istrain
        users = np.unique(self.dataset["userID"])
        test_dataset = []
        for user in users:
            test_negative = self.negative[user]
            test_positive = self.dataset[self.dataset["userID"] == user]["itemID"].tolist()
            item = test_positive + test_negative
            label = np.zeros(len(item))
            label[:len(test_positive)] = 1
            label = label.tolist()
            test_user = np.ones(len(item)) * user
            test_dataset.append([test_user.tolist(), item, label])

        self.dataset = test_dataset

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, index):
        if self.istrain:
            user, item_p = self.dataset[index]
            # Negative sampling
            ng_pool = np.array(self.negative[user])
            idx = np.random.choice(len(ng_pool),self.num_neg,replace=False)
            item_n = ng_pool[idx].tolist()
            if self.use_feature:
                feature_p = self.feature[item_p]
                feature_n = self.feature[item_n]
                return user, item_p, item_n, feature_p, feature_n
            else:
                return user, item_p, item_n, 0.0, 0.0
        else:
            user, item, label = self.dataset[index]
            if self.use_feature:
                feature = self.feature[item]
                return user, item, feature, label
            else:
                return user, item, 0.0, label


def inspect(df, num_inter):
    user = np.unique(df["userID"])
    x_user = []
    x_num_rating = []
    for i in user:
        if len(df[df["userID"] == i]) < num_inter:
            x_user.append(i)
            x_num_rating.append(len(df[df["userID"] == i]))

    return x_user, x_num_rating
