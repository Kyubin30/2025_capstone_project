#!/usr/bin/env python3
# 실패 시 10초 대기 후 동일 감정 재시도. 목표 개수 보장.

import argparse, json, os, random, time
from datetime import datetime
from typing import Dict, Any, List

import config
from generate_data import NewsGenerator

def _log(msg: str):
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}")

def norm(label: str) -> str:
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

def round_robin(items: List[Any]):
    i, n = 0, len(items)
    while True:
        yield items[i % n]
        i += 1

def load_companies_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    industries = data.get("industries", [])
    companies = data.get("companies", data if isinstance(data, list) else [])
    id2name = {i.get("industry_id"): i.get("industry_name") for i in industries if "industry_id" in i}
    for c in companies:
        if "industry_name" not in c:
            c["industry_name"] = id2name.get(c.get("industry_id"), c.get("industry", ""))
    return {"industries": industries, "companies": companies}

def try_generate_company_once(gen: NewsGenerator, company: Dict[str, Any], origin_sentiment: str) -> bool:
    """한 번 시도. 저장 성공 시 True."""
    industry = company.get("industry_name") or ""
    _log(f"[회사뉴스] {company['name']} / origin={origin_sentiment}")
    
    # Bedrock에서 제목과 본문 직접 생성 (sentiment 전달)
    news = gen.generate_news_with_bedrock(industry, company, sentiment=origin_sentiment)
    if not news:
        _log("[회사뉴스] 뉴스 생성 실패")
        return False
    
    title = news.get("title", "").strip()
    content = news.get("body", "").strip()
    
    if not title or not content:
        _log("[회사뉴스] 제목 또는 본문이 비어있음")
        return False
    
    # 감정 분석 - sentiment_analyzer 연결
    try:
        anal = gen.sentiment_analyzer.predict(content)
        _log(f"[회사뉴스] 감정분석 완료: {anal}")
    except Exception as e:
        _log(f"[회사뉴스] 감정분석 실패: {e} -> neutral로 처리")
        anal = "neutral"
    
    # 산업 영향 분석
    try:
        impact = gen.company_analyzer.analyze_industry_impact(content, industry)
    except Exception as e:
        _log(f"[회사뉴스] 산업영향분석 실패: {e}")
        impact = {
            "industry_name": industry,
            "impact_direction": "neutral",
            "impact_score": 0.5
        }
    
    # MongoDB에 저장할 문서
    doc = {
        "industry_name": industry,
        "company_id": company["id"],
        "company_name": company["name"],
        "title": title,
        "content": content,
        "origin_sentiment": origin_sentiment,
        "anal_sentiment": anal,
        "industry_impact": impact
    }
    
    ok = gen.save_to_mongodb(doc)
    _log(f"[회사뉴스] 저장 {'성공' if ok else '실패'} origin={origin_sentiment} anal={anal}")
    return ok

def ensure_n_for_company(gen: NewsGenerator, company: Dict[str, Any], origin_sentiment: str, target: int):
    """해당 회사·감정에 대해 target개가 저장될 때까지 반복. 실패 시 10초 대기."""
    made = 0
    wait_on_fail = getattr(config, "RETRY_WAIT_ON_FAIL", 10)
    while made < target:
        if try_generate_company_once(gen, company, origin_sentiment):
            made += 1
            _log(f"[회사뉴스] 누적 {made}/{target} ({company['name']} / {origin_sentiment})")
        else:
            _log(f"[회사뉴스] 실패 → {wait_on_fail}s 대기 후 재시도")
            time.sleep(max(0, wait_on_fail))

def try_generate_global_once(gen: NewsGenerator, event_name: str) -> bool:
    """글로벌 이벤트 뉴스 생성 시도"""
    _log(f"[글로벌] 이벤트={event_name}")
    
    # Bedrock에서 제목과 본문 직접 생성
    news = gen.generate_news_with_bedrock("전체", {"id": "GLOBAL", "name": "전체 시장"}, global_event=event_name)
    if not news:
        _log("[글로벌] 뉴스 생성 실패")
        return False
    
    title = news.get("title", "").strip()
    content = news.get("body", "").strip()
    
    if not title or not content:
        _log("[글로벌] 제목 또는 본문이 비어있음")
        return False
    
    # 감정 분석 - sentiment_analyzer 연결
    try:
        anal = gen.sentiment_analyzer.predict(content)
        _log(f"[글로벌] 감정분석 완료: {anal}")
    except Exception as e:
        _log(f"[글로벌] 감정분석 실패: {e} -> neutral로 처리")
        anal = "neutral"
    
    # 산업 영향 분석
    try:
        impact = gen.company_analyzer.analyze_industry_impact(content, "전체")
    except Exception as e:
        _log(f"[글로벌] 산업영향분석 실패: {e}")
        impact = {
            "industry_name": "전체",
            "impact_direction": "neutral",
            "impact_score": 0.5
        }
    
    # MongoDB에 저장할 문서
    doc = {
        "industry_name": "전체",
        "company_id": "GLOBAL",
        "company_name": "전체 시장",
        "title": title,
        "content": content,
        "origin_sentiment": None,
        "anal_sentiment": anal,
        "industry_impact": impact
    }
    
    ok = gen.save_to_mongodb(doc)
    _log(f"[글로벌] 저장 {'성공' if ok else '실패'} anal={anal}")
    return ok

def run_company_counts(gen: NewsGenerator, companies: List[Dict[str, Any]], pos: int, neg: int, neu: int, shuffle: bool):
    """각 회사별로 감정별 개수만큼 생성"""
    if shuffle:
        random.shuffle(companies)
    plan = [("positive", pos), ("negative", neg), ("neutral", neu)]
    for c in companies:
        for origin, cnt in plan:
            if cnt > 0:
                _log(f"[회사별 계획] {c['name']} / {origin} x {cnt}")
                ensure_n_for_company(gen, c, origin, cnt)

def run_global_even(gen: NewsGenerator, total_global: int):
    """글로벌 이벤트를 round-robin으로 생성"""
    names = [name for name, _ in config.GLOBAL_EVENTS]
    rr = round_robin(names)
    made = 0
    wait_on_fail = getattr(config, "RETRY_WAIT_ON_FAIL", 10)
    while made < total_global:
        if try_generate_global_once(gen, next(rr)):
            made += 1
            _log(f"[글로벌] 누적 {made}/{total_global}")
        else:
            _log(f"[글로벌] 실패 → {wait_on_fail}s 대기 후 재시도")
            time.sleep(max(0, wait_on_fail))

def main():
    ap = argparse.ArgumentParser(description="감정별 정확 개수 보장 생성기")
    ap.add_argument("--pos", type=int, default=0)
    ap.add_argument("--neg", type=int, default=0)
    ap.add_argument("--neu", type=int, default=0)
    ap.add_argument("--global", dest="global_count", type=int, default=0)
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--limit-companies", type=int, default=0)
    ap.add_argument("--companies-path", type=str, default="./companies.json")
    args = ap.parse_args()

    gen = NewsGenerator()
    data = load_companies_json(args.companies_path)
    companies = data.get("companies", [])
    if args.limit_companies > 0:
        companies = companies[:args.limit_companies]

    _log("=" * 58)
    _log(f"대상 {len(companies)} | per-company pos {args.pos} neg {args.neg} neu {args.neu} | 글로벌 {args.global_count}")
    _log(f"호출전대기={getattr(config, 'FIXED_CALL_DELAY', 10)}s, 실패후대기={getattr(config, 'RETRY_WAIT_ON_FAIL', 10)}s")
    _log("=" * 58)

    if companies and (args.pos or args.neg or args.neu):
        run_company_counts(gen, companies, args.pos, args.neg, args.neu, args.shuffle)

    if args.global_count > 0:
        run_global_even(gen, args.global_count)

    gen.close()
    _log("완료.")

if __name__ == "__main__":
    main()