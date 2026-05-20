"""
boilerplate_filter
==================
判斷一段文字是否為法律免責聲明、版權聲明、聯絡資訊或其他樣板內容。
這類內容對於投資觀點判斷沒有意義，必須在計分前過濾掉，
否則會讓「沒有訊號」被誤判為「中性 50 分」，把整體分數往中間拉。

使用方式：
    from boilerplate_filter import is_boilerplate, filter_boilerplate_chunks

    # 單段判斷
    if is_boilerplate(chunk_text):
        skip_this_chunk()

    # 整批過濾
    clean_chunks = filter_boilerplate_chunks(chunks, threshold=0.30)
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


# ──────────────────────────────────────────────────────────
#  樣板片語：免責聲明 / 版權 / 法律保留 / 內部聯絡資訊
#  繁簡體均列入；命中即累計樣板分數
# ──────────────────────────────────────────────────────────
BOILERPLATE_PHRASES: List[str] = [
    # ── 中文：免責 / 版權 ──
    "免責聲明", "免责声明",
    "版權所有", "版权所有",
    "保留所有權利", "保留所有权利",
    "保留一切權利", "保留一切权利",
    # ── 中文：不構成投資建議 ──
    "不構成投資建議", "不构成投资建议",
    "並不構成", "并不构成",
    "本報告之內容並不構成", "本报告之内容并不构成",
    "不構成任何要約", "不构成任何要约",
    "本文僅供", "本文仅供",
    "僅供參考", "仅供参考",
    "本文之內容", "本文之内容",
    # ── 中文：概不負責 / 免責語 ──
    "概不負上", "概不负上",
    "概不負責", "概不负责",
    "不承擔任何責任", "不承担任何责任",
    "不對其準確性", "不对其准确性",
    "不對該等", "不对该等",
    "不作任何陳述或保證", "不作任何陈述或保证",
    "完整性或準確性", "完整性或准确性",
    "完整性或正確性", "完整性或正确性",
    "完整性、準確性", "完整性、准确性",
    # ── 中文：授權 / 轉載 ──
    "未經本公司書面同意", "未经本公司书面同意",
    "未經書面同意", "未经书面同意",
    "未經我們事先書面同意", "未经我们事先书面同意",
    "請勿轉載", "请勿转载",
    "不得複製", "不得复制",
    "不得再次派發", "不得再次派发",
    # ── 中文：投資人風險警示 ──
    "投資涉及風險", "投资涉及风险",
    "投資有風險", "投资有风险",
    "並不適合所有投資者", "并不适合所有投资者",
    "請審慎注意", "请审慎注意",
    "請諮詢", "请咨询",
    "請聯絡您的", "请联系您的",
    "獨立調查", "独立调查",
    # ── 中文：公司章 / 聯絡資訊 ──
    "電話[:：]", "电话[:：]",
    "傳真[:：]", "传真[:：]",
    "地址[:：]",
    "註冊地址", "注册地址",
    # ── 中文：監管 / 法規 ──
    "監管機構", "监管机构",
    "本研究報告由", "本研究报告由",
    "本研究報告所載", "本研究报告所载",

    # ── 英文：版權 / 免責 ──
    "Copyright", "All Rights Reserved", "All rights reserved",
    "Disclaimer", "Important Disclosures", "Important disclosures",
    "Disclosure", "Disclosures",
    "Analyst Certification", "analyst certification",
    "FINRA", "SIPC", "MiFID",
    # ── 英文：不構成投資建議 ──
    "for informational purposes only",
    "for information purposes only",
    "solely for informational",
    "not intended as investment advice",
    "not constitute investment advice",
    "does not constitute an offer",
    "should not be construed as",
    "not an offer to buy or sell",
    "not a solicitation",
    # ── 英文：免責 / 不保證 ──
    "no representation or warranty",
    "no representations or warranties",
    "accuracy or completeness",
    "accuracy and completeness",
    "past performance is not",
    "past performance does not",
    "subject to change without notice",
    "we accept no liability",
    "without any liability",
    "shall not be liable",
    # ── 英文：轉載 / 授權 ──
    "without prior written consent",
    "without the prior written permission",
    "may not be reproduced",
    "may not be distributed",
    "unauthorized reproduction",
    # ── 英文：目標讀者 ──
    "for institutional investors only",
    "qualified institutional buyers",
    "qualified investors only",
    "professional clients only",
    "accredited investors",
    # ── 英文：公司 / 監管 ──
    "this report has been prepared by",
    "this document has been prepared by",
    "this material has been prepared",
    "registered investment adviser",
    "member of",
    "regulated by",
    "authorized and regulated",

    # ── 日文：版權 / 免責 ──
    "免責事項",
    "著作権",
    "無断転載禁止",
    "無断複製・転載を禁じます",
    "無断で複製",
    "無断転用を禁じます",
    # ── 日文：不構成投資建議 ──
    "情報提供のみを目的",
    "投資勧誘を目的とするものではありません",
    "投資勧誘を意図するものではありません",
    "投資判断はご自身でお願いします",
    "投資判断はお客様ご自身で",
    "特定の有価証券への投資を推奨するものではありません",
    # ── 日文：免責 / 不保證 ──
    "当社は一切責任を負いません",
    "いかなる責任も負いかねます",
    "正確性・完全性を保証するものではありません",
    "情報の正確性",
    "内容の正確性",
    "損害について責任を負いません",
    # ── 日文：轉載 / 授權 ──
    "事前の書面による承諾なく",
    "弊社の事前の許可なく",
    # ── 日文：目標讀者 / 監管 ──
    "機関投資家向け",
    "金融商品取引法",
    "金融商品取引業者",
    "日本証券業協会",
    "投資信託協会",
    "日本投資顧問業協会",
    "本レポートは",
    "本資料は",
    "当レポートは",
    "当資料は",
    "弊社調査部",
    # ── 日文：聯絡資訊 ──
    "お問い合わせ",
    "お問い合わせ先",
    "連絡先",
    "所在地",
    "電話番号",
    "TEL[:：]",
    "FAX[:：]",
    "E-mail[:：]",
    "ご利用に際して",
    # ── 日文：真實樣板句（來自 Mizuho / MURC）──
    "取引の勧誘を目的としたものではありません",
    "その正確性、確実性を保証するものではありません",
    "当社はその正確性、完全性を保証するものではありません",
    "当社は一切の責任を負いません",
    "予告なしに変更されることもあります",
    "配信停止を希望する旨をお知らせ願います",
    "著作権法に基づき保護されています",
    "転載・複製する際は著作権者の許諾が必要",
    "ご自身の判断にてなされますようお願い申し上げます",

    # ── 韓文：版權 / 免責 ──
    "면책조항",
    "저작권",
    "무단전재",
    "무단복제를 금합니다",
    "무단 복제 및 배포를 금합니다",
    # ── 韓文：不構成投資建議 ──
    "정보 제공을 목적으로",
    "투자 권유를 목적으로 하지 않습니다",
    "투자 권유를 위한 것이 아닙니다",
    "투자판단은 고객 본인이",
    "특정 종목에 대한 매수·매도 추천이 아닙니다",
    # ── 韓文：免責 / 不保證 ──
    "당사는 어떠한 책임도 지지 않습니다",
    "정확성을 보장하지 않습니다",
    "완전성을 보증하지 않습니다",
    "손해에 대해 책임지지 않습니다",
    "내용의 정확성",
    # ── 韓文：轉載 / 授權 ──
    "사전 서면 동의 없이",
    "무단으로 복제하거나",
    # ── 韓文：監管 ──
    "자본시장법",
    "금융투자업규정",
    "금융감독원",
    "금융투자협회",
    "본 보고서는",
    "본 자료는",
    # ── 韓文：聯絡資訊 ──
    "문의사항",
    "연락처",
    "고객센터",

    # ── 越南文：版權 / 免責（KBSV 等）──
    "Tuyên bố miễn trách",        # 免責聲明
    "Miễn trách nhiệm",
    "Bản quyền",                  # 版權
    "Không được sao chép",        # 不得複製
    "không được tái bản",
    "chỉ mang tính chất tham khảo",  # 僅供參考
    "không phải là lời khuyên đầu tư",  # 非投資建議
    "không cấu thành khuyến nghị đầu tư",
    "Chúng tôi không chịu trách nhiệm",  # 不承擔責任
    "không đảm bảo tính chính xác",      # 不保證準確性
    "có thể thay đổi mà không cần thông báo",  # 可能不另行通知更改
    # ── 越南文：聯絡資訊 ──
    "Chuyên viên phân tích",      # 分析師
    "Để biết thêm thông tin",     # 更多資訊
    "liên hệ với chúng tôi",      # 聯絡我們
]


# ──────────────────────────────────────────────────────────
#  正則樣板：電話 / 傳真 / 地址章
# ──────────────────────────────────────────────────────────
BOILERPLATE_PATTERNS: List[re.Pattern] = [
    # 中文電話 / 傳真
    re.compile(r"電話\s*[:：]\s*\(?\d{2,4}\)?\s*\d{4,}"),
    re.compile(r"电话\s*[:：]\s*\(?\d{2,4}\)?\s*\d{4,}"),
    re.compile(r"傳真\s*[:：]\s*\(?\d{2,4}\)?\s*\d{4,}"),
    re.compile(r"传真\s*[:：]\s*\(?\d{2,4}\)?\s*\d{4,}"),
    re.compile(r"\(852\)\s*\d{4}"),      # 香港電話
    re.compile(r"\(\+?86[\)\-]\s*\d"),   # 中國電話
    re.compile(r"\d+\s*樓|\d+\s*楼"),
    re.compile(r"中環|中环|九龍|九龙"),
    # 英文電話 / 地址
    re.compile(r"Tel\.?\s*[:：]?\s*\+?\d[\d\s\-\(\)]{7,}"),
    re.compile(r"Fax\.?\s*[:：]?\s*\+?\d[\d\s\-\(\)]{7,}"),
    re.compile(r"\+1[\s\-]\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{4}"),  # 北美電話
    re.compile(r"\+44[\s\-]\(?\d{2,4}\)?[\s\-]\d{4,}"),          # 英國電話
    re.compile(r"\+65[\s\-]\d{4}[\s\-]?\d{4}"),                  # 新加坡電話
    # 日文電話 / 地址
    re.compile(r"TEL\s*[:：]?\s*\(?\d{2,4}\)?[\s\-]\d{4,}"),
    re.compile(r"FAX\s*[:：]?\s*\(?\d{2,4}\)?[\s\-]\d{4,}"),
    re.compile(r"\(\+?81[\)\-]\s*\d"),   # 日本電話 +81
    re.compile(r"〒\d{3}[-－]\d{4}"),    # 日本郵遞區號
    re.compile(r"\d+\s*[丁目番地号]"),   # 日本地址單位
    # 韓文電話 / 地址
    re.compile(r"\(\+?82[\)\-]\s*\d"),   # 韓國電話 +82
    re.compile(r"02[\s\-]\d{3,4}[\s\-]\d{4}"),  # 首爾電話
    re.compile(r"\d{5,6}[\s,，]\s*[가-힣]"),    # 韓國郵遞區號+地址
    # 通用：Email 地址
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    # 通用：TEL / FAX 後接號碼
    re.compile(r"TEL\s*[:：]\s*[\d\-\(\)\+\s]{7,}"),
    re.compile(r"FAX\s*[:：]\s*[\d\-\(\)\+\s]{7,}"),
    # 越南電話 +84
    re.compile(r"\(\+?84[\)\-]\s*\d"),
]


# ──────────────────────────────────────────────────────────
#  打分
# ──────────────────────────────────────────────────────────
def boilerplate_score(text: str) -> float:
    """回傳一段文字屬於樣板的程度（0~1）。

    判斷依據（合計後 clip 到 1.0）：
      - 樣板片語命中數：每命中一個 +0.12
      - 樣板片語的字元覆蓋率：覆蓋率 × 4.0
      - 樣板正則命中數：每命中一個 +0.08
      - 「本文 / 本報告 / 本公司」自我指涉密度（典型免責句式）

    經驗閾值：>= 0.30 即可視為樣板。
    """
    if not text:
        return 0.0
    raw = text.strip()
    if len(raw) < 30:
        return 0.0

    text_lower = raw.lower()
    n_chars = len(raw)

    # 1. 片語命中
    phrase_hits = 0
    covered_chars = 0
    for phrase in BOILERPLATE_PHRASES:
        # 已經是 regex 片段（含 [:：]）的就用 search，否則用 in
        if any(c in phrase for c in "[]"):
            try:
                m = re.search(phrase, raw)
            except re.error:
                continue
            if m:
                phrase_hits += 1
                covered_chars += len(m.group(0))
            continue

        p_lower = phrase.lower()
        count = text_lower.count(p_lower)
        if count > 0:
            phrase_hits += count
            covered_chars += len(phrase) * count

    # 2. 正則命中（email 依出現次數計，其餘每個 pattern 算 1）
    _email_re = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    email_count = len(_email_re.findall(raw))
    pattern_hits = sum(1 for p in BOILERPLATE_PATTERNS if p.search(raw))
    pattern_hits += max(email_count - 1, 0) * 2  # 多封 email 是聯絡清單的強烈訊號，額外加重

    # 3. 自我指涉密度（免責文常出現「本文 / 本報告 / 本公司」等）
    self_ref_hits = (
        text_lower.count("本文")
        + text_lower.count("本報告")
        + text_lower.count("本报告")
        + text_lower.count("本公司")
        + raw.count("本レポート")
        + raw.count("本資料")
        + raw.count("当レポート")
        + raw.count("当資料")
        + raw.count("본 보고서")
        + raw.count("본 자료")
        + text_lower.count("this report")
        + text_lower.count("this document")
        + text_lower.count("this material")
    )

    coverage_ratio = covered_chars / max(n_chars, 1)

    score = (
        phrase_hits * 0.12
        + coverage_ratio * 4.0
        + pattern_hits * 0.08
        + max(self_ref_hits - 2, 0) * 0.05  # 出現超過 2 次才算可疑
    )
    return min(score, 1.0)


def is_boilerplate(text: str, threshold: float = 0.30) -> bool:
    """判斷一段文字是否為樣板（免責聲明 / 版權 / 聯絡資訊 / 法律保留）。

    threshold 預設 0.30；提高會比較寬鬆（保留更多 chunk），降低則更嚴格。
    """
    return boilerplate_score(text) >= threshold


def filter_boilerplate_chunks(
    chunks: Iterable[Dict[str, Any]],
    threshold: float = 0.30,
    text_key: str = "text",
) -> List[Dict[str, Any]]:
    """過濾掉樣板 chunk，保留有實質內容者。

    chunks: 每筆要有 ``text`` 欄（或自訂 ``text_key``）。
    回傳新 list，保持原順序。
    """
    return [c for c in chunks if not is_boilerplate(c.get(text_key, ""), threshold)]


__all__ = [
    "BOILERPLATE_PHRASES",
    "BOILERPLATE_PATTERNS",
    "boilerplate_score",
    "is_boilerplate",
    "filter_boilerplate_chunks",
]
