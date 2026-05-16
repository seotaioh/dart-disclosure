"""
DART 기업공시정보 조회 API (Vercel Serverless 배포용)

- /api/search?q=...
- /api/company/{corp_code}
- /api/disclosures/{corp_code}
- /api/financials/{corp_code}?year=...
- /api/shareholders/{corp_code}?year=...
- /api/executives/{corp_code}?year=...

정적 HTML은 /public/index.html (Vercel이 자동 서빙)
환경변수: DART_API_KEY (Vercel 대시보드에서 설정)
"""

import os
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

DART_API_KEY = os.getenv("DART_API_KEY", "")
DART_BASE_URL = "https://opendart.fss.or.kr/api"

app = FastAPI(title="DART 기업공시정보 조회 API")

# 기업 고유번호 캐시 (서버리스 인스턴스 내에서만 유지)
_corp_code_cache: dict[str, dict] = {}
_cache_loaded = False


async def load_corp_codes() -> dict[str, dict]:
    global _corp_code_cache, _cache_loaded
    if _cache_loaded:
        return _corp_code_cache
    if not DART_API_KEY:
        raise HTTPException(500, "DART_API_KEY 환경변수가 설정되지 않았습니다.")
    url = f"{DART_BASE_URL}/corpCode.xml"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, params={"crtfc_key": DART_API_KEY})
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            with zf.open("CORPCODE.xml") as xml_file:
                tree = ET.parse(xml_file)
                for item in tree.getroot().findall("list"):
                    name = (item.findtext("corp_name") or "").strip()
                    if not name:
                        continue
                    _corp_code_cache[name] = {
                        "corp_code": (item.findtext("corp_code") or "").strip(),
                        "corp_name": name,
                        "stock_code": (item.findtext("stock_code") or "").strip(),
                        "modify_date": (item.findtext("modify_date") or "").strip(),
                    }
    _cache_loaded = True
    return _corp_code_cache


def search_corp(keyword: str, limit: int = 20) -> list[dict]:
    keyword = keyword.strip()
    if not keyword:
        return []
    results: list[dict] = []
    seen: set[str] = set()

    def add(info):
        if info["corp_code"] not in seen:
            seen.add(info["corp_code"])
            results.append(info)

    if keyword in _corp_code_cache:
        add(_corp_code_cache[keyword])
    for name, info in _corp_code_cache.items():
        if name.startswith(keyword):
            add(info)
        if len(results) >= limit:
            break
    if len(results) < limit:
        for name, info in _corp_code_cache.items():
            if keyword in name:
                add(info)
            if len(results) >= limit:
                break
    results.sort(key=lambda x: (not bool(x.get("stock_code")), x["corp_name"]))
    return results[:limit]


async def fetch_json(path: str, params: dict) -> dict:
    if not DART_API_KEY:
        raise HTTPException(500, "DART_API_KEY 환경변수가 설정되지 않았습니다.")
    params = {"crtfc_key": DART_API_KEY, **params}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{DART_BASE_URL}/{path}", params=params)
        return r.json()


@app.get("/api/health")
async def health():
    return {"ok": True, "has_key": bool(DART_API_KEY)}


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), limit: int = 20):
    await load_corp_codes()
    return {"results": search_corp(q, limit=limit)}


@app.get("/api/company/{corp_code}")
async def api_company(corp_code: str):
    data = await fetch_json("company.json", {"corp_code": corp_code})
    if data.get("status") != "000":
        return JSONResponse({"error": data.get("message", "조회 실패")}, status_code=400)
    return data


@app.get("/api/disclosures/{corp_code}")
async def api_disclosures(
    corp_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    disclosure_type: Optional[str] = None,
    page_count: int = 20,
):
    if not end_date:
        end_date = datetime.now().strftime("%Y%m%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    params = {
        "corp_code": corp_code,
        "bgn_de": start_date,
        "end_de": end_date,
        "page_count": min(page_count, 100),
    }
    if disclosure_type:
        params["pblntf_ty"] = disclosure_type
    data = await fetch_json("list.json", params)
    if data.get("status") not in ("000", "013"):
        return JSONResponse({"error": data.get("message", "조회 실패")}, status_code=400)
    return data


@app.get("/api/financials/{corp_code}")
async def api_financials(
    corp_code: str,
    year: int,
    report_type: str = "11011",
    fs_type: str = "OFS",
):
    data = await fetch_json(
        "fnlttSinglAcntAll.json",
        {
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": report_type,
            "fs_div": fs_type,
        },
    )
    if data.get("status") != "000":
        return JSONResponse({"error": data.get("message", "조회 실패")}, status_code=400)
    return data


@app.get("/api/shareholders/{corp_code}")
async def api_shareholders(corp_code: str, year: int, report_type: str = "11011"):
    data = await fetch_json(
        "hyslrSttus.json",
        {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": report_type},
    )
    if data.get("status") != "000":
        return JSONResponse({"error": data.get("message", "조회 실패")}, status_code=400)
    return data


@app.get("/api/executives/{corp_code}")
async def api_executives(corp_code: str, year: int, report_type: str = "11011"):
    data = await fetch_json(
        "exctvSttus.json",
        {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": report_type},
    )
    if data.get("status") != "000":
        return JSONResponse({"error": data.get("message", "조회 실패")}, status_code=400)
    return data
