'''
Author: roy
Date: 2020-11-07 15:49:03
LastEditTime: 2020-11-16 20:04:58
LastEditors: Please set LastEditors
Description: In User Settings Edit
FilePath: /LAMA/GLUE/main.py
'''
from functools import reduce
import os
import sys
sys.path.append(os.getcwd())

from torch.nn.utils import prune
from GLUE.glue_datamodule import *
from GLUE.glue_model import *
# import logging
from typing import *


# logging.basicConfig(level=logging.INFO,
#                     format='%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s:  %(message)s', datefmt='%a, %d %b %Y %H:%M:%S')
# logger = logging.getLogger(__name__)


ConceptNetRelations = ['AtLocation', 'CapableOf', 'Causes', 'CausesDesire', 'Desires', 'HasA', 'HasPrerequisite', 'HasProperty', 'HasSubevent', 'IsA', 'MadeOf', 'MotivatedByGoal', 'NotDesires', 'PartOf', 'ReceivesAction', 'UsedFor']


def load_masks(model_name: str, bli: int, tli: int, relations: List, init_method: str):
    masks = []
    for relation in relations:
        mask_pth = "/home1/roy/commonsense/LAMA/masks/{}_{}_{}_{}_{}_init>{}.pickle".format(model_name, relation, (tli-bli+1)*6, bli, tli, init_method)
        with open(mask_pth, mode='rb') as f:
            mask = torch.load(f)
            masks.append(mask)
    return masks

def dissimilarity(mask1, mask2):
    assert len(mask1) == len(mask2)
    _mask1 = []
    _mask2 = []
    for mask in mask1:
        mask = torch.sigmoid(mask)
        mask[mask>0.5] = 1
        mask[mask<=0.5] = 0
        _mask1.append(mask)
    for mask in mask2:
        mask = torch.sigmoid(mask)
        mask[mask>0.5] = 1
        mask[mask<=0.5] = 0
        _mask2.append(mask)
    cnt = 0
    c = 0
    for i in range(len(_mask1)):
        fro_norm = torch.norm(_mask1[i]-_mask2[i])**2
        c += fro_norm.item()
        cnt += _mask1[i].nelement()
        if i % 5 == 0:
            print(c / cnt)
    print(c / cnt)


def union_masks(*masks):
    thresholded_masks = []
    for mask in masks:
        tmp = []
        assert isinstance(mask[0], torch.nn.Parameter)
        for matrix in mask:
            prob = torch.sigmoid(matrix.data)
            prob[prob > 0.5] = 1
            prob[prob <= 0.5] = 0
            prob = prob.bool()
            tmp.append(prob)
        thresholded_masks.append(tmp)
    final_masks = []
    for mask_for_all_relations in zip(*thresholded_masks):
        tmp_mask = reduce(lambda x, y: torch.logical_or(x, y), mask_for_all_relations)
        final_masks.append(tmp_mask)
    cnt = 0
    num_0_all = 0
    for mask in final_masks:
        num_0 = (mask.int()==0).sum().item()
        cnt += mask.nelement()
        num_0_all += num_0
    print(num_0_all)
    print(cnt)
    print(num_0_all / cnt)
    return final_masks


def apply_masks(pl_model: GLUETransformer, model_name, bli, tli, masks):
    backbone = pl_model.model
    model_type = model_name.split('-')[0]
    assert hasattr(backbone, model_type), f"LM does not have {model_type}"
    if 'roberta' in model_name:
        layers = backbone.roberta.encoder.layer
    elif 'distil' in model_name:
        layers = backbone.distilbert.transformer.layer
    else:
        layers = backbone.bert.encoder.layer

    # load pre-trained masks
    parameters_tobe_pruned = []
    for i in range(bli, tli+1):
        try:
            parameters_tobe_pruned.append(
                (layers[i].attention.self.query, 'weight'))
            parameters_tobe_pruned.append(
                (layers[i].attention.self.key, 'weight'))
            parameters_tobe_pruned.append(
                (layers[i].attention.self.value, 'weight'))
            parameters_tobe_pruned.append(
                (layers[i].attention.output.dense, 'weight'))
            parameters_tobe_pruned.append(
                (layers[i].intermediate.dense, 'weight'))
            parameters_tobe_pruned.append(
                (layers[i].output.dense, 'weight'))
        except Exception:
            parameters_tobe_pruned.append(
                (layers[i].attention.q_lin, 'weight')
            )
            parameters_tobe_pruned.append(
                (layers[i].attention.k_lin, 'weight')
            )
            parameters_tobe_pruned.append(
                (layers[i].attention.v_lin, 'weight')
            )
            parameters_tobe_pruned.append(
                (layers[i].attention.out_lin, 'weight')
            )
            parameters_tobe_pruned.append(
                (layers[i].ffn.lin1, 'weight')
            )
            parameters_tobe_pruned.append(
                (layers[i].ffn.lin2, 'weight')
            )
    assert len(masks) == len(
        parameters_tobe_pruned), f"{parameters_tobe_pruned} != {len(masks)}"
    for mask, (module, name) in zip(masks, parameters_tobe_pruned):
        prune.custom_from_mask(module, name, mask)
        prune.remove(module, name)
    print("Pre-computed mask applied to {}".format(model_name))


def parse_args():
    parser = ArgumentParser()
    parser = pl.Trainer.add_argparse_args(parser)
    parser = GLUEDataModule.add_argparse_args(parser)
    parser = GLUETransformer.add_model_specific_args(parser)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--apply_mask', default=False, action='store_true', help="whether to apply pre-computed mask")
    parser.add_argument('--bli', type=int, default=None)
    parser.add_argument('--tli', type=int, default=None)
    parser.add_argument('--relations', nargs='+', type=str)
    parser.add_argument('--init_method', type=str)
    return parser.parse_args()


def main(args):
    pl.seed_everything(args.seed)
    dm = GLUEDataModule.from_argparse_args(args)
    dm.prepare_data()
    dm.setup('fit')
    model = GLUETransformer(num_labels=dm.num_labels,
                            eval_splits=dm.eval_splits, **vars(args))
    trainer = pl.Trainer.from_argparse_args(args)
    return dm, model, trainer


if __name__ == "__main__":
    args = parse_args()
    print(vars(args))
    data_module, pl_model, trainer = main(args)
    # if args.apply_mask and args.bli is not None and args.tli is not None and args.init_method is not None:
    #     # load masks
    #     print("Loading pre-computed masks")
    #     rels = ['IsA', 'Causes']
    #     masks = load_masks(args.model_name_or_path, args.bli, args.tli, rels, args.init_method)
    #     # union masks
    #     print("Unifying masks")
    #     final_mask = union_masks(*masks)
    #     # apply 
    #     print("Applying final unioned mask")
    #     apply_masks(pl_model, args.model_name_or_path, args.bli, args. tli, final_mask)
    # print("Start training on GLUE")
    trainer.fit(pl_model, data_module)
