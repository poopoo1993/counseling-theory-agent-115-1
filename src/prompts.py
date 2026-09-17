"""角色、案例、對話、評量與續談快照提示詞。"""

from __future__ import annotations

import json
from typing import Any

from .theory_library import get_school, get_techniques
from .transcript import transcript_text


PRACTICE_CASE_KEYS = (
    "case_id",
    "display_name",
    "public_opening",
    "persona",
    "presenting_problem",
    "hidden_formulation",
    "disclosure_layers",
    "resistance_rules",
    "nonverbal_baseline",
)


def case_data_from_plan(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan:
        return None
    case = {key: plan[key] for key in PRACTICE_CASE_KEYS if key in plan}
    return case or None


COMMON_SYSTEM = """你正在執行大學諮商教學的虛構文字模擬，不是真實心理治療、診斷或危機服務。
不得要求真實姓名、電話、地址、學校或機構等可識別資訊。若內容出現明確即時自傷或他傷意圖，停止角色模擬並建議立即尋求真人協助。
使用繁體中文。括弧只描述可觀察的非語言行為，例如（視線移開）或（雙手微微握緊）；不可用括弧直接揭露內心、診斷或評分。非語言訊息須自然、低頻且有功能，不必每句出現。"""


def _technique_block(school_id: str, selected_ids: list[str]) -> str:
    school = get_school(school_id)
    selected = get_techniques(school_id, selected_ids)
    return "\n".join(
        f"- {item['name']}：{item['short']} 案例可用條件：{item['affordance']}" for item in selected
    ) + f"\n學派核心：{school['core']}"


def build_knowledge_block(school_id: str, selected_ids: list[str]) -> str:
    """Shared counseling knowledge for planner, analyzer, and chatbot. Names come only from SCHOOLS."""
    school = get_school(school_id)
    selected = get_techniques(school_id, selected_ids)
    lines = [
        COMMON_SYSTEM,
        f"學派：{school['name']}（school_id={school_id}）",
        f"學派核心：{school['core']}",
        "指定技巧（只能使用下列 id 與中文名稱，不得發明新技巧或改名）：",
    ]
    for item in selected:
        lines.append(
            f"- technique_id={item['id']} 名稱={item['name']}：{item['short']} 可用條件：{item['affordance']}"
        )
    return "\n".join(lines)


def build_counseling_plan_prompt(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    theme: str,
    difficulty: str,
    prior_snapshot: dict[str, Any] | None = None,
    prior_plan: dict[str, Any] | None = None,
    prior_analysis: dict[str, Any] | None = None,
) -> str:
    school = get_school(school_id)
    knowledge = build_knowledge_block(school_id, selected_ids)
    prior = {
        "prior_snapshot": snapshot_for_dialogue(prior_snapshot),
        "prior_plan": prior_plan or {},
        "prior_analysis": prior_analysis or {},
    }
    if mode == "practice":
        return f"""你是內部「諮商計畫」引擎，不是對學生說話的聊天角色。根據學派方法擬定計畫與需要蒐集的資訊。輸出僅供系統使用，學生看不到。
知識庫：
{knowledge}
模式：practice（學生當諮商師，AI 當標準化個案）
主題：{theme}
難度：{difficulty}
前次狀態：{json.dumps(prior, ensure_ascii=False)}
續談時延續同一人物與已談內容，但不要把尚未完成議題寫成學生應先完成的目標清單；形成晤談目標是學生諮商師的任務。

請建立虛構成人或大學生個案，讓三項指定技巧都有合理機會，但不可在開場一次揭露答案。不要使用真實人物或危機情節。info_targets 是學生諮商師依本學派需要探問／觀察的資訊；status 初始為 pending。technique_id 只能出自知識庫。
只輸出 JSON：
{{
  "mode": "practice",
  "school_id": "{school_id}",
  "case_id": "簡短英文代碼",
  "display_name": "虛構名字或稱呼",
  "public_opening": "個案第一句，1至3句，可含自然非語言訊息",
  "persona": "年齡層、角色、語氣與互動風格",
  "presenting_problem": "表層主訴",
  "hidden_formulation": "深層議題與關係模式，禁止直接對學生揭露",
  "disclosure_layers": ["先可說內容", "關係較安全後可說內容", "合適技巧後可說內容"],
  "resistance_rules": ["探索不足時的反應", "介入合宜時的反應"],
  "nonverbal_baseline": ["最多三項可觀察線索"],
  "phase_goals": ["本學派階段目標"],
  "info_targets": [{{"id": "t1", "intent": "要蒐集的資訊", "school_method": "對應{school['name']}方法", "status": "pending"}}],
  "do_not_disclose": ["技巧名稱", "教學講課", "隱藏設定"]
}}"""

    return f"""你是內部「諮商計畫」引擎，不是對學生說話的聊天角色。根據學派方法擬定示範諮商計畫，以及示範諮商師需要向學生個案蒐集的資訊。輸出僅供系統使用，學生看不到。
知識庫：
{knowledge}
模式：experience（學生當個案，AI 當{school['name']}示範諮商師）
主題：{theme}
難度：{difficulty}
前次狀態：{json.dumps(prior, ensure_ascii=False)}
續談時延續同一示範諮商師與已談內容，但不要把尚未完成議題當成開場目標清單；從當下對話中探問與形成焦點。

info_targets 必須貼近該學派蒐集資料的方式，不得發明知識庫以外的技巧名稱。status 初始為 pending。晤談中仍不得對學生說出技巧名稱或講課。
只輸出 JSON：
{{
  "mode": "experience",
  "school_id": "{school_id}",
  "opening_approach": "低威脅開場方式，並可提醒學生用虛構或低敏感內容練習",
  "phase_goals": ["本學派階段目標"],
  "info_targets": [{{"id": "t1", "intent": "示範諮商師要了解的資訊", "school_method": "對應{school['name']}方法", "status": "pending"}}],
  "do_not_disclose": ["技巧名稱", "評量學生", "教學講課"]
}}"""


def coaching_tier(difficulty: str) -> str:
    value = str(difficulty or "").strip()
    if value == "初階":
        return "easy"
    if value == "中階":
        return "medium"
    return "hard"


def live_plan_visible(difficulty: str) -> bool:
    """初階在對話旁顯示依現況調整的計畫與例句。"""
    return coaching_tier(difficulty) == "easy"


def turn_review_visible(difficulty: str) -> bool:
    """初階與中階在對話中顯示單句回饋／目標效果。"""
    return coaching_tier(difficulty) in {"easy", "medium"}


def thought_coach_visible(mode: str, difficulty: str) -> bool:
    """實作初階／中階顯示旁欄想法框；體驗與進階不顯示。"""
    return mode == "practice" and turn_review_visible(difficulty)


def live_coaching_enabled(mode: str, difficulty: str) -> bool:
    """Any student-visible in-session analyzer coaching. 進階仍只在結束後回饋。"""
    del mode
    return turn_review_visible(difficulty)


def uses_planner_llm(mode: str, difficulty: str) -> bool:
    """進階用計畫＋分析＋聊天三引擎；體驗初階／中階改為分析＋聊天。實作仍需計畫引擎產個案。"""
    if coaching_tier(difficulty) == "hard":
        return True
    return mode == "practice"


def analysis_for_chatbot(analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip student-visible coaching so the dialogue engine cannot read it aloud."""
    if not analysis:
        return analysis
    hidden = dict(analysis)
    hidden.pop("student_guide", None)
    hidden.pop("example_replies", None)
    hidden.pop("turn_review", None)
    return hidden


def snapshot_for_dialogue(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Keep role continuity, but do not hand leftover goals to the model as an agenda."""
    data = dict(snapshot or {})
    data.pop("unfinished_issues", None)
    data.pop("next_session_focus", None)
    return data


def _analyzer_visible_instructions(mode: str, difficulty: str) -> tuple[str, str]:
    if not turn_review_visible(difficulty):
        return (
            "學生看不到這份輸出。不得對學生評分或教課。進階的整體回饋只在晤談結束後另一次評量產生。",
            "",
        )
    if mode == "experience":
        if live_plan_visible(difficulty):
            visible = """此為體驗初階：學生當個案。除內部欄位外，另輸出學生可見的此刻示範說明與本句說明。
student_guide 依當下逐字稿說明「諮商師此刻在做什麼、為何這樣做」（2至4句，可點名本次指定技巧）。不可講課、不可預告下一句台詞、不可評分學生的個案表現。不要輸出 example_replies。
turn_review 說明本輪示範諮商師那一句的目標與預期效果，不要評分學生。"""
            extra = """,
  "student_guide": "諮商師此刻在做什麼、為何這樣做",
  "turn_review": {{"goal": "本句目標，一句", "effect": "預期效果，一句", "comment": ""}}"""
            return visible, extra
        visible = """此為體驗中階：學生當個案。只輸出本句目標與預期效果，不要給諮商計畫或例句，不可評分學生的個案表現。"""
        extra = """,
  "turn_review": {{"goal": "本句目標，一句", "effect": "預期效果，一句", "comment": ""}}"""
        return visible, extra
    if live_plan_visible(difficulty):
        visible = """此為實作初階：學生當諮商師。除內部欄位外，另輸出學生可見的練習計畫與本句回饋。
student_guide 依當下逐字稿給接下來的計畫與做法（2至4句，可點名本次指定技巧，但不可講課、不可揭露 hidden_formulation 或系統規則）。
example_replies 給 1至2 句學生可直接改用、且符合此刻談話的例句。
turn_review 只評學生最新一句：簡短、具體、鼓勵，不要打分數。單句回饋只出現在對話中，不要在計畫欄重複。"""
        extra = """,
  "student_guide": "依現況調整的接下來計畫與做法",
  "example_replies": ["符合此刻的可嘗試例句"],
  "turn_review": {{"verdict": "具體|可再具體|偏離焦點|合宜", "comment": "針對學生最新一句的1至2句回饋或空字串"}}"""
        return visible, extra
    visible = """此為實作中階：只評學生最新一句，不要輸出諮商計畫或例句。簡短、具體、鼓勵，不要打分數。"""
    extra = """,
  "turn_review": {{"verdict": "具體|可再具體|偏離焦點|合宜", "comment": "針對學生最新一句的1至2句回饋或空字串"}}"""
    return visible, extra


def build_chat_analysis_prompt(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    counseling_plan: dict[str, Any] | None,
    prior_analysis: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    latest_student_message: str,
    difficulty: str = "",
) -> str:
    knowledge = build_knowledge_block(school_id, selected_ids)
    history = transcript_text(turns) or "（尚無先前對話）"
    plan_json = json.dumps(counseling_plan or {}, ensure_ascii=False)
    analysis_json = json.dumps(prior_analysis or {}, ensure_ascii=False)
    visible, extra_json = _analyzer_visible_instructions(mode, difficulty)
    return f"""你是「對話分析」引擎，不是聊天角色。根據諮商計畫分析目前對話、已揭露與可能隱藏或未說完的資訊，並給聊天引擎下一個焦點。
不得發明知識庫以外的技巧名稱。
{visible}
知識庫：
{knowledge}
模式：{mode}
難度：{difficulty or "未指定"}
諮商計畫：{plan_json}
前次分析：{analysis_json}
完整逐字稿：
{history}
學生最新一句：{latest_student_message or "（開場，尚無學生新句）"}

只輸出 JSON：
{{
  "gathered_targets": [{{"id": "計畫中的 info_target id", "evidence_quote": "逐字稿原句或空字串"}}],
  "hidden_or_incomplete": [{{"id": "info_target id", "hypothesis": "可能尚未說出或被避開的內容"}}],
  "still_needed": [{{"id": "info_target id", "why": "為何仍需要"}}],
  "hiding_cues": ["可觀察的避開、簡答或轉移"],
  "next_focus": "聊天引擎下一句應朝向的單一焦點，不要寫技巧名稱"{extra_json}
}}"""


def build_case_prompt(school_id: str, selected_ids: list[str], theme: str, difficulty: str) -> str:
    school = get_school(school_id)
    return f"""請建立一名虛構、可供諮商技巧練習的標準化成人或大學生個案。
學派：{school['name']}
主題：{theme}
難度：{difficulty}
所選技巧與必要可用條件：
{_technique_block(school_id, selected_ids)}

案例必須讓三項技巧都有合理機會使用，但不可在開場一次揭露答案。個案要有一致的人物背景、語氣、核心困擾、阻力與三層漸進揭露。不要使用真實人物或危機情節。
只輸出 JSON，欄位如下：
{{
  "case_id": "簡短英文代碼",
  "display_name": "虛構名字或稱呼",
  "public_opening": "個案第一句，1至3句，可含自然非語言訊息",
  "persona": "年齡層、角色、語氣與互動風格",
  "presenting_problem": "表層主訴",
  "hidden_formulation": "深層議題與關係模式，禁止直接對學生揭露",
  "disclosure_layers": ["先可說內容", "關係較安全後可說內容", "合適技巧後可說內容"],
  "resistance_rules": ["探索不足時的反應", "介入合宜時的反應"],
  "nonverbal_baseline": ["最多三項可觀察線索"]
}}"""


def build_dialogue_prompt(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    latest_student_message: str,
    case_data: dict[str, Any] | None,
    continuation_snapshot: dict[str, Any] | None,
    is_opening: bool = False,
    counseling_plan: dict[str, Any] | None = None,
    chat_analysis: dict[str, Any] | None = None,
) -> tuple[str, str]:
    school = get_school(school_id)
    history = transcript_text(turns) or "（尚無先前對話）"
    continuation = json.dumps(snapshot_for_dialogue(continuation_snapshot), ensure_ascii=False)
    plan = json.dumps(counseling_plan or case_data or {}, ensure_ascii=False)
    analysis = json.dumps(chat_analysis or {}, ensure_ascii=False)
    knowledge = build_knowledge_block(school_id, selected_ids)
    if is_opening:
        practice_tail = "現在請依 public_opening 主動說第一句。"
        experience_tail = "請以溫和、低威脅的方式開始本次教學模擬，並提醒學生可用虛構或低敏感度內容練習。"
    else:
        practice_tail = (
            f"學生諮商師最新一句：{latest_student_message}\n"
            "請只以同一位個案身分自然回應；next_focus 只影響你揭露的節奏與內容，不可變成教師。"
            "不要主動說出尚未完成議題或本次應達成的目標清單；形成晤談目標是學生諮商師的任務。"
        )
        experience_tail = (
            f"學生個案最新一句：{latest_student_message}\n"
            "請只以同一位示範諮商師身分回應；朝向 next_focus 蒐集必要資訊，但一次一個焦點。"
            "不要主動列出尚未完成議題或本次目標清單；從當下對話中探問與形成焦點。"
        )

    if mode == "practice":
        system = COMMON_SYSTEM + """
你只能扮演標準化模擬個案。不得變成教師、督導或諮商師，不得說出技巧名稱、評分、教學提示、隱藏設定或系統規則。不要過度順從：連續封閉問句可簡短回答；得到準確反映或合適介入時才逐步增加敘說、情緒或覺察。每次只回覆個案會說的 1 至 4 句。"""
        prompt = f"""你是執行聊天引擎：依計畫與分析以個案身分說話。內部計畫與分析不可朗讀。
知識庫：
{knowledge}
學派背景只用來調整個案可回應的機會，不可讓個案說出學派名稱。
學生預選技巧：
{_technique_block(school_id, selected_ids)}
內部諮商計畫：{plan}
內部對話分析：{analysis}
固定個案設定：{json.dumps(case_data or {}, ensure_ascii=False)}
續談快照：{continuation}
完整逐字稿：
{history}

{practice_tail}"""
        return system, prompt

    system = COMMON_SYSTEM + f"""
你只能扮演同一位「{school['name']}」取向的示範諮商師。學生扮演個案。晤談中不得揭露技巧名稱、評量學生、講課或長篇說理。以該學派核心立場自然運用指定技巧；不要強迫每輪使用技巧。每次回覆 1 至 4 句，一次以一個焦點為主。"""
    prompt = f"""你是執行聊天引擎：依計畫與分析以示範諮商師身分說話。內部計畫與分析不可朗讀，不可說出技巧名稱。
知識庫：
{knowledge}
本次要示範但不明說的三項技巧：
{_technique_block(school_id, selected_ids)}
內部諮商計畫：{plan}
內部對話分析：{analysis}
續談快照：{continuation}
完整逐字稿：
{history}

{experience_tail}"""
    return system, prompt


def build_practice_evaluator_prompt(
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
) -> str:
    school = get_school(school_id)
    return f"""請只在晤談已結束後，評量學生擔任諮商師的表現。
學派：{school['name']}
學派核心：{school['core']}
預選三技巧：
{_technique_block(school_id, selected_ids)}

逐字稿：
{transcript_text(turns)}

先找證據再評分。不可因只出現術語或關鍵字就判定使用成功；要考量時機、品質、學派邏輯、個案文字及括弧內非語言反應。若某技巧確實沒有適當機會，標為 no_opportunity，不可等同漏用。使用未選取的同學派技巧列為 extension_skill，不扣分。回饋先具體肯定 2 至 3 點，再聚焦 1 至 2 個最重要的改善方向，語氣支持但不可空泛稱讚。

只輸出 JSON：
{{
  "total_score": 0到100整數,
  "dimensions": {{
    "theory_fit": {{"score": 0到20, "reason": "理由"}},
    "selected_skills": {{"score": 0到20, "reason": "理由"}},
    "timing_process": {{"score": 0到20, "reason": "理由"}},
    "responsiveness": {{"score": 0到20, "reason": "理由"}},
    "communication_professionalism": {{"score": 0到20, "reason": "理由"}}
  }},
  "skill_events": [{{"technique_id": "技巧ID", "status": "used|missed_opportunity|no_opportunity|extension_skill", "turn_index": 整數或null, "quality": "mechanical|appropriate|natural_helpful|not_observed", "evidence_quote": "逐字稿原句或空字串", "effect": "個案反應或判斷"}}],
  "strengths": [{{"point": "具體優點", "evidence_quote": "學生原句", "effect": "可能效果"}}],
  "improvement_points": [{{"point": "優先改善處", "evidence_quote": "學生原句", "reason": "理由"}}],
  "alternative_responses": [{{"original_quote": "學生原句", "better_response": "更貼近本學派的替代句", "why": "理由"}}],
  "encouragement": "具體、真誠且不誇大的鼓勵",
  "next_practice_focus": ["一至兩項下次任務"],
  "limitations": "形成性 AI 評量限制"
}}"""


def build_experience_analysis_prompt(
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
) -> str:
    school = get_school(school_id)
    return f"""學生剛完成「學生當個案、AI 當示範諮商師」的教學體驗。不可評分學生的自我揭露或個案表現。
學派：{school['name']}
預定示範技巧：
{_technique_block(school_id, selected_ids)}
逐字稿：
{transcript_text(turns)}

只輸出 JSON：
{{
  "mode": "experience",
  "score": null,
  "technique_explanations": [{{"technique_id": "技巧ID", "ai_quote": "AI諮商師原句", "why_used": "當下理由", "possible_effect": "可能效果", "turn_index": 整數或null}}],
  "overall_learning": "本次學派體驗重點",
  "encouragement": "鼓勵學生觀察與反思的具體文字",
  "reflection_questions": ["一至兩個不要求揭露隱私的反思問題"]
}}"""


def build_snapshot_prompt(
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    prior_snapshot: dict[str, Any] | None,
) -> str:
    ai_role = "ai_client" if mode == "practice" else "ai_counselor"
    prior_json = json.dumps(prior_snapshot or {}, ensure_ascii=False)
    return f"""請為下一次續談建立中性、結構化快照。模式={mode}，延續角色={ai_role}，學派={school_id}，本次技巧={selected_ids}。
前次快照：{prior_json}
本次逐字稿：
{transcript_text(turns)}

只輸出 JSON：
{{
  "continuation_role": "{ai_role}",
  "relationship_summary": "目前晤談關係與互動風格",
  "disclosed_topics": ["已談主題，不含可識別資料"],
  "emotional_state": "目前情緒狀態",
  "prior_interventions": ["已出現的重要介入"],
  "student_response_patterns": "學生在其角色中的反應模式",
  "unfinished_issues": ["尚未完成議題"],
  "next_session_focus": ["可自然接續的焦點"],
  "ai_role_consistency": "下次需維持的同一位 AI 個案或諮商師特徵"
}}"""


def build_thought_coach_prompt(
    *,
    mode: str,
    school_id: str,
    selected_ids: list[str],
    turns: list[dict[str, Any]],
    student_guide: str,
    example_replies: list[str],
    prior_notes: list[dict[str, Any]],
    latest_thought: str,
) -> tuple[str, str]:
    knowledge = build_knowledge_block(school_id, selected_ids)
    history = transcript_text(turns) or "（尚無模擬對話）"
    notes = "\n".join(
        f"{'學生' if item.get('role') == 'student' else '回應'}：{item.get('content', '')}"
        for item in (prior_notes or [])[-6:]
    ) or "（尚無先前想法）"
    examples = "\n".join(f"- {item}" for item in example_replies if str(item).strip()) or "（尚無例句）"
    if mode == "practice":
        system = COMMON_SYSTEM + """
你是實作的教學督導，只回應學生對此刻晤談的想法與判斷。可以點名本次指定技巧、肯定合宜判斷、溫和校正偏離。
不得扮演模擬個案，不得把這段話當成晤談對話，不得要求真實個資，不要打分數。每次回覆 2 至 5 句。"""
        role_note = "模式：practice（學生當諮商師）。針對其臨床想法作答。"
    else:
        system = COMMON_SYSTEM + """
你是初階體驗的教學解說者，只回應學生對示範晤談的觀察與想法。可以說明此刻做法為何、可能效果為何。
不得評分學生的個案表現，不得扮演模擬諮商師把這段話當成晤談對話，不得要求真實個資。每次回覆 2 至 5 句。"""
        role_note = "模式：experience（學生當個案）。針對其觀察與理解作答，不評分個案表現。"
    prompt = f"""請回覆學生此刻寫下的想法與判斷。
{role_note}
知識庫：
{knowledge}
旁欄計畫：{student_guide or "（尚無）"}
旁欄例句：
{examples}
模擬逐字稿（僅供對照，不要延續其角色說話）：
{history}
先前想法對話：
{notes}
學生此刻想法：{latest_thought}
"""
    return system, prompt
