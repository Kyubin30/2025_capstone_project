import os
from typing import Literal
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import logging
import config

logger = logging.getLogger(__name__)
Label = Literal["positive", "negative", "neutral"]

class SentimentAnalyzer:
    def __init__(self):
        model_id = getattr(config, "SENTIMENT_MODEL_PATH", "./best_model")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_id)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_id)
            self.model.eval()
            self.labels = self._resolve_labels()
            self.ready = True
            logger.info(f"[SentimentAnalyzer] 모델 로드 성공: {model_id}")
        except Exception as e:
            # 원인 파악 도움용 명확한 메시지
            msg = (
                f"[SentimentAnalyzer] 모델 로드 실패: {e}\n"
                f"- 확인사항:\n"
                f"  1) config.SENTIMENT_MODEL_PATH='{model_id}' 가 올바른 로컬 경로 또는 허깅페이스 모델 ID인지\n"
                f"  2) 폴더에 tokenizer 파일(tokenizer.json 또는 vocab.txt 등)과 config.json/pytorch_model.bin 존재 여부\n"
                f"  3) protobuf, transformers, torch 버전 설치 여부\n"
            )
            logger.error(msg)
            raise RuntimeError(msg)

    def _resolve_labels(self):
        """모델의 id2label/label2id에서 라벨명 추정"""
        cfg = self.model.config
        if hasattr(cfg, "id2label") and cfg.id2label:
            id2label = {int(k): v.lower() for k, v in cfg.id2label.items()}
            return [id2label[i] for i in sorted(id2label.keys())]
        return ["negative", "neutral", "positive"]  # 일반적 3클래스 기본값

    def _normalize_label(self, label: str) -> Label:
        """라벨을 표준화된 감정값으로 변환"""
        if not label:
            return "neutral"
        
        label_lower = label.lower().strip()
        
        # 긍정
        if label_lower.startswith(("pos", "긍")):
            return "positive"
        
        # 부정
        if label_lower.startswith(("neg", "부")):
            return "negative"
        
        # 중립
        if "neutral" in label_lower or "중립" in label_lower:
            return "neutral"
        
        return "neutral"

    def predict(self, text: str) -> Label:
        """텍스트 감정 분석 (positive/negative/neutral)"""
        try:
            if not text or not isinstance(text, str):
                logger.warning(f"[SentimentAnalyzer] 유효하지 않은 입력: {text}")
                return "neutral"
            
            text = text.strip()
            if not text:
                return "neutral"
            
            with torch.no_grad():
                inputs = self.tokenizer(text, truncation=True, max_length=256, return_tensors="pt")
                logits = self.model(**inputs).logits
                pred_id = int(torch.argmax(logits, dim=-1).item())
                
                # 라벨 추출
                label = self.labels[pred_id] if pred_id < len(self.labels) else "neutral"
                
                # 라벨 정규화
                normalized = self._normalize_label(label)
                logger.debug(f"[SentimentAnalyzer] 분석 결과: {label} -> {normalized}")
                
                return normalized
        
        except Exception as e:
            logger.error(f"[SentimentAnalyzer] predict() 실패: {e}")
            return "neutral"