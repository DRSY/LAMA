'''
Author: roy
Date: 2020-10-30 22:18:56
LastEditTime: 2020-11-10 09:22:35
LastEditors: Please set LastEditors
Description: In User Settings Edit
FilePath: /LAMA/utils.py
'''
from transformers import AutoModelForMaskedLM, AutoTokenizer
import copy
import torch
import torch.nn as nn
import torch.nn.utils.prune as prune
from torch.distributions import Bernoulli
import jsonlines
import prettytable as pt
import sys

from typing import List, Dict
from tqdm import tqdm


class FoobarPruning(prune.BasePruningMethod):
    """
    Customized Pruning Method
    """
    PRUNING_TYPE = 'unstructured'

    def __init__(self, pregenerated_mask) -> None:
        super().__init__()
        self.pre_generated_mask = pregenerated_mask

    def compute_mask(self, t, default_mask):
        """
        """
        mask = self.pre_generated_mask
        return mask


def Foobar_pruning(module, name, mask=None):
    """
    util function for pruning parameters of given module.name using corresponding mask generated by relation-specific mask generator
    Parameters:
    module: subclass of nn.Module
    name: name of parameters to be pruned
    id: id for the parameters in the parameters_tobe_pruned list
    """
    sub_module = getattr(module, name)
    shape = sub_module.size()
    if mask is not None and isinstance(mask, (torch.Tensor, torch.nn.Parameter)):
        assert shape == mask.size(
        ), "size of mask and parameters not consistent: {} != {}".format(mask.size(), shape)
    FoobarPruning.apply(module, name, pregenerated_mask=mask)
    return module


def remove_prune_reparametrization(module, name):
    """
    make pruning permanent
    """
    prune.remove(module, name)


def restore_init_state(model: torch.nn.Module, init_state):
    """
    load copyed initial state dict after prune.remove
    """
    model.load_state_dict(init_state)


def freeze_parameters(model):
    """
    freeze all parameters of input model
    """
    for p in model.parameters():
        p.requires_grad = False


def bernoulli_hard_sampler(probs, require_logprob: bool = True):
    """
    Hard sampler for bernoulli distribution
    """
    Bernoulli_Sampler = Bernoulli(probs=probs)
    sample = Bernoulli_Sampler.sample()
    if require_logprob:
        log_probs_of_sample = Bernoulli_Sampler.log_prob(sample)
        return sample, log_probs_of_sample
    return sample


def bernoulli_soft_sampler(logits, temperature: float = 0.1):
    """
    Soft sampler for bernoulli distribution
    """
    device = logits.device
    uniform_variables = torch.rand(*logits.size()).to(device)
    assert uniform_variables.shape == logits.shape
    samples = torch.sigmoid(
        (logits + torch.log(uniform_variables) - torch.log(1-uniform_variables)) / temperature)
    return samples


def LAMA(model, tokenizer, device, input_w_mask, topk=5):
    # model.eval()
    if '[MASK]' != tokenizer.mask_token:
        input_w_mask = input_w_mask.replace('[MASK]', tokenizer.mask_token)
    inputs = tokenizer(input_w_mask, return_tensors='pt')
    mask_id = inputs['input_ids'][0].tolist().index(tokenizer.mask_token_id)
    inputs.to(device)
    outputs = model(**inputs)
    logits = outputs.logits
    probs = torch.softmax(logits[0, mask_id], dim=-1)
    _, indices = torch.topk(probs, k=topk)
    predictions = []
    for token in tokenizer.decode(indices).strip().split(" "):
        predictions.append(token.lower())
    return predictions


def save_pruning_masks_generators(args, model_name: str, pruning_masks_generators: List[List], id_to_relation: Dict, save_dir: str):
    """
    Save pruning mask generators specified with model name, relation type and number of transformer blocks of interest.
    """
    if "/" in model_name:
        model_name = model_name.split("/")[-1]
    for i in range(len(id_to_relation)):
        relation_str = id_to_relation[i]
        type = "soft" if args.soft_infer and args.soft_train else "hard"
        file_prefix = "{}/{}_{}_{}_{}_{}_init>{}_{}.pickle".format(save_dir,
                                                                model_name, relation_str, len(pruning_masks_generators[i]), args.bottom_layer_index, args.top_layer_index, args.init_method, type)
        with open(file_prefix, mode='wb') as f:
            torch.save(pruning_masks_generators[i], f)
        print("Pruning mask generators for {} is saved at {}".format(
            relation_str, file_prefix))


def sparsity(model, init_method: str):
    # sparsity
    try:
        if init_method == 'ones':
            v = 1.0
        else:
            v = float(init_method)
    except Exception:
        return dict()
    threshold = torch.sigmoid(torch.tensor(v)).item()
    sparsities = dict()
    id_to_relation = model.id_to_relation
    for i in range(len(model.pruning_mask_generators)):
        total_cnt = 0
        cnt = 0
        pruning_masks = model.pruning_mask_generators[i]
        for p in pruning_masks:
            bernoulli_p = torch.sigmoid(p.data)
            bernoulli_p = bernoulli_p < threshold
            cnt = bernoulli_p.int().sum().item()
            total_cnt += p.nelement()
        sparsities[id_to_relation[i]] = cnt / total_cnt
    return sparsities

def relation_miner(context: str):
    """
    Return a set of possible commonsense relations given the context
    """
    token2rels = {
        'use': ['UsedFor'],
        'used': ['UsedFor'],
        'where': ['AtLocation'],
        'Where': ['AtLocation'],
        'cause': ['Causes'],
        'cause': ['Causes'],
        'desire': ['Desires'],
        'desires': ['Desires'],
        'in': ['AtLocation'],
        'happen': ['HasSubevent']
    }
    raise NotImplementedError


def test(argv):
    bert_name = argv[1]
    device = torch.device('cuda:{}'.format(argv[2]))
    # masks = torch.nn.Parameter(torch.empty(768, 768))
    # opt = torch.optim.Adam(masks, lr=3e-4)
    # opt.zero_grad()
    # torch.nn.init.zeros_(masks)
    # soft_samples = bernoulli_soft_sampler(masks, temperature=0.1)
    # assert soft_samples.requires_grad == True, "no grad associated with soft samples"

    # testing
    bert = AutoModelForMaskedLM.from_pretrained(
        bert_name, return_dict=True).to(device)
    bert.eval()
    freeze_parameters(bert)
    # init_state = copy.deepcopy(bert.state_dict())
    tokenizer = AutoTokenizer.from_pretrained(bert_name, use_fast=True)
    print(tokenizer.mask_token_id)
    parameters_tobe_pruned = []
    # for i in range(8, 12):
    #     parameters_tobe_pruned.append(
    #         (bert.bert.encoder.layer[i].attention.self.query, 'weight'))
    #     parameters_tobe_pruned.append(
    #         (bert.bert.encoder.layer[i].attention.self.key, 'weight'))
    #     parameters_tobe_pruned.append(
    #         (bert.bert.encoder.layer[i].attention.self.value, 'weight'))
    #     parameters_tobe_pruned.append(
    #         (bert.bert.encoder.layer[i].attention.output.dense, 'weight'))
    #     parameters_tobe_pruned.append(
    #         (bert.bert.encoder.layer[i].intermediate.dense, 'weight'))
    #     parameters_tobe_pruned.append(
    #         (bert.bert.encoder.layer[i].output.dense, 'weight'))
    # parameters_tobe_pruned = tuple(parameters_tobe_pruned)
    # # prune
    # for module, name in parameters_tobe_pruned:
    #     prune.random_unstructured(module, name, amount=0.30)
        # Foobar_pruning(module, name, soft_samples[0])
    # print(sparsity(bert))

    corpus_fileobj = open("./data/ConceptNet/test.jsonl",
                          mode='r', encoding='utf-8')
    total_loss = .0
    cnt = 0
    top1 = 0
    top2 = 0
    top3 = 0
    for instance in jsonlines.Reader(corpus_fileobj):
        cnt += 1
        text = instance['masked_sentences'][0].replace(
            '[MASK]', tokenizer.mask_token)
        obj_label = instance['obj_label'].lower()
        input_dict = tokenizer(text, return_tensors='pt').to(device)
        mask_index = input_dict['input_ids'][0].tolist().index(
            tokenizer.mask_token_id)
        labels = input_dict['input_ids'].clone().to(device)
        labels.fill_(-100)
        labels[0, mask_index] = tokenizer.convert_tokens_to_ids([obj_label])[0]
        outputs = bert(**input_dict, labels=labels)
        logits = outputs.logits
        loss = outputs.loss
        probs = torch.softmax(logits[0, mask_index], dim=-1)
        _, indices = torch.topk(probs, k=5)
        predictions = tokenizer.decode(indices).strip().split()
        try:
            if obj_label == predictions[0].lower():
                top1 += 1
            if obj_label in [predictions[0].lower(), predictions[1].lower()]:
                top2 += 1
            if obj_label in [predictions[0].lower(), predictions[1].lower(), predictions[2].lower()]:
                top3 += 1
        except Exception:
            pass
        # if loss.item() <= 2.2:
        #     print(text)
        #     print(obj_label)
        #     print(LAMA(bert, tokenizer, device, text))
        #     exit()
        # print(loss)
        total_loss += loss.detach().item()
        print(cnt)
        # print(LAMA(bert, tokenizer, torch.device('cpu'), text))
    p1 = top1 / cnt
    p2 = top2 / cnt
    p3 = top3 / cnt
    print(argv[1])
    print(total_loss / cnt)
    print('P@1:', p1)
    print('P@2:', p2)
    print('P@3:', p3)


if __name__ == "__main__":
    argv = sys.argv
    test(argv)
    # for module, name in parameters_tobe_pruned:
    #     remove_prune_reparametrization(module, name)
