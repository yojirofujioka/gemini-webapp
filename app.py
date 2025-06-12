import streamlit as st
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
        /* Streamlitのデフォルト要素を強制的に非表示（印刷時） */
        @media print {
            /* Streamlitの全ての要素を非表示 */
            .stApp > header,
            .stApp > footer,
            header[data-testid="stHeader"],
            div[data-testid="stToolbar"],
            div[data-testid="stDecoration"],
            div[data-testid="stStatusWidget"],
            section[data-testid="stSidebar"],
            div[data-testid="collapsedControl"],
            button,
            .stButton,
            .stDownloadButton,
            .element-container:has(button),
            .row-widget.stButton,
            iframe,
            .stAlert,
            .stInfo,
            .stSuccess,
            .stWarning,
            .stError,
            .stException,
            .st-emotion-cache-1y4p8pa,
            .st-emotion-cache-16idsys,
            .st-emotion-cache-1dp5vir,
            .viewerBadge_container__1QSob,
            .styles_viewerBadge__1yB5_,
            .main > .block-container > div > div > div:not(.report-wrapper),
            .stMarkdown:not(.report-content),
            div:has(> .stButton),
            div:has(> button) {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                width: 0 !important;
                opacity: 0 !important;
                overflow: hidden !important;
                position: absolute !important;
                left: -9999px !important;
            }
            
            /* レポートコンテナ以外を非表示 */
            .main .block-container > div > div > div {
                display: none !important;
            }
            
            /* レポートラッパーのみ表示 */
            .report-wrapper {
                display: block !important;
                visibility: visible !important;
                position: static !important;
                opacity: 1 !important;
                width: 100% !important;
                height: auto !important;
                left: auto !important;
            }
            
            /* 印刷時のページ設定 */
            @page {
                size: A4;
                margin: 10mm 15mm;
            }
            
            /* body要素の設定 */
            html, body {
                background: white !important;
                background-color: white !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: visible !important;
                height: auto !important;
            }
            
            /* メインコンテナのパディングを削除 */
            .main, .main > .block-container {
                padding: 0 !important;
                margin: 0 !important;
                max-width: 100% !important;
                overflow: visible !important;
            }
            
            /* レポートコンテナの印刷設定 */
            .report-container {
                background: white !important;
                box-shadow: none !important;
                border: none !important;
                padding: 0 !important;
                margin: 0 !important;
                width: 100% !important;
                display: block !important;
                page-break-inside: auto !important;
            }
            
            /* 写真セクションのページ分割防止 */
            .photo-section {
                page-break-inside: avoid !important;
                break-inside: avoid !important;
                display: block !important;
                margin: 15px 0 !important;
                padding: 15px 0 !important;
                width: 100% !important;
            }
            
            .photo-content-wrapper {
                page-break-inside: avoid !important;
                break-inside: avoid !important;
                display: flex !important;
                width: 100% !important;
            }
            
            /* 写真のサイズ調整 */
            .photo-column {
                width: 35% !important;
                max-width: 35% !important;
            }
            
            .content-column {
                width: 65% !important;
                padding-left: 20px !important;
            }
            
            .photo-image {
                max-height: 200px !important;
                width: auto !important;
                height: auto !important;
            }
        }
        
        /* 通常表示時のスタイル */
        .report-wrapper {
            width: 100%;
        }
        
        .report-content {
            width: 100%;
        }
        
        .report-container { 
            background-color: #ffffff; 
            color: #333333; 
            border-radius: 8px; 
            border: 1px solid #e0e0e0; 
            padding: 2.5em 3.5em; 
            box-shadow: 0 8px 30px rgba(0,0,0,0.05); 
            margin: 2em 0; 
        }
        
        .report-container h1 { 
            color: #1F2937; 
            font-size: 2.5em; 
            border-bottom: 3px solid #D1D5DB; 
            padding-bottom: 0.4em; 
            margin-bottom: 1em;
        }
        
        .report-container h2 { 
            color: #1F2937; 
            font-size: 1.8em; 
            border-bottom: 2px solid #E5E7EB; 
            padding-bottom: 0.3em; 
            margin-top: 2em; 
            margin-bottom: 1em;
        }
        
        .report-container hr { 
            border: 1px solid #e0e0e0; 
            margin: 2.5em 0; 
        }
        
        /* 写真セクションのスタイル（コンパクト版） */
        .photo-section { 
            margin: 1.5rem 0;
            padding: 1.5rem 0;
            border-top: 1px solid #e0e0e0;
            page-break-inside: avoid;
            break-inside: avoid;
        }
        
        .report-container .photo-section:first-of-type { 
            border-top: none; 
            padding-top: 0; 
            margin-top: 0; 
        }
        
        /* 写真とコンテンツのレイアウト（コンパクト版） */
        .photo-content-wrapper {
            display: flex;
            gap: 1.5rem;
            align-items: flex-start;
            page-break-inside: avoid;
            break-inside: avoid;
        }
        
        .photo-column {
            flex: 0 0 30%;
            max-width: 30%;
        }
        
        .content-column {
            flex: 1;
            min-width: 0;
        }
        
        /* タイトルを右側に配置 */
        .section-title { 
            color: #374151; 
            font-size: 1.2em; 
            margin: 0 0 0.8em 0; 
            font-weight: 600;
            page-break-after: avoid;
            break-after: avoid;
        }
        
        .photo-image {
            width: 100%;
            max-height: 250px;
            object-fit: contain;
            display: block;
            page-break-inside: avoid;
            break-inside: avoid;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
        }
        
        .finding-item {
            margin-bottom: 1rem;
            page-break-inside: avoid;
            break-inside: avoid;
            font-size: 0.95em;
        }
        
        .finding-item ul {
            margin: 0.3em 0 0 0;
            padding-left: 1.5em;
        }
        
        .finding-item li {
            margin-bottom: 0.3em;
        }
        
        .priority-badge { 
            display: inline-block; 
            padding: 0.25em 0.7em; 
            border-radius: 12px; 
            font-weight: 600; 
            color: white; 
            font-size: 0.85em; 
            margin-left: 8px; 
        }
        
        .priority-high { background-color: #DC2626; }
        .priority-medium { background-color: #F59E0B; }
        .priority-low { background-color: #3B82F6; }
        
        /* 情報ボックスのスタイル */
        .info-box {
            background-color: #D1FAE5; 
            padding: 0.8em; 
            border-radius: 6px; 
            margin-top: 0;
            font-size: 0.95em;
        }
        
        .success-box {
            background-color: #D1FAE5; 
            padding: 0.8em; 
            border-radius: 6px; 
            margin-top: 0;
            font-size: 0.95em;
        }
        
        /* メトリクスのスタイル */
        .metrics-container {
            display: flex; 
            justify-content: space-around; 
            margin: 2em 0;
        }
        
        .metric-item {
            text-align: center;
        }
        
        .metric-value {
            font-size: 2em; 
            font-weight: bold; 
            color: #1F2937;
        }
        
        .metric-label {
            color: #6B7280;
            margin-top: 0.3em;
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
def display_finding_content_html(finding):
    """指摘事項をHTML形式で返す"""
    priority = finding.get('priority', 'N/A')
    p_class = {"高": "high", "中": "medium", "低": "low"}.get(priority, "")
    
    html = f"""
    <div class="finding-item">
        <p style="margin-bottom: 0.5em;"><strong>指摘箇所: {finding.get('location', 'N/A')}</strong> 
        <span class='priority-badge priority-{p_class}'>緊急度: {priority}</span></p>
        <ul>
            <li><strong>現状:</strong> {finding.get('current_state', 'N/A')}</li>
            <li><strong>提案工事:</strong> {finding.get('suggested_work', 'N/A')}</li>
    """
    
    if finding.get('notes'):
        html += f"<li><strong>備考:</strong> {finding.get('notes', 'N/A')}</li>"
    
    html += "</ul></div>"
    return html

def display_full_report(report_payload, files_dict):
    report_data = report_payload.get('report_data', [])
    report_title = report_payload.get('title', '')
    survey_date = report_payload.get('date', '')

    # レポート全体をラップする要素を追加
    st.markdown('<div class="report-wrapper">', unsafe_allow_html=True)
    st.markdown('<div class="report-content">', unsafe_allow_html=True)
    st.markdown('<div class="report-container">', unsafe_allow_html=True)
    
    # ヘッダー部分
    st.markdown(f"<h1>現場分析レポート</h1>", unsafe_allow_html=True)
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; margin-bottom: 2em;">
            <div><strong>物件名・案件名:</strong><br>{report_title or '（未設定）'}</div>
            <div><strong>調査日:</strong><br>{survey_date}</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # サマリー部分
    st.markdown("<h2>📊 分析結果サマリー</h2>", unsafe_allow_html=True)
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    
    st.markdown(f"""
        <div class="metrics-container">
            <div class="metric-item">
                <div class="metric-value">{len(report_data)} 枚</div>
                <div class="metric-label">分析写真枚数</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">{total_findings} 件</div>
                <div class="metric-label">総指摘件数</div>
            </div>
            <div class="metric-item">
                <div class="metric-value" style="color: #DC2626;">{high_priority_count} 件</div>
                <div class="metric-label">緊急度「高」の件数</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # 詳細分析結果
    st.markdown("<h2>📋 詳細分析結果</h2>", unsafe_allow_html=True)
    
    for i, item in enumerate(report_data):
        st.markdown(f'<div class="photo-section">', unsafe_allow_html=True)
        st.markdown('<div class="photo-content-wrapper">', unsafe_allow_html=True)
        
        # 写真カラム
        st.markdown('<div class="photo-column">', unsafe_allow_html=True)
        if files_dict and item.get('file_name') in files_dict:
            # 画像をbase64エンコードして埋め込む
            file_obj = files_dict[item['file_name']]
            file_obj.seek(0)
            img_data = file_obj.read()
            img_base64 = base64.b64encode(img_data).decode()
            
            st.markdown(f'<img src="data:image/jpeg;base64,{img_base64}" class="photo-image" alt="{item.get("file_name", "")}">', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # コンテンツカラム（タイトルを含む）
        st.markdown('<div class="content-column">', unsafe_allow_html=True)
        
        # タイトルを右側に配置
        st.markdown(f'<h3 class="section-title">{i + 1}. {item.get("file_name", "")}</h3>', unsafe_allow_html=True)
        
        findings = item.get("findings", [])
        if findings:
            for finding in findings:
                st.markdown(display_finding_content_html(finding), unsafe_allow_html=True)
        elif item.get("observation"):
            st.markdown(f'<div class="info-box"><strong>【AIによる所見】</strong><br>{item["observation"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="success-box">✅ 特に修繕が必要な箇所は見つかりませんでした。</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)  # content-column
        st.markdown('</div>', unsafe_allow_html=True)  # photo-content-wrapper
        st.markdown('</div>', unsafe_allow_html=True)  # photo-section
    
    st.markdown('</div>', unsafe_allow_html=True)  # report-container
    st.markdown('</div>', unsafe_allow_html=True)  # report-content
    st.markdown('</div>', unsafe_allow_html=True)  # report-wrapper

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
            # セッションをクリアして初期画面に戻る
            st.session_state.clear()
            st.rerun()
        
        display_full_report(st.session_state.report_payload, st.session_state.files_dict)
        return

    # --- 状態2: 初期画面（入力フォーム） ---
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
    
    # ★ 処理中はボタンを無効化
    is_processing = st.session_state.get('processing', False)
    submitted = st.button(
        "レポートを作成する",
        type="primary",
        use_container_width=True,
        disabled=not uploaded_files or is_processing
    )

    if submitted:
        st.session_state.processing = True
        
        # UIをクリアし、プログレスバーを表示
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
