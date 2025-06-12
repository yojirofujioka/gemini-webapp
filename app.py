import streamlit as st
import streamlit.components.v1 as components
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account
from datetime import date
import math
import base64
from io import BytesIO

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
        /* 基本スタイル */
        .report-container { 
            background-color: #ffffff; 
            color: #333333; 
            border-radius: 8px; 
            border: 1px solid #e0e0e0; 
            padding: 2em; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.08); 
            margin: 1em auto;
            max-width: 1200px;
        }
        
        .report-header {
            text-align: center;
            border-bottom: 3px solid #1F2937;
            padding-bottom: 1.5em;
            margin-bottom: 2em;
        }
        
        .report-title {
            font-size: 2em;
            color: #1F2937;
            margin-bottom: 0.5em;
            font-weight: bold;
        }
        
        .report-info {
            display: flex;
            justify-content: center;
            gap: 4em;
            margin-top: 1em;
            font-size: 0.95em;
        }
        
        .report-section {
            margin: 2em 0;
        }
        
        .section-title {
            font-size: 1.4em;
            color: #1F2937;
            border-bottom: 2px solid #E5E7EB;
            padding-bottom: 0.5em;
            margin-bottom: 1em;
        }
        
        /* サマリー */
        .summary-container {
            display: flex;
            justify-content: space-around;
            background-color: #F9FAFB;
            border-radius: 8px;
            padding: 1.5em;
            margin-bottom: 2em;
        }
        
        .summary-item {
            text-align: center;
        }
        
        .summary-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #1F2937;
        }
        
        .summary-label {
            color: #6B7280;
            margin-top: 0.3em;
            font-size: 0.9em;
        }
        
        /* 写真レイアウト - グリッド形式 */
        .photos-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1.5em;
            margin-top: 1em;
        }
        
        .photo-item {
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            overflow: hidden;
            background-color: #FFFFFF;
            page-break-inside: avoid;
            break-inside: avoid;
        }
        
        .photo-header {
            background-color: #F9FAFB;
            padding: 0.8em 1em;
            border-bottom: 1px solid #E5E7EB;
            font-weight: 600;
            font-size: 0.95em;
            color: #374151;
        }
        
        .photo-content {
            display: flex;
            padding: 1em;
            gap: 1em;
            align-items: flex-start;
        }
        
        .photo-img-container {
            flex: 0 0 200px;
            max-width: 200px;
        }
        
        .photo-img {
            width: 100%;
            height: 150px;
            object-fit: cover;
            border-radius: 4px;
            border: 1px solid #E5E7EB;
        }
        
        .photo-details {
            flex: 1;
            min-width: 0;
        }
        
        .finding-item {
            margin-bottom: 1em;
            padding: 0.8em;
            background-color: #FEF3C7;
            border-radius: 6px;
            border-left: 4px solid #F59E0B;
            font-size: 0.85em;
        }
        
        .finding-item:last-child {
            margin-bottom: 0;
        }
        
        .finding-location {
            font-weight: 600;
            color: #92400E;
            margin-bottom: 0.3em;
        }
        
        .finding-details {
            margin-left: 0.5em;
            line-height: 1.5;
        }
        
        .priority-high {
            border-left-color: #DC2626;
            background-color: #FEE2E2;
        }
        
        .priority-high .finding-location {
            color: #991B1B;
        }
        
        .priority-low {
            border-left-color: #3B82F6;
            background-color: #DBEAFE;
        }
        
        .priority-low .finding-location {
            color: #1E40AF;
        }
        
        .no-finding {
            color: #059669;
            font-size: 0.9em;
            padding: 0.5em;
        }
        
        .observation {
            background-color: #D1FAE5;
            padding: 0.8em;
            border-radius: 6px;
            font-size: 0.85em;
            color: #065F46;
        }
        
        /* 印刷用スタイル */
        @media print {
            /* Streamlitの要素を完全に隠す */
            body > div:not(.stApp) { display: none !important; }
            .stApp > header { display: none !important; }
            .stApp > div[data-testid="stAppViewContainer"] > .main > footer { display: none !important; }
            div[data-testid="stToolbar"] { display: none !important; }
            div[data-testid="stDecoration"] { display: none !important; }
            div[data-testid="stStatusWidget"] { display: none !important; }
            .st-emotion-cache-1y4p8pa { display: none !important; }
            section[data-testid="stSidebar"] { display: none !important; }
            button { display: none !important; }
            .stButton { display: none !important; }
            .stAlert { display: none !important; }
            
            /* bodyとhtmlの設定 */
            html, body {
                height: auto !important;
                overflow: visible !important;
                background: white !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            
            /* Streamlitのコンテナ設定 */
            .stApp {
                overflow: visible !important;
                height: auto !important;
            }
            
            .main {
                padding: 0 !important;
                margin: 0 !important;
                overflow: visible !important;
            }
            
            .block-container {
                padding: 0 !important;
                margin: 0 !important;
                max-width: 100% !important;
                overflow: visible !important;
            }
            
            /* 印刷専用コンテナのみ表示 */
            #printable-report {
                display: block !important;
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            
            /* レポートコンテナの印刷設定 */
            .report-container {
                box-shadow: none !important;
                border: none !important;
                margin: 0 !important;
                padding: 15mm !important;
                max-width: 100% !important;
                page-break-inside: auto !important;
            }
            
            /* グリッドを1列に変更（印刷時） */
            .photos-grid {
                grid-template-columns: 1fr !important;
                gap: 1em !important;
            }
            
            .photo-item {
                page-break-inside: avoid !important;
                break-inside: avoid !important;
                margin-bottom: 1em !important;
            }
            
            .photo-content {
                display: flex !important;
                gap: 1em !important;
            }
            
            .photo-img-container {
                flex: 0 0 150px !important;
                max-width: 150px !important;
            }
            
            .photo-img {
                height: 120px !important;
            }
            
            /* フォントサイズ調整 */
            .report-title { font-size: 1.8em !important; }
            .section-title { font-size: 1.3em !important; }
            .finding-item { font-size: 0.8em !important; }
            
            @page {
                size: A4;
                margin: 10mm;
            }
        }
        
        /* Streamlitのマージンをリセット */
        .main .block-container {
            padding-top: 1rem;
        }
    </style>
    
    <script>
        // 印刷時に全てのコンテンツを確実に表示する
        window.addEventListener('beforeprint', function() {
            // Streamlitの動的コンテンツを全て展開
            document.querySelectorAll('*').forEach(function(element) {
                if (element.style.display === 'none' || 
                    element.style.visibility === 'hidden' ||
                    element.style.height === '0px' ||
                    element.style.overflow === 'hidden') {
                    // 印刷対象でない要素は除外
                    if (!element.closest('#printable-report')) {
                        element.style.setProperty('display', 'none', 'important');
                    }
                }
            });
            
            // 印刷用コンテナを確実に表示
            const printableReport = document.getElementById('printable-report');
            if (printableReport) {
                printableReport.style.display = 'block';
                printableReport.style.visibility = 'visible';
                printableReport.style.height = 'auto';
                printableReport.style.overflow = 'visible';
            }
        });
    </script>
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
def create_photo_item_html(index, item, img_base64=None):
    """個別の写真アイテムのHTMLを生成"""
    import html
    findings = item.get("findings", [])
    
    # ファイル名をHTMLエスケープ
    file_name = html.escape(item.get('file_name', ''))
    
    photo_html = f"""
    <div class="photo-item">
        <div class="photo-header">{index}. {file_name}</div>
        <div class="photo-content">
    """
    
    # 画像部分
    if img_base64:
        photo_html += f"""
            <div class="photo-img-container">
                <img src="data:image/jpeg;base64,{img_base64}" class="photo-img" alt="{file_name}">
            </div>
        """
    
    # 詳細部分
    photo_html += '<div class="photo-details">'
    
    if findings:
        for finding in findings:
            priority = finding.get('priority', '中')
            priority_class = 'priority-high' if priority == '高' else 'priority-low' if priority == '低' else ''
            
            # 各項目をHTMLエスケープ
            location = html.escape(finding.get('location', 'N/A'))
            current_state = html.escape(finding.get('current_state', 'N/A'))
            suggested_work = html.escape(finding.get('suggested_work', 'N/A'))
            
            photo_html += f"""
            <div class="finding-item {priority_class}">
                <div class="finding-location">📍 {location} (緊急度: {priority})</div>
                <div class="finding-details">
                    <div>状態: {current_state}</div>
                    <div>提案: {suggested_work}</div>
            """
            if finding.get('notes'):
                notes = html.escape(finding.get('notes', ''))
                photo_html += f"<div>備考: {notes}</div>"
            photo_html += "</div></div>"
    elif item.get("observation"):
        observation = html.escape(item.get("observation", ""))
        photo_html += f'<div class="observation">📋 {observation}</div>'
    else:
        photo_html += '<div class="no-finding">✅ 修繕必要箇所なし</div>'
    
    photo_html += '</div></div></div>'
    return photo_html

def display_full_report(report_payload, files_dict):
    import html as html_lib
    
    report_data = report_payload.get('report_data', [])
    report_title = html_lib.escape(report_payload.get('title', ''))
    survey_date = html_lib.escape(report_payload.get('date', ''))
    
    # 統計情報の計算
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    
    # レポートコンテナを開く
    with st.container():
        # CSSスタイルを適用（別途markdownで）
        st.markdown('<div id="printable-report">', unsafe_allow_html=True)
        st.markdown('<div class="report-container">', unsafe_allow_html=True)
        
        # ヘッダー部分
        st.markdown("""
        <div class="report-header">
            <div class="report-title">現場分析レポート</div>
            <div class="report-info">
                <div><strong>物件名:</strong> {}</div>
                <div><strong>調査日:</strong> {}</div>
            </div>
        </div>
        """.format(report_title or '（未設定）', survey_date), unsafe_allow_html=True)
        
        # サマリー部分
        st.markdown("""
        <div class="report-section">
            <h2 class="section-title">📊 分析結果サマリー</h2>
            <div class="summary-container">
                <div class="summary-item">
                    <div class="summary-value">{}</div>
                    <div class="summary-label">分析写真枚数</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{}</div>
                    <div class="summary-label">総指摘件数</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value" style="color: #DC2626;">{}</div>
                    <div class="summary-label">緊急度「高」</div>
                </div>
            </div>
        </div>
        """.format(len(report_data), total_findings, high_priority_count), unsafe_allow_html=True)
        
        # 詳細結果のヘッダー
        st.markdown("""
        <div class="report-section">
            <h2 class="section-title">📋 詳細分析結果</h2>
            <div class="photos-grid">
        """, unsafe_allow_html=True)
        
        # 各写真の処理
        for i, item in enumerate(report_data):
            img_base64 = None
            if files_dict and item.get('file_name') in files_dict:
                file_obj = files_dict[item['file_name']]
                file_obj.seek(0)
                img_data = file_obj.read()
                img_base64 = base64.b64encode(img_data).decode()
            
            # 個別の写真アイテムを表示
            photo_html = create_photo_item_html(i + 1, item, img_base64)
            st.markdown(photo_html, unsafe_allow_html=True)
        
        # クロージングタグ
        st.markdown('</div></div></div></div>', unsafe_allow_html=True)

# ----------------------------------------------------------------------
# 5. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    inject_custom_css()
    model = initialize_vertexai()

    # --- 状態1: レポートが生成済み ---
    if 'report_payload' in st.session_state:
        st.success("✅ レポートの作成が完了しました！")
        st.info("💡 レポートをPDFとして保存するには、ブラウザの印刷機能（Ctrl+P または Cmd+P）を使用してください。")
        if st.button("新しいレポートを作成する", key="new_from_result"):
            st.session_state.clear()
            st.rerun()
        
        display_full_report(st.session_state.report_payload, st.session_state.files_dict)
        return

    # --- 状態2: 初期画面（入力フォーム） ---
    st.title("📷 AIリフォーム箇所分析＆報告書作成")
    st.markdown("現場写真をアップロードすると、AIがクライアント向けの修繕提案レポートを自動作成します。")

    if not model:
        st.warning("AIモデルを読み込めませんでした。")
        st.stop()

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
        
        ui_placeholder = st.empty()
        with ui_placeholder.container():
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
                ui_placeholder.empty()
                st.rerun()

if __name__ == "__main__":
    main()
