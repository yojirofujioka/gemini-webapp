import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account
from datetime import date
import zlib
import base64
import math

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
        .report-container { background-color: #ffffff; color: #333333; border-radius: 8px; border: 1px solid #e0e0e0; padding: 2.5em 3.5em; box-shadow: 0 8px 30px rgba(0,0,0,0.05); margin: 2em 0; }
        .report-container h1 { color: #1F2937; font-size: 2.5em; border-bottom: 3px solid #D1D5DB; padding-bottom: 0.4em; }
        .report-container h2 { color: #1F2937; font-size: 1.8em; border-bottom: 2px solid #E5E7EB; padding-bottom: 0.3em; margin-top: 2em; }
        .report-container hr { border: 1px solid #e0e0e0; margin: 2.5em 0; }
        .photo-section { page-break-inside: avoid !important; padding-top: 2rem; margin-top: 2rem; border-top: 1px solid #e0e0e0; }
        .report-container .photo-section:first-of-type { border-top: none; padding-top: 0; margin-top: 0; }
        .photo-section h3 { color: #374151; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 600; }
        .priority-badge { display: inline-block; padding: 0.3em 0.9em; border-radius: 15px; font-weight: 600; color: white; font-size: 0.9em; margin-left: 10px; }
        .priority-high { background-color: #DC2626; }
        .priority-medium { background-color: #F59E0B; }
        .priority-low { background-color: #3B82F6; }
        .no-print { /* このクラスを持つ要素は印刷しない */ }
        @media print {
            .no-print { display: none !important; }
            .stApp > header, .stApp > footer, .stToolbar, #stDecoration { display: none !important; }
            body { background-color: #ffffff !important; }
            .report-container { box-shadow: none; border: 1px solid #ccc; padding: 1em; margin: 0; }
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

def encode_report_data(data):
    json_str = json.dumps(data)
    compressed = zlib.compress(json_str.encode('utf-8'))
    return base64.urlsafe_b64encode(compressed).decode('utf-8')

def decode_report_data(encoded_data):
    try:
        compressed = base64.urlsafe_b64decode(encoded_data)
        json_str = zlib.decompress(compressed).decode('utf-8')
        return json.loads(json_str)
    except Exception:
        return None

# ----------------------------------------------------------------------
# 4. レポート表示の関数
# ----------------------------------------------------------------------
def display_finding_content(finding):
    priority = finding.get('priority', 'N/A')
    p_class = {"高": "high", "中": "medium", "低": "low"}.get(priority, "")
    st.markdown(f"**指摘箇所: {finding.get('location', 'N/A')}** <span class='priority-badge priority-{p_class}'>緊急度: {priority}</span>", unsafe_allow_html=True)
    st.markdown(f"- **現状:** {finding.get('current_state', 'N/A')}")
    st.markdown(f"- **提案工事:** {finding.get('suggested_work', 'N/A')}")
    if finding.get('notes'):
        st.markdown(f"- **備考:** {finding.get('notes', 'N/A')}")

def display_full_report(report_payload, files_dict=None):
    report_data = report_payload.get('report_data', [])
    report_title = report_payload.get('title', '')
    survey_date = report_payload.get('date', '')

    st.markdown('<div class="report-container">', unsafe_allow_html=True)
    
    st.markdown(f"<h1>現場分析レポート</h1>", unsafe_allow_html=True)
    c1, c2 = st.columns(2); c1.markdown(f"**物件名・案件名:**<br>{report_title or '（未設定）'}", unsafe_allow_html=True); c2.markdown(f"**調査日:**<br>{survey_date}", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>📊 分析結果サマリー</h2>", unsafe_allow_html=True)
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    m1, m2, m3 = st.columns(3); m1.metric("分析写真枚数", f"{len(report_data)} 枚"); m2.metric("総指摘件数", f"{total_findings} 件"); m3.metric("緊急度「高」の件数", f"{high_priority_count} 件")
    st.markdown("<hr>", unsafe_allow_html=True)
    
    st.markdown("<h2>📋 詳細分析結果</h2>", unsafe_allow_html=True)
    for i, item in enumerate(report_data):
        st.markdown('<div class="photo-section">', unsafe_allow_html=True)
        st.markdown(f"<h3>{i + 1}. 写真ファイル: {item.get('file_name', '')}</h3>", unsafe_allow_html=True)
        
        has_image = files_dict and item.get('file_name') in files_dict
        col1, col2 = st.columns([2, 3])
        
        with col1:
            if has_image:
                st.image(files_dict[item['file_name']], use_container_width=True)
            else:
                st.empty()
        
        with col2:
            findings = item.get("findings", [])
            if findings:
                for finding in findings:
                    display_finding_content(finding)
            elif item.get("observation"):
                st.info(f"**【AIによる所見】**\n\n{item['observation']}")
            else:
                st.success("✅ 特に修繕が必要な箇所は見つかりませんでした。")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------------------------------------------------
# 5. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    inject_custom_css()
    model = initialize_vertexai()

    if "report" in st.query_params:
        report_payload = decode_report_data(st.query_params["report"])
        if report_payload:
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            st.success("レポート表示中（共有モード）")
            st.info("このページのURLを他者に共有できます。ブラウザの印刷機能（Ctrl+P）でPDF化してください。")
            if st.button("新しいレポートを作成する", key="new_from_shared"):
                st.session_state.clear()
                st.query_params.clear()
            st.markdown('</div>', unsafe_allow_html=True)
            display_full_report(report_payload)
        else:
            st.error("レポートのURLが無効です。")
            if st.button("ホームに戻る"): st.query_params.clear()
        return

    # --- レポート作成画面 ---
    st.markdown('<div class="no-print">', unsafe_allow_html=True)
    if 'processing' not in st.session_state:
        st.session_state.processing = False

    # レポート作成中は何もしない
    if st.session_state.processing:
        return

    st.title("📷 AIリフォーム箇所分析＆報告書作成")
    st.markdown("現場写真をアップロードすると、AIがクライアント向けの修繕提案レポートを自動作成します。")

    if not model:
        st.warning("AIモデルを読み込めませんでした。"); st.stop()
    
    with st.form("report_form"):
        st.subheader("1. レポート情報入力")
        report_title = st.text_input("物件名・案件名", "（例）〇〇ビル 301号室 原状回復工事")
        survey_date = st.date_input("調査日", date.today())
        
        st.subheader("2. 写真アップロード")
        uploaded_files = st.file_uploader(
            "分析したい写真を選択",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="file_uploader"
        )
        
        # ★アップロード状況の表示
        if uploaded_files:
            st.success(f"{len(uploaded_files)}件の写真がアップロードされました。")
        else:
            st.info("ここに写真をドラッグ＆ドロップするか、「Browse files」ボタンを押して選択してください。")
        
        submitted = st.form_submit_button(
            "レポートを作成する",
            type="primary",
            use_container_width=True,
            disabled=not uploaded_files # ★ファイルがなければ非活性
        )

    if submitted:
        st.session_state.processing = True
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
                    st.error(f"バッチ {current_batch_num} の分析中にエラーが発生しました。このバッチはスキップされます。")
            
            progress_bar.progress(1.0, text="分析完了！レポートを生成中です...")
            
            st.session_state.files_dict = {f.name: f for f in uploaded_files}
            report_payload = {
                "title": report_title,
                "date": survey_date.strftime('%Y年%m月%d日'),
                "report_data": final_report_data
            }
            
            st.session_state.report_payload = report_payload
            st.query_params["report"] = encode_report_data(report_payload)
            
        except Exception as e:
            st.error(f"分析処理全体で予期せぬエラーが発生しました: {e}")
        finally:
            st.session_state.processing = False
            progress_bar.empty()
            st.rerun() # 結果表示のために再描画

    # セッションにレポートデータがあれば表示
    if 'report_payload' in st.session_state:
        st.info("💡 レポートをPDFとして保存するには、ブラウザの印刷機能（Ctrl+P または Cmd+P）を使用してください。")
        st.info("ℹ️ このページのURLを共有すると、テキストのみのレポートが相手に表示されます。")
        display_full_report(st.session_state.report_payload, st.session_state.files_dict)
        
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
