'''
Author: roy
Date: 2020-11-01 11:16:54
LastEditTime: 2020-11-01 21:26:03
LastEditors: Please set LastEditors
Description: In User Settings Edit
FilePath: /LAMA/config.py
'''
import argparse
import logging
from pytorch_lightning import Trainer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s %(message)s', datefmt='%a, %d %b %Y %H:%M:%S')
logger = logging.getLogger(__name__)

conceptNet_path = "./data/ConceptNet/test.jsonl"
place_of_birth_path = "./data/Google_RE/place_of_birth_test.jsonl"
place_of_death_path = "./data/Google_RE/place_of_death_test.jsonl"


def get_args():
    parser = argparse.ArgumentParser(
        "Probing knwoledge in pretrained language model using self-masking")
    parser = Trainer.add_argparse_args(parser)
    parser.add_argument('--model_name', type=str, default='bert-base-uncased',
                        help="name of pretrained language model")
    parser.add_argument('--max_length', type=int, default=20,
                        help="max length of input cloze question")
    parser.add_argument('--lr', type=float, default=2e-4, help="learning rate")
    args = parser.parse_args()
    return args
