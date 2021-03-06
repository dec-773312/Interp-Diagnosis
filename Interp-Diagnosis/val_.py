# -*- coding: utf-8 -*-
"""Projectcode.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1tU3EbOtWCHv5z-MSJs46KuTzPoGlrDnf
"""

torch_version_suffix = "+cu110"
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from tabulate import tabulate
from torch import nn
from torch.utils.data import Dataset, DataLoader

import clip
from clip.simple_tokenizer import SimpleTokenizer

device = "cuda" if torch.cuda.is_available() else "cpu"

# %matplotlib inline
# %config InlineBackend.figure_format = 'retina'

_tokenizer = SimpleTokenizer()

def tokenize(texts, context_length: int = 77) -> torch.LongTensor:
    if isinstance(texts, str):
        texts = [texts]

    sot_token = _tokenizer.encoder["<|startoftext|>"]
    eot_token = _tokenizer.encoder["<|endoftext|>"]
    all_tokens = [[sot_token] + _tokenizer.encode(text) + [eot_token] for text in texts]
    result = torch.zeros(len(all_tokens), context_length, dtype=torch.long)

    for i, tokens in enumerate(all_tokens):
        n = min(len(tokens), context_length)
        result[i, :n] = torch.tensor(tokens)[:n]
        if len(tokens) > context_length:
            result[i, -1] = tokens[-1]

    return result

class RollingMean():
    def __init__(self):
        self.n = 0
        self.mean = 0
        
    def update(self, value):
        self.mean = (self.mean * self.n + value) / (self.n+1)
        self.n += 1
        
    def result(self):
        return self.mean

class MyDataset(Dataset):
    def __init__(self, df, images_path, transform):
        # super().__init__()
        self.transform = transform
        self.df = df
        self.images_path = images_path
        #self.classes = ['no','pre-proliferative','proliferative']
        self.classes = ['the diabetic retinopathy label level is normal',
                        'the diabetic retinopathy label level is background diabetic retinopathy',
                        'the diabetic retinopathy label level is degrees of referable diabetic retinopathy']
        data = {}
        for k,v in df.groupby('level'):
            if len(v) < 1000:
                data[k] = v
            else:
                data[k] = v.iloc[:len(v),:]
        self.data = pd.concat([data[i] for i in range(3) if i in data],axis=0)

    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        img_name, text = self.df.iloc[idx,:].values
        image = self.transform(Image.open(os.path.join(self.images_path, img_name+'.jpeg')))
        return image, text


class Metric():
    def __init__(self, CLASSES):
        self.CLASSES = CLASSES
        self.top1recall = {}
        self.top1precision = {}

    def clear(self):
        for i in range(len(self.CLASSES)):
            self.top1recall[i] = []
            self.top1precision[i] = []

    def update(self, similarity, labels):
        # similarity:Nx7 labels:N
        for i, label in enumerate(labels):
            tar = int(label)
            pre = similarity[i].topk(1).indices
            if pre == label:
                self.top1precision[int(pre)].append(1)
                self.top1recall[tar].append(1)
            else:
                self.top1precision[int(pre)].append(0)
                self.top1recall[tar].append(0)

    def report(self):
        table_header = ["class","Precision","Recall","F1"]
        table_data = []
        for i, cls in enumerate(self.CLASSES):
            recall = np.mean(self.top1recall[i])
            precision = np.mean(self.top1precision[i])
            f1 = 2 * (precision * recall) / (precision + recall)
            table_data.append((cls, str(precision)[:4], str(recall)[:4], str(f1)[:4]))

        print(tabulate(table_data, headers=table_header, tablefmt='grid'))

def val(batch_size):
    # Load CLIP
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess = clip.load('ViT-B/32', device)
    model.eval()
    #text = clip.tokenize(['no','pre-proliferative','proliferative']).to(device)

    classifier = nn.Sequential(nn.Linear(512, 64),
                            nn.ReLU(),
                            nn.Linear(64, 3),
                            nn.Sigmoid())

    checkpoint = torch.load("classifier1.pt")
    classifier.load_state_dict(checkpoint['model_state_dict'])
    classifier.eval()

    loss_img = nn.CrossEntropyLoss(weight=torch.FloatTensor([0.1, 1.5, 0.5])).to(device)

    total=0;
    correct=0;

    # load train data
    val_images_path = Path('/Users/shuumichi/Desktop/CLIP-main/data/train/train')

    df_val = pd.read_csv('/Users/shuumichi/Desktop/CLIP-main/data/train.csv')

    dsval = MyDataset(df_val, val_images_path, preprocess)

    dlval = DataLoader(dsval, batch_size=batch_size, shuffle=False, drop_last=False)

    texts = torch.cat([clip.tokenize(f"{dsval}") for dsval in dsval.classes]).to(device)
    text_features = model.encode_text(texts)
    metric = Metric(dsval.classes)
    metric.clear()
    # for images, labels in tqdm(dlval):
    with torch.no_grad():
        for images, labels in dlval:
        
            if labels.size()[0] != batch_size:
                continue

            image_features = model.encode_image(images.to(device))
            predictions = classifier(image_features)
            predictions = predictions.resize_(1,512)
            #text_features = textifier(text_features)
            similarity = (100.0 * predictions @ text_features.T).softmax(dim=-1)
            similarity = torch.where(torch.isnan(similarity), torch.full_like(similarity, 1e-8), similarity)
            metric.update(similarity.type(torch.float32), labels)
            total += 1
            if labels == similarity.topk(1).indices : correct += 1
            print(similarity)
        metric.report()
        accuracy = correct / total
        print(accuracy)

# model, preprocess = clip.load("ViT-B/32",device=device,jit=False) 
# checkpoint = torch.load("model.pt")
# model.load_state_dict(checkpoint['model_state_dict'])

def main():
    val(batch_size=1)

if __name__=="__main__":
    main()
