import numpy as np
import pandas as pd
import random
import os
import json
import time
from torch.utils.data import Dataset
import pickle
from PIL import Image
import torchvision.transforms as transforms
import torchvision.models as M
import torch

def load_data(data_path, feature_type):
    feature_dir = os.path.join(data_path,'../')
    train_df = pd.read_feather(os.path.join(data_path, 'train_positive.ftr'))
    test_df = pd.read_feather(os.path.join(data_path, 'test_positive.ftr'))
    train_ng_pool = pd.read_feather(os.path.join(data_path, 'train_negative.ftr'))
    test_negative = pd.read_feather(os.path.join(data_path, 'test_negative.ftr'))
    
    
    train_df = train_df.astype('int64')
    test_df = test_df.astype('int64')
    train_df.rename(columns={"userid":"userID","train_pos":"itemID"}, inplace=True)
    test_df.rename(columns={"userid":"userID","test_pos":"itemID"}, inplace=True)
    train_ng_pool = train_ng_pool["train_negative"].tolist()
    test_negative = test_negative["test_negative"].tolist()
    
    index_info = pd.read_csv(os.path.join(data_path,'../index-info/item_index.csv'))
    
    num_user = max(train_df["userID"])+1
    num_item = max(train_df["itemID"])+1

    index_list = index_info["itemidx"].tolist()
    id_list = index_info["itemid"].tolist()

    with open(os.path.join(feature_dir,"item_meta.json"), "rb") as f:
        meta_data = json.load(f)

    image_path_list = [] 

    for item_id in id_list:

        img_path = meta_data[f"{item_id}"]["image_path"]
        image_path_list.append(os.path.abspath(os.path.join(feature_dir, img_path)))


    image_path_list = np.array(image_path_list)
    images = []

    start = time.time()
    if feature_type == "all" or feature_type == "img":
        transform = transforms.Compose([transforms.Resize((224,224)),
                                            transforms.ToTensor(),
                                            transforms.Normalize((0.5,),(0.5,))])
        
        for i in range(len(image_path_list)):
            img = Image.open(image_path_list[i]).convert("RGB")
            img = transform(img)
            images.append(img)
            
    end = time.time()
    print(f"Data Loaded {end-start}. num user : {num_user} num item : {num_item}")
    
    return train_df, test_df, train_ng_pool, test_negative, num_user, num_item, torch.stack(images)


class CustomDataset(Dataset):
    '''
    Train Batch [user, item_p, item_n, pos_set, feature_p]
    user = [1]
    item_p = [1]
    item_n = [1]
    pos_set = [1 x p]
    feature_p = [1 x p x f]

    Test Batch [user, item, pos_set, feature_p]
    N = number of positive + negative item for corresponding user
    user = [1]
    item = [N]
    pos_set = [1 x p]
    feature_p = [1 x p x f]

    '''

    def __init__(self, train, test, images, negative, istrain=False, feature_type = "all",num_sam = 1):
        super(CustomDataset, self).__init__()
        self.istrain = istrain
        self.train = train # df
        self.images = images # Tensor
        self.positive_set = train.groupby("userID")["itemID"].apply(np.array)
        self.negative = np.array(negative) # list->np
        self.feature_type = feature_type
        if not istrain:
            self.test = np.array(test)
        self.train = np.array(train)
        self.num_sam = num_sam

    def __len__(self):
        if self.istrain:
            return len(self.train)
        else:
            return len(self.test)

    def __getitem__(self, index):
        if self.istrain:
            user, item_p = self.train[index]
            positives = self.positive_set[user]
            
          
            users = np.repeat(user,self.num_sam)         
            users = user.reshape(-1,self.num_sam)             
            # Negative Sampling
            ng_pool = self.negative[user]
            ng_idx = np.random.choice(len(ng_pool),1)
            item_n = ng_pool[ng_idx].reshape(-1)

            img_p = self.images[positives]
            #img_p = np.expand_dims(img_p, axis=1)
            #img_p = img_p.reshape(-1,self.num_sam)
            positives = positives.reshape(-1,self.num_sam)
            return users, item_p, item_n, positives, img_p

        else:
            user, _ = self.train[index]
            positives = self.positive_set[user]
            

            users = np.repeat(user,self.num_sam)
            users = user.reshape(-1,self.num_sam)
                
            img_p = self.images[positives]
            img_p = img_p.reshape(-1,self.num_sam)
            
            _,test_positive = self.test[user]
            test_negative = self.negative[user]
            positives = positives.reshape(-1,self.num_sam)
            return users, test_positive, test_negative, positives, img_p
