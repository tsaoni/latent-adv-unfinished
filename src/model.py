from lib import *
from utils import *

import torch.nn as nn
from argparse import Namespace
from transformers import (
    AutoModel, 
    AutoModelForSequenceClassification, 
    AutoModelForQuestionAnswering, 
    AutoModelForPreTraining, 
    AutoModelForTokenClassification, 
    AutoModelWithLMHead, 
    AutoModelForSeq2SeqLM, 

)

MODEL_MODES = {
    "base": AutoModel,
    "sequence-classification": AutoModelForSequenceClassification,
    "question-answering": AutoModelForQuestionAnswering,
    "pretraining": AutoModelForPreTraining,
    "token-classification": AutoModelForTokenClassification,
    "language-modeling": AutoModelWithLMHead,
    "summarization": AutoModelForSeq2SeqLM,
    "translation": AutoModelForSeq2SeqLM,
}

class Attacker(nn.Module):
    def __init__(
        self, 
        config, 
        model_name_or_path=None, 
    ):
        super().__init__()
        self.config = Namespace(
            model_name_or_path=model_name_or_path, 
            length_penalty=0.1,
            num_beams=4, 
            eval_min_gen_length=6, 
            eval_max_gen_length=50, 
        )
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name_or_path, config=config)
      
    def forward(self, **batch):
        pad_token_id = self.model.config.pad_token_id
        decoder_start_token_id = self.model.config.decoder_start_token_id
        src_ids, src_mask = batch["input_ids"], batch["attention_mask"]

        if 'labels' in batch:
            tgt_ids = batch["labels"]
            if isinstance(self.model, T5ForConditionalGeneration):
                decoder_input_ids = self.model._shift_right(tgt_ids)
            else:
                decoder_input_ids = shift_tokens_right(tgt_ids, pad_token_id, \
                                        decoder_start_token_id=decoder_start_token_id)
        else:
            tgt_ids=None
            decoder_input_ids = None


        outputs = self.model(
            src_ids, 
            attention_mask=src_mask, 
            decoder_input_ids=decoder_input_ids, 
            use_cache=False,
            labels=tgt_ids, 
        )

        return outputs

    
    def generate(self, batch: dict, return_ids=True, tokenizer=None):
        #print('for decoding, eval_max_length={}, eval_min_length={}, eval_beams={}'\
        #    .format(self.args.eval_max_gen_length, self.args.eval_min_gen_length, self.args.eval_beams))
    
        seq2seq_model_type = (
            BartForConditionalGeneration, 
            GPT2LMHeadModel, 
        )
        if isinstance(self.model, GPT2LMHeadModel):
            # todo: set gpt parameters
            output_sequences = self.model.generate(
                input_ids=batch["input_ids"],
                emb_match=None,
                #control_code=control_code,
                max_length=self.config.eval_max_gen_length,
                temperature=1.0,
                top_p=0.8,
                eos_token_id=tokenizer.eos_token_id,
                num_beams=4,
                #repetition_penalty=args.repetition_penalty,
                #do_sample=True,
                num_return_sequences=4,
            )
        elif isinstance(self.model, BartForConditionalGeneration): 
            self.model.input_ids = batch["input_ids"]
            output_sequences = self.model.generate(
                batch["input_ids"],
                # past_key_values=None,
                attention_mask=batch["attention_mask"],
                use_cache=True,
                length_penalty=self.config.length_penalty,
                # use_prefix=True,
                decoder_start_token_id=self.model.config.decoder_start_token_id,
                #num_return_sequences=4,
                num_beams=4, #self.config.num_beams,
                #temperature=1.2, 
                #return_dict_in_generate=True,
                #output_scores=True,
                min_length=self.config.eval_min_gen_length,
                max_length=self.config.eval_max_gen_length,
            )
            if hasattr(self.model, 'batch_word_range'):
                self.batch_word_range = self.model.batch_word_range
        else: 
            assert isinstance(self.model, seq2seq_model_type)

        if return_ids:
            return output_sequences
        else:
            return self.ids_to_clean_text(output_sequences, tokenizer)

    def ids_to_clean_text(self, generated_ids: torch.Tensor, tokenizer):
        gen_text = tokenizer.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True
        )
        return lmap(str.strip, gen_text)
