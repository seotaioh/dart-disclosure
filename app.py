"""
DART 기업공시정보 조회 웹 앱
FastAPI 기반의 간단한 웹 인터페이스로 DART OpenAPI를 호출하여
기업검색 / 기업개황 / 공시목록 / 재무제표 / 최대주주 / 임원현황을 조회합니다.

실행:
    set DART_API_KEY=발급받은_API_KEY   (Windows)
    export DART_API_KEY=...              (Mac/Linux)
    uvicorn app:app --reload --port 8000

이후 브라우저에서 http://localhost:8000 접속
"""

import os
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

DART_API_KEY = os.getenv("DART_API_KEY", "")
DART_BASE_URL = "https://opendart.fss.or.kr/api"

app = FastAPI(title="DART 기업공시정보 조회")

# 기업 고유번호 캐시
_corp_code_cache: dict[str, dict] = {}
_cache_loaded = False


async def load_corp_codes() -> dict[str, dict]:
    """전체 기업 고유번호 목록을 다운로드하여 캐시"""
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

    def add(info: dict):
        key = info["corp_code"]
        if key not in seen:
            seen.add(key)
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


# ---------------------- API 엔드포인트 ----------------------

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


# ---------------------- 정적 페이지 ----------------------

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
