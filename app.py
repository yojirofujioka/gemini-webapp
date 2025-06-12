import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account
from datetime import date
import math
import base64 # ★エラー修正のため、削除されていたbase64ライブラリを再インポート

# ----------------------------------------------------------------------
# 1. 設定と定数
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="AIリフォーム箇所分析レポート",
    page_icon="🏠",
    layout="wide"
)
BATCH_SIZE = 10 # 一度にAIに送信する写真の枚数

# ----------------------------------------------------------------------
# 2. デザインとGCP初期化
# ----------------------------------------------------------------------
def inject_custom_css():
    """レポートデザインを向上させるためのカスタムCSSを注入する。"""
    st.markdown("""
    <style>
        /* --- 基本的なレポートスタイル --- */
        .report-container { background-color: #ffffff; color: #333333; border-radius: 8px; border: 1px solid #e0e0e0; padding: 2.5em 3.5em; box-shadow: 0 8px 30px rgba(0,0,0,0.05); margin: 2em 0; }
        .report-container h1 { color: #1F2937; font-size: 2.5em; border-bottom: 3px solid #D1D5DB; padding-bottom: 0.4em; }
        .report-container h2 { color: #1F2937; font-size: 1.8em; border-bottom: 2px solid #E5E7EB; padding-bottom: 0.3em; margin-top: 2em; }
        .report-container hr { border: 1px solid #e0e0e0; margin: 2.5em 0; }
        .priority-badge { display: inline-block; padding: 0.3em 0.9em; border-radius: 15px; font-weight: 600; color: white; font-size: 0.9em; margin-left: 10px; }
        .priority-high { background-color: #DC2626; }
        .priority-medium { background-color: #F59E0B; }
        .priority-low { background-color: #3B82F6; }
        
        /* --- 画面表示時のスタイル (1列表示) --- */
        .photo-section { border-top: 1px solid #e0e0e0; padding-top: 2rem; margin-top: 2rem; }
        .report-container .photo-section:first-of-type { border-top: none; padding-top: 0; margin-top: 0; }
        .photo-section h3 { color: #374151; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 600; }
        .image-container img { max-height: 400px; width: auto; max-width: 100%; }

        /* --- 印刷時のスタイル --- */
        @media print {
            .main > .block-container > div:nth-child(1) > div:nth-child(1) > div:not(.printable-report) { display: none !important; }
            .stApp > header, .stApp > footer, .stToolbar, #stDecoration { display: none !important; }
            body { background-color: #ffffff !important; }
            .printable-report { box-shadow: none; border: none; padding: 0; margin: 0; }
            .print-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; page-break-after: always; }
            .print-item { border: 1px solid #ccc; padding: 15px; border-radius: 8px; display: flex; flex-direction: column; page-break-inside: avoid; }
            .print-item h3 { font-size: 12px; margin: 0 0 10px 0; font-weight: bold; }
            .print-item .image-box { height: 180px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; overflow: hidden; }
            .print-item .image-box img { width: 100%; height: 100%; object-fit: contain; }
            .print-item .text-box { font-size: 10px; line-height: 1.4; }
            .print-item .priority-badge { font-size: 9px; padding: 2px 6px; }
        }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def initialize_vertexai():
    try:
        gcp_secrets = st.secrets["gcp"]
        service_account_info = json.loads(gcp_secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        vertexai.init(project=gcp_secrets["project_id"], location="asia-northeast1", credentials=credentials)
        return GenerativeModel("gemini-1.5-pro")
    except Exception as e:
        st.error(f"GCPの認証またはVertex AIの初期化に失敗しました: {e}")
        return None

# ----------------------------------------------------------------------
# 3. AIとデータ処理の関数
# ----------------------------------------------------------------------
def create_report_prompt(filenames):
    file_list_str = "\n".join([f"- {name}" for name in filenames])
    return f"""
    あなたは、日本のリフォーム・原状回復工事を専門とする、経験豊富な現場監督です。あなたの仕事は、提供された現場写真を分析し、クライアントに提出するための、丁寧で分かりやすい修繕提案レポートを作成することです。以下の写真（ファイル名と共に提示）を一枚ずつ詳細に確認し、修繕や交換が必要と思われる箇所をすべて特定してください。特定した各箇所について、以下のJSON形式で報告書を作成してください。
    **最重要**: あなたの出力は、純粋なJSON文字列のみでなければなりません。説明文や ```json ... ``` のようなマークダウンは絶対に含めないでください。
    **JSONの構造**:
    出力は、JSONオブジェクトのリスト形式 `[ ... ]` としてください。各オブジェクトは1枚の写真に対応します。
    各写真オブジェクトには、以下のキーを含めてください。
    - "file_name": (string) 分析対象の写真のファイル名。
    - "findings": (array) その写真から見つかった指摘事項のリスト。指摘がない場合は空のリスト `[]` としてください。
    - "observation": (string) 【重要】"findings"が空の場合にのみ、写真から読み取れる客観的な情報を記述してください（例：「TOTO製トイレ、型番TCF8GM23。目立った傷や汚れなし。」）。"findings"がある場合は空文字列 `""` としてください。
    "findings" 配列の各指摘事項オブジェクトには、以下のキーを含めてください。
    - "location": (string) 指摘箇所の具体的な場所。
    - "current_state": (string) 現状の客観的な説明。
    - "suggested_work": (string) 提案する工事内容。
    - "priority": (string) 工事の緊急度を「高」「中」「低」の3段階で評価。
    - "notes": (string) クライアントへの補足事項。
    ---
    分析対象のファイルリスト: {file_list_str}
    ---
    それでは、以下の写真の分析を開始してください。
    """

def generate_ai_report(model, file_batch, prompt):
    image_parts = [Part.from_data(f.getvalue(), mime_type=f.type) for f in file_batch]
    response = model.generate_content([prompt] + image_parts)
    return response.text

def parse_json_response(text):
    match = re.search(r'```(json)?\s*(.*?)\s*```', text, re.DOTALL)
    json_str = match.group(2) if match else text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        st.error("AIの応答をJSONとして解析できませんでした。")
        st.info("AIからの生の応答:"); st.code(text, language="text")
        return None

# ----------------------------------------------------------------------
# 4. レポート表示の関数
# ----------------------------------------------------------------------
def get_finding_html(finding):
    priority = finding.get('priority', 'N/A')
    p_class = {"高": "high", "中": "medium", "低": "low"}.get(priority, "")
    html = f"<b>指摘箇所: {finding.get('location', 'N/A')}</b> <span class='priority-badge priority-{p_class}'>緊急度: {priority}</span><br>"
    html += f"- <b>現状:</b> {finding.get('current_state', 'N/A')}<br>"
    html += f"- <b>提案工事:</b> {finding.get('suggested_work', 'N/A')}<br>"
    if finding.get('notes'):
        html += f"- <b>備考:</b> {finding.get('notes', 'N/A')}"
    return html

def display_full_report(report_payload, files_dict):
    report_data = report_payload.get('report_data', [])
    report_title = report_payload.get('title', '')
    survey_date = report_payload.get('date', '')

    # --- 画面表示用のレポート ---
    with st.container():
        st.markdown('<div class="report-container">', unsafe_allow_html=True)
        st.markdown(f"<h1>現場分析レポート</h1>", unsafe_allow_html=True)
        c1, c2 = st.columns(2); c1.markdown(f"**物件名・案件名:**<br>{report_title or '（未設定）'}", unsafe_allow_html=True); c2.markdown(f"**調査日:**<br>{survey_date}", unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<h2>📊 分析結果サマリー</h2>", unsafe_allow_html=True)
        total_findings = sum(len(item.get("findings", [])) for item in report_data)
        high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
        m1, m2, m3 = st.columns(3); m1.metric("分析写真枚数", f"{len(report_data)} 枚"); m2.metric("総指摘件数", f"{total_findings} 件"); m3.metric("緊急度「高」の件数", f"{high_priority_count} 件")
        st.markdown("<hr>", unsafe_allow_html=True)
        
        st.markdown("<h2>📋 詳細分析結果（画面表示用）</h2>", unsafe_allow_html=True)
        for i, item in enumerate(report_data):
            st.markdown('<div class="photo-section">', unsafe_allow_html=True)
            st.markdown(f"<h3>{i + 1}. 写真ファイル: {item.get('file_name', '')}</h3>", unsafe_allow_html=True)
            col1, col2 = st.columns([2, 3])
            with col1:
                if files_dict and item.get('file_name') in files_dict:
                    st.image(files_dict[item['file_name']], use_container_width=True)
            with col2:
                findings = item.get("findings", [])
                if findings:
                    for finding in findings:
                        st.markdown(get_finding_html(finding), unsafe_allow_html=True)
                        st.markdown("---")
                elif item.get("observation"):
                    st.info(f"**【AIによる所見】**\n\n{item['observation']}")
                else:
                    st.success("✅ 特に修繕が必要な箇所は見つかりませんでした。")
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- 印刷用の非表示レポート ---
    st.markdown('<div class="printable-report" style="display:none;">', unsafe_allow_html=True)
    for i in range(0, len(report_data), 3):
        st.markdown('<div class="print-grid">', unsafe_allow_html=True)
        for j in range(3):
            if i + j < len(report_data):
                item = report_data[i+j]
                file_name = item.get('file_name', '')
                image_html = ""
                if files_dict and file_name in files_dict:
                    image_bytes = files_dict[file_name].getvalue()
                    b64_img = base64.b64encode(image_bytes).decode() # ★この行でbase64が必要
                    image_html = f'<div class="image-box"><img src="data:image/png;base64,{b64_img}"></div>'
                
                text_html = ""
                findings = item.get("findings", [])
                if findings:
                    for finding in findings:
                        text_html += get_finding_html(finding) + "<br>"
                elif item.get("observation"):
                    text_html = f"<b>【AIによる所見】</b><br>{item['observation']}"
                else:
                    text_html = "特に修繕が必要な箇所は見つかりませんでした。"

                st.markdown(f"""
                <div class="print-item">
                    <h3>{i+j+1}. {file_name}</h3>
                    {image_html}
                    <div class="text-box">{text_html}</div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 5. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    inject_custom_css()
    model = initialize_vertexai()

    if 'report_payload' in st.session_state:
        st.success("✅ レポートの作成が完了しました！")
        st.info("💡 レポートをPDFとして保存するには、ブラウザの印刷機能（Ctrl+P または Cmd+P）を使用してください。")
        if st.button("新しいレポートを作成する", key="new_from_result"):
            st.session_state.clear()
            st.rerun()
        
        display_full_report(st.session_state.report_payload, st.session_state.files_dict)
        return

    st.title("📷 AIリフォーム箇所分析＆報告書作成")
    st.markdown("現場写真をアップロードすると、AIがクライアント向けの修繕提案レポートを自動作成します。")

    if not model:
        st.warning("AIモデルを読み込めませんでした。"); st.stop()

    report_title = st.text_input("物件名・案件名", "（例）〇〇ビル 301号室 原状回復工事")
    survey_date = st.date_input("調査日", date.today())
    
    uploaded_files = st.file_uploader(
        "分析したい写真を選択",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="file_uploader"
    )
    
    if uploaded_files:
        st.success(f"{len(uploaded_files)}件の写真がアップロードされました。")
    
    is_processing = st.session_state.get('processing', False)
    submitted = st.button(
        "レポートを作成する",
        type="primary",
        use_container_width=True,
        disabled=not uploaded_files or is_processing
    )

    if submitted:
        st.session_state.processing = True
        st.session_state.uploaded_files = uploaded_files # 分析中に使うため保存
        st.session_state.report_title_val = report_title
        st.session_state.survey_date_val = survey_date
        st.rerun() # 処理中UIに切り替える

def run_analysis():
    """st.rerunの後に実行される分析処理の本体"""
    model = initialize_vertexai()
    uploaded_files = st.session_state.uploaded_files
    report_title = st.session_state.report_title_val
    survey_date = st.session_state.survey_date_val
    
    st.info("分析処理を実行中です。このままお待ちください...")
    total_batches = math.ceil(len(uploaded_files) / BATCH_SIZE)
    progress_bar = st.progress(0, text="AI分析の準備をしています...")
    
    final_report_data = []
    try:
        for i in range(0, len(uploaded_files), BATCH_SIZE):
            current_batch_num = (i // BATCH_SIZE) + 1
            progress_text = f"AIが写真を分析中... (バッチ {current_batch_num}/{total_batches})"
            progress_bar.progress(i / len(uploaded_files), text=progress_text)

            file_batch = uploaded_files[i:i + BATCH_SIZE]
            filenames = [f.name for f in file_batch]
            prompt = create_report_prompt(filenames)
            
            response_text = generate_ai_report(model, file_batch, prompt)
            batch_report_data = parse_json_response(response_text)
            
            if batch_report_data:
                final_report_data.extend(batch_report_data)
            else:
                st.error(f"バッチ {current_batch_num} の分析中にエラーが発生しました。")
        
        progress_bar.progress(1.0, text="分析完了！レポートを生成中です...")
        
        st.session_state.files_dict = {f.name: f for f in uploaded_files}
        report_payload = {
            "title": report_title,
            "date": survey_date.strftime('%Y年%m月%d日'),
            "report_data": final_report_data
        }
        st.session_state.report_payload = report_payload
        
    except Exception as e:
        st.error(f"分析処理全体で予期せぬエラーが発生しました: {e}")
    finally:
        st.session_state.processing = False
        # 不要になった一時データを削除
        for key in ['uploaded_files', 'report_title_val', 'survey_date_val']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

if __name__ == "__main__":
    if st.session_state.get('processing', False):
        run_analysis()
    else:
        main()
