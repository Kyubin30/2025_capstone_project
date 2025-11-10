#!/usr/bin/env python3
import argparse, json, logging, time
from typing import Optional, Dict, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pymongo import MongoClient

import config
from sentiment_analyzer import SentimentAnalyzer
from company_analyzer import CompanyAnalyzer

logger = logging.getLogger("generate_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class NewsGenerator:
    def __init__(self):
        self.bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=config.AWS_REGION_NAME,
            aws_access_key_id=getattr(config, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(config, "AWS_SECRET_ACCESS_KEY", None),
            config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2, "mode": "standard"})
        )
        self.mongo = MongoClient(config.MONGO_DB_URI)
        db = self.mongo[config.MONGO_DB_NAME]
        self.collection = db[config.MONGO_COLLECTION_NAME]

        self.sentiment_analyzer = SentimentAnalyzer()
        self.company_analyzer = CompanyAnalyzer()
        logger.info("NewsGenerator 초기화 완료")

    def _invoke_bedrock(self, user_prompt: str) -> Optional[str]:
        """Bedrock 호출 및 응답 파싱"""
        delay = getattr(config, "FIXED_CALL_DELAY", 10)
        if delay > 0:
            time.sleep(delay)

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        try:
            resp = self.bedrock_client.invoke_model(
                body=json.dumps(payload),
                modelId=config.BEDROCK_MODEL_ID,
                accept="application/json",
                contentType="application/json",
            )
            body = json.loads(resp.get("body").read())
            return body["content"][0]["text"].strip()
        except ClientError as e:
            logger.error(f"Bedrock 실패: {e}")
            return None
        except Exception as e:
            logger.error(f"예외: {e}")
            return None

    def _parse_json_response(self, response: str) -> Optional[Dict[str, str]]:
        """응답에서 JSON 추출 및 파싱"""
        if not response:
            return None
        try:
            # 공백 및 개행 정리
            response = response.strip()
            
            # JSON 블록 추출 (```json ... ``` 형식 제거)
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            # { 부터 } 까지만 추출 (불완전한 응답 처리)
            if "{" in response and "}" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                response = response[start:end]
            
            data = json.loads(response)
            if "title" in data and "body" in data:
                title = str(data["title"]).strip()
                body = str(data["body"]).strip()
                if title and body:
                    return {
                        "title": title,
                        "body": body
                    }
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON 파싱 실패: {response[:150]}")
        return None

    def generate_news_with_bedrock(self, industry: str, company_info: Dict[str, Any], 
                                   global_event: str = None, sentiment: str = None) -> Optional[Dict[str, str]]:
        """Bedrock에서 제목과 본문 직접 생성"""
        if global_event:
            prompt = config.get_global_event_prompt(global_event)
            user_prompt = prompt
        else:
            prompt = config.get_company_news_prompt()
            user_prompt = prompt.format(
                industry=industry,
                company_name=company_info["name"],
                sentiment=sentiment or "neutral"
            )
        
        response = self._invoke_bedrock(user_prompt)
        if not response:
            logger.error("Bedrock 응답 없음")
            return None
        
        result = self._parse_json_response(response)
        if result:
            logger.info(f"생성 성공 - 제목: {result['title'][:50]}...")
        else:
            logger.error(f"JSON 파싱 실패 - 응답: {response[:150]}")
        return result

    def _norm(label: str) -> str:
        """감정 라벨 정규화"""
        if not label:
            return "neutral"
        l = label.lower().strip()
        if l.startswith(("pos", "긍")):
            return "positive"
        if l.startswith(("neg", "부")):
            return "negative"
        if "neutral" in l or "중립" in l:
            return "neutral"
        return "neutral"

    def save_to_mongodb(self, doc: Dict[str, Any]) -> bool:
        """MongoDB에 저장"""
        try:
            result = self.collection.insert_one(doc)
            logger.info(f"[MongoDB] 저장 완료 _id={result.inserted_id}")
            return True
        except Exception as e:
            logger.error(f"[MongoDB] 저장 실패: {e}")
            return False

    def close(self):
        """리소스 정리"""
        try:
            self.mongo.close()
        except Exception:
            pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--industry", type=str, default=None)
    args = ap.parse_args()

    gen = None
    try:
        gen = NewsGenerator()
        # 여기서 bulk_generate와 함께 사용하면 됩니다
        logger.info(f"NewsGenerator 준비 완료. bulk_generate.py를 사용하세요.")
    finally:
        if gen:
            gen.close()

if __name__ == "__main__":
    main()