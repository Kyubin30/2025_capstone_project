import json
import re
from typing import List, Dict, Any, Tuple
from collections import Counter
import logging

logger = logging.getLogger(__name__)


class CompanyAnalyzer:
    def __init__(self, companies_file_path: str = './companies.json'):
        """
        회사 데이터를 로드하고 분석기를 초기화합니다.
        
        Args:
            companies_file_path (str): 회사 데이터 JSON 파일 경로
        """
        self.companies_data = self._load_companies_data(companies_file_path)
        self.industries = self.companies_data.get('industries', [])
        self.companies = self.companies_data.get('companies', [])
        
        # 산업 ID -> 산업명 매핑
        self.industry_id_to_name = {
            industry['industry_id']: industry['industry_name'] 
            for industry in self.industries
        }
        
        # 산업명 리스트
        self.industry_names = [industry['industry_name'] for industry in self.industries]
        
        # 영향도 분석을 위한 키워드 사전
        self.positive_keywords = [
            '성장', '발전', '증가', '성공', '획득', '계약', '투자', '혁신', '개발', '출시',
            '향상', '확장', '진출', '협력', '제휴', '상승', '도약', '발표', '론칭', '개선'
        ]
        
        self.negative_keywords = [
            '감소', '하락', '손실', '문제', '논란', '중단', '지연', '실패', '취소', '위험',
            '우려', '부족', '어려움', '갈등', '규제', '제재', '침체', '타격', '위기', '폐쇄'
        ]
        
        logger.info(f"회사 데이터 로딩 완료: {len(self.companies)}개 회사, {len(self.industries)}개 산업")
    
    def _load_companies_data(self, file_path: str) -> Dict[str, Any]:
        """
        JSON 파일에서 회사 및 산업 데이터를 로드합니다.
        
        Args:
            file_path (str): JSON 파일 경로
            
        Returns:
            Dict[str, Any]: 회사 및 산업 데이터
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"회사 데이터 로딩 실패: {e}")
            return {"industries": [], "companies": []}
    
    def _analyze_impact_direction(self, text: str) -> Tuple[str, float]:
        """
        뉴스 텍스트에서 긍정/부정 영향 방향과 강도를 분석합니다.
        
        Args:
            text (str): 분석할 뉴스 텍스트
            
        Returns:
            Tuple[str, float]: (영향 방향, 영향 강도)
        """
        text_lower = text.lower()
        
        positive_count = sum(1 for keyword in self.positive_keywords if keyword in text_lower)
        negative_count = sum(1 for keyword in self.negative_keywords if keyword in text_lower)
        
        # 영향 방향 결정
        if positive_count > negative_count:
            direction = "positive"
            intensity = min(positive_count / 3.0, 1.0)  # 최대 3개 키워드로 정규화
        elif negative_count > positive_count:
            direction = "negative"
            intensity = min(negative_count / 3.0, 1.0)
        else:
            direction = "neutral"
            intensity = 0.5
        
        return direction, intensity
    
    def analyze_industry_impact(self, text: str, target_industry: str) -> Dict[str, Any]:
        """
        뉴스가 특정 산업에 미치는 영향을 간단히 분석합니다.
        
        Args:
            text (str): 분석할 뉴스 텍스트
            target_industry (str): 대상 산업명
            
        Returns:
            Dict[str, Any]: 산업 영향 분석 결과
        """
        # 영향 방향과 강도 분석
        impact_direction, impact_intensity = self._analyze_impact_direction(text)
        
        industry_impact = {
            "industry_name": target_industry,
            "impact_direction": impact_direction,
            "impact_score": round(impact_intensity, 3)
        }
        
        logger.info(f"산업 영향도 분석 완료: {target_industry} - {impact_direction} ({impact_intensity:.3f})")
        return industry_impact
    
    def get_random_company_by_industry(self, industry_name: str = None) -> Dict[str, Any]:
        """
        특정 산업 또는 랜덤 산업에서 회사를 선택합니다.
        
        Args:
            industry_name (str): 특정 산업명 (None이면 랜덤 선택)
            
        Returns:
            Dict[str, Any]: 선택된 회사 정보 (industry_name 추가)
        """
        import random
        
        if industry_name:
            # 산업명으로 industry_id 찾기
            industry_id = None
            for industry in self.industries:
                if industry['industry_name'] == industry_name:
                    industry_id = industry['industry_id']
                    break
            
            if industry_id:
                # 특정 산업의 회사들 필터링
                industry_companies = [c for c in self.companies if c['industry_id'] == industry_id]
                if industry_companies:
                    selected_company = random.choice(industry_companies)
                else:
                    selected_company = random.choice(self.companies)
            else:
                selected_company = random.choice(self.companies)
        else:
            # 전체에서 랜덤 선택
            selected_company = random.choice(self.companies)
        
        # 산업명 추가
        selected_company['industry_name'] = self.industry_id_to_name.get(
            selected_company['industry_id'], ''
        )
        
        return selected_company