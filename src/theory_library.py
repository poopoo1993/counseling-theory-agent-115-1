"""十一個諮商學派及固定技巧資料庫。

畫面與提示詞都只從本檔載入，避免模型臨時發明技巧名稱。
"""

from __future__ import annotations

from typing import Any


def _t(tech_id: str, name: str, short: str, affordance: str) -> dict[str, str]:
    return {"id": tech_id, "name": name, "short": short, "affordance": affordance}


SCHOOLS: dict[str, dict[str, Any]] = {
    "psychodynamic": {
        "name": "精神分析／心理動力",
        "core": "理解無意識衝突、防衛、早期關係與當下關係中反覆出現的模式。",
        "techniques": [
            _t("free_association", "自由聯想邀請", "邀請不加修飾地說出浮現的想法與感受。", "可由片段記憶、夢、矛盾感受或突然轉換話題延伸。"),
            _t("resistance_exploration", "探索抗拒", "好奇地探索沉默、迴避或改變話題的功能。", "在接近重要情緒時出現停頓、淡化或轉題。"),
            _t("transference_pattern", "移情／關係模式探索", "留意舊有關係期待如何出現在目前互動。", "人物關係具有反覆的期待、害怕或失望。"),
            _t("clarification_confrontation", "澄清與面質", "溫和指出敘說中的模糊、落差或矛盾。", "言語、情緒與行動之間存在可探索的不一致。"),
            _t("tentative_interpretation", "暫時性詮釋", "以假設語氣連結重複模式與早期經驗。", "目前困境可與早期重要關係形成合理但不武斷的連結。"),
        ],
        "experience_default": ["free_association", "resistance_exploration", "tentative_interpretation"],
    },
    "adlerian": {
        "name": "阿德勒學派",
        "core": "從目的性、生活風格、歸屬感與社會興趣理解個人的選擇。",
        "techniques": [
            _t("family_constellation", "家庭星座", "探索排行、手足及早期家庭互動。", "案例具有手足、照顧者角色與家庭位置脈絡。"),
            _t("early_recollection", "早期回憶", "從早期具體畫面理解現在的生活主題。", "能回想一段具體早年事件與當時感受。"),
            _t("lifestyle", "生活風格探索", "整理面對任務與關係時反覆採取的策略。", "困擾中有跨情境重複的自我看法或因應模式。"),
            _t("social_interest", "社會興趣", "探索歸屬、合作、貢獻與共同體連結。", "案例含人際歸屬、合作或貢獻感議題。"),
            _t("encouragement_reorientation", "鼓勵與再定向", "肯定努力與勇氣，嘗試更有建設性的方向。", "個案可辨識可行的小步驟並願意嘗試。"),
        ],
        "experience_default": ["family_constellation", "early_recollection", "social_interest"],
    },
    "person_centered": {
        "name": "個人中心治療",
        "core": "以真誠、無條件積極關懷與準確同理促進個案自我理解。",
        "techniques": [
            _t("empathic_reflection", "同理反映", "貼近個案觀點，反映其主觀經驗。", "有可被理解與展開的主觀經驗。"),
            _t("feeling_reflection", "情感反映", "指出語句或非語言訊息中的情緒。", "言語與可觀察情緒線索可供反映。"),
            _t("paraphrase_clarification", "重述／澄清", "用自己的話核對重點，避免過早解釋。", "敘說中有多層訊息或尚待釐清之處。"),
            _t("congruence", "真誠一致性", "適度、為個案利益而真實回應當下互動。", "關係中出現可被真誠但不搶焦點地回應的時刻。"),
            _t("here_now_relationship", "此時此刻的關係回應", "探索此刻在晤談關係中的感受與經驗。", "個案對諮商師或談話安全感出現可探索反應。"),
        ],
        "experience_default": ["empathic_reflection", "feeling_reflection", "congruence"],
    },
    "gestalt": {
        "name": "完形治療",
        "core": "提升此時此刻覺察，整合身體、情緒與未完成經驗。",
        "techniques": [
            _t("present_awareness", "此時此刻覺察", "把注意帶回此刻正在發生的經驗。", "敘說時出現當下可覺察的情緒轉變。"),
            _t("body_awareness", "身體感受覺察", "探索身體緊繃、呼吸、姿勢等可觀察感受。", "自然呈現身體訊號與非語言線索。"),
            _t("empty_chair", "空椅技術", "在準備足夠時向重要他人或部分自我表達。", "有重要關係的未竟情緒且具備適當安全度。"),
            _t("two_chair", "兩椅對話", "讓內在衝突的兩個部分輪流表達。", "存在清楚的兩難或互相拉扯的內在立場。"),
            _t("unfinished_experiment", "未竟事務／誇大與重複實驗", "用安全的小實驗深化未完成經驗的覺察。", "有重複動作、語句或尚未表達的情緒。"),
        ],
        "experience_default": ["present_awareness", "body_awareness", "empty_chair"],
    },
    "behavior": {
        "name": "行為治療",
        "core": "以可觀察的前因、行為與後果理解問題，透過練習改變行為。",
        "techniques": [
            _t("functional_analysis", "ABC／功能分析", "釐清前因、具體行為與後果。", "可描述明確觸發情境、行為與短長期結果。"),
            _t("self_monitoring", "自我監測", "記錄行為、情境、頻率與結果。", "目標行為可被定義與追蹤。"),
            _t("relaxation", "放鬆訓練", "以呼吸或肌肉放鬆降低生理喚起。", "有可觀察的緊繃、心跳或迴避前焦慮。"),
            _t("graded_exposure", "漸進暴露", "建立階層並逐步接近害怕情境。", "存在非危險但被迴避、可分級的情境。"),
            _t("reinforcement_activation", "增強／行為活化與行為契約", "安排可行行動並建立回饋或增強。", "有低活動、拖延或可用具體行為目標改善的困擾。"),
        ],
        "experience_default": ["functional_analysis", "self_monitoring", "graded_exposure"],
    },
    "cbt": {
        "name": "Beck 認知治療／CBT",
        "core": "合作辨識自動化思考，檢核證據並形成較平衡的想法與行動。",
        "techniques": [
            _t("automatic_thoughts", "辨識自動化思考", "捕捉情境中快速浮現的具體想法。", "案例能描述事件、情緒及當下腦中一句話。"),
            _t("evidence_review", "找證據支持與反證", "合作檢核想法的支持與不支持證據。", "有可查證而非純價值判斷的認知內容。"),
            _t("cognitive_restructuring", "認知重建／替代想法", "形成可信、平衡且有助行動的新觀點。", "檢核後能建立不過度正向的替代想法。"),
            _t("behavioral_experiment", "行為實驗", "用小型可觀察行動測試預測。", "核心預測可被安全且具體地測試。"),
            _t("activity_homework", "活動安排與家庭作業", "共同安排課後可完成並可回顧的練習。", "有清楚、低負擔、可追蹤的實作任務。"),
        ],
        "experience_default": ["automatic_thoughts", "evidence_review", "cognitive_restructuring"],
    },
    "rebt": {
        "name": "理情行為治療 REBT",
        "core": "辨識事件與情緒間的信念，辯證僵化要求並練習理性替代信念。",
        "techniques": [
            _t("abc_model", "ABC 模式", "區分觸發事件、信念與情緒行為結果。", "案例可清楚拆分 A、B、C。"),
            _t("irrational_belief", "辨識非理性信念", "找出必須、糟透了、無法忍受或自我貶抑。", "語句含僵化要求、災難化或全盤自評。"),
            _t("disputation", "駁斥／辯證非理性信念", "從邏輯、經驗與實用性合作辯證。", "信念可被堅定但尊重地檢視而非爭辯。"),
            _t("rational_emotive_imagery", "理性情緒意象", "在想像情境中練習把不健康情緒轉為健康負向情緒。", "有可安全想像且能辨識情緒差異的事件。"),
            _t("behavioral_belief_homework", "行為作業與新的理性信念練習", "用行動與自我陳述鞏固理性信念。", "可形成具體作業與可重複的新信念。"),
        ],
        "experience_default": ["abc_model", "irrational_belief", "disputation"],
    },
    "reality": {
        "name": "現實治療／選擇理論",
        "core": "聚焦當事人的需要、目前選擇、自我評估與可承諾的計畫。",
        "techniques": [
            _t("wants", "W：Wants 需求與想要", "釐清真正想要的關係、生活與結果。", "案例具有可釐清的需求與期望落差。"),
            _t("doing", "D：Doing 目前行為", "具體盤點目前正在做、想與感受什麼。", "可描述當下可選擇的整體行為。"),
            _t("evaluation", "E：Evaluation 自我評估", "邀請評估目前做法是否接近想要。", "行為與目標的效果可由個案自行判斷。"),
            _t("planning", "P：Planning 可行計畫", "形成簡單、可達成、可控制並可承諾的計畫。", "個案有控制範圍內的下一步。"),
            _t("choice_responsibility", "選擇與責任語言", "聚焦可選擇與願負責的部分，避免責備。", "能區分不可控制情境與自己的選擇。"),
        ],
        "experience_default": ["wants", "evaluation", "planning"],
    },
    "sfbt": {
        "name": "焦點解決短期治療 SFBT",
        "core": "從偏好未來、例外、資源與可行小步驟促進改變。",
        "techniques": [
            _t("miracle_question", "奇蹟問句", "具體描繪問題改善後可觀察的生活差異。", "可用日常細節描述偏好未來。"),
            _t("exception_question", "例外問句", "尋找問題較輕或沒有發生的時候。", "過去存在強度較低或成功因應的例外。"),
            _t("scaling_question", "量尺問句", "以 0 到 10 定位現況、資源與下一小格。", "狀態可被量尺化並探索分數背後的資源。"),
            _t("coping_question", "因應問句", "探索在困難中仍能撐住的做法與力量。", "個案雖困難但已展現維持生活的行動。"),
            _t("compliment_next_step", "讚美＋下一個小步驟", "具體肯定有效行動並共同找最小下一步。", "有可被具體肯定的行動及可延伸步驟。"),
        ],
        "experience_default": ["exception_question", "scaling_question", "miracle_question"],
    },
    "narrative": {
        "name": "敘事治療",
        "core": "把人與問題分開，探索問題影響、獨特結果與偏好身分故事。",
        "techniques": [
            _t("externalization", "問題外化", "把問題視為影響人的力量，而非人的本質。", "困擾容易被內化成負向身分標籤。"),
            _t("problem_naming", "為問題命名", "與個案共同用貼切語言命名問題。", "問題可由個案主導命名且避免污名化。"),
            _t("relative_influence", "相對影響問句", "探索問題如何影響生活及人如何回應問題。", "能呈現雙向影響而不只列症狀。"),
            _t("unique_outcome", "獨特結果／閃亮時刻", "找出問題未完全支配生活的例外行動。", "存在符合價值但容易被忽略的具體例外。"),
            _t("reauthoring", "重寫故事與偏好身分", "厚描例外背後的價值、能力與偏好身分。", "可連結例外、價值、見證者與未來行動。"),
        ],
        "experience_default": ["externalization", "unique_outcome", "reauthoring"],
    },
    "positive": {
        "name": "正向心理治療",
        "core": "在不否認痛苦的前提下，發展優勢、正向經驗、感恩、希望與意義。",
        "techniques": [
            _t("strength_identification", "優勢辨識", "從具體經驗辨識已展現的品格優勢。", "故事中有可由行動證據辨識的優勢。"),
            _t("strength_use", "優勢運用", "設計新的、適切的優勢使用方式。", "優勢能對目前困境形成可行的新用法。"),
            _t("three_good_things", "三件好事／正向事件探索", "留意正向事件、成因與自身貢獻。", "日常中有可被辨識而不否認困難的正向事件。"),
            _t("gratitude", "感恩練習", "探索真實感謝及合宜表達方式。", "有值得感謝的人事物且不強迫感恩。"),
            _t("hope_meaning_best_self", "希望、意義與最佳可能自我", "連結價值、路徑、能動性與可能未來。", "個案能探索有意義的目標與多條可行路徑。"),
        ],
        "experience_default": ["strength_identification", "three_good_things", "hope_meaning_best_self"],
    },
}


PRACTICE_THEMES = {
    "academic": "課業與表現壓力",
    "relationship": "人際關係與歸屬",
    "career": "生涯選擇與自我懷疑",
    "family": "家庭期待與界線",
    "internship": "實習壓力與角色適應",
    "self_worth": "自我價值與失敗經驗",
}


def get_school(school_id: str) -> dict[str, Any]:
    if school_id not in SCHOOLS:
        raise KeyError(f"未知學派：{school_id}")
    return SCHOOLS[school_id]


def get_techniques(school_id: str, ids: list[str]) -> list[dict[str, str]]:
    school = get_school(school_id)
    mapping = {item["id"]: item for item in school["techniques"]}
    missing = [item for item in ids if item not in mapping]
    if missing:
        raise KeyError(f"未知技巧：{', '.join(missing)}")
    return [mapping[item] for item in ids]


def validate_selected_techniques(school_id: str, ids: list[str]) -> None:
    if len(ids) != 3 or len(set(ids)) != 3:
        raise ValueError("實作模式必須選擇恰好三項不同技巧。")
    get_techniques(school_id, ids)
