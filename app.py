import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account
from datetime import date
import math
from PIL import Image
import io
import html
import base64

# ----------------------------------------------------------------------
# 1. 設定と定数
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="AIリフォーム箇所分析レポート",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed"  # サイドバーを最初から非表示
)
BATCH_SIZE = 10 # 一度にAIに送信する写真の枚数

# セッション状態の初期化
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'report_payload' not in st.session_state:
    st.session_state.report_payload = None
if 'files_dict' not in st.session_state:
    st.session_state.files_dict = None
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False
if 'edited_report' not in st.session_state:
    st.session_state.edited_report = None

# ----------------------------------------------------------------------
# 2. デザインとGCP初期化
# ----------------------------------------------------------------------
def inject_custom_css():
    """印刷用のカスタムCSSを注入する。"""
    st.markdown("""
    <style>
        /* ========== グローバルテーマ設定 ========== */
        /* Streamlitのダークモードを完全に無効化 */
        :root {
            color-scheme: light !important;
        }
        
        /* アプリ全体の背景を白に */
        html, body, .stApp, [data-testid="stAppViewContainer"], .main {
            background-color: #ffffff !important;
            color: #1f2937 !important;
        }
        
        /* ========== テキスト要素のスタイル ========== */
        /* すべての見出し */
        h1, h2, h3, h4, h5, h6,
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
            color: #1f2937 !important;
        }
        
        /* 段落とスパン */
        p, span, label, .stMarkdown, .stText {
            color: #374151 !important;
        }
        
        /* ========== 入力要素のスタイル ========== */
        /* テキスト入力のラベル */
        [data-testid="stTextInput"] label,
        [data-testid="stDateInput"] label,
        [data-testid="stFileUploader"] label,
        .stTextInput label,
        .stDateInput label,
        .stFileUploader label {
            color: #1f2937 !important;
            font-weight: 600 !important;
            opacity: 1 !important;
        }
        
        /* テキスト入力フィールド */
        [data-testid="stTextInput"] input,
        .stTextInput input {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 1px solid #d1d5db !important;
        }
        
        /* 日付入力フィールド */
        [data-testid="stDateInput"] input,
        .stDateInput input {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 1px solid #d1d5db !important;
        }
        
        /* ファイルアップローダー */
        [data-testid="stFileUploadDropzone"],
        .stFileUploader > div {
            background-color: #f9fafb !important;
            border: 2px dashed #d1d5db !important;
        }
        
        [data-testid="stFileUploadDropzone"] svg {
            color: #6b7280 !important;
        }
        
        [data-testid="stFileUploadDropzone"] p,
        [data-testid="stFileUploadDropzone"] span {
            color: #4b5563 !important;
        }
        
        /* ========== ボタンのスタイル ========== */
        .stButton > button {
            background-color: #3b82f6 !important;
            color: #ffffff !important;
            border: none !important;
            font-weight: 600 !important;
        }
        
        .stButton > button:hover:not(:disabled) {
            background-color: #2563eb !important;
        }
        
        .stButton > button:disabled {
            background-color: #9ca3af !important;
            opacity: 0.6 !important;
        }
        
        /* ========== アラートメッセージ ========== */
        /* 成功メッセージ */
        .stSuccess, [data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
            background-color: #d1fae5 !important;
            color: #065f46 !important;
        }
        
        .stSuccess svg {
            color: #10b981 !important;
        }
        
        /* 警告メッセージ */
        .stWarning, [data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
            background-color: #fef3c7 !important;
            color: #92400e !important;
        }
        
        .stWarning svg {
            color: #f59e0b !important;
        }
        
        /* 情報メッセージ */
        .stInfo, [data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
            background-color: #dbeafe !important;
            color: #1e3a8a !important;
        }
        
        .stInfo svg {
            color: #3b82f6 !important;
        }
        
        /* ========== プログレスバー ========== */
        .stProgress > div > div {
            background-color: #e5e7eb !important;
        }
        
        .stProgress > div > div > div {
            background-color: #3b82f6 !important;
        }
        
        /* ========== カスタムスタイル ========== */
        /* 基本スタイル */
        .report-header {
            text-align: center;
            padding: 2rem 0;
            border-bottom: 3px solid #1F2937;
            margin-bottom: 2rem;
            background: #ffffff;
        }
        
        /* 印刷ガイダンス */
        .print-guidance {
            background: #fef3c7;
            border: 2px solid #f59e0b;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 2rem;
            text-align: center;
        }
        
        .print-guidance strong {
            color: #d97706;
            font-size: 1.1rem;
        }
        
        /* サマリーカード */
        .metric-card {
            background: #ffffff;
            border: 2px solid #d1d5db;
            padding: 1.5rem;
            border-radius: 8px;
            text-align: center;
            height: 100%;
        }
        
        .metric-value {
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            color: #1f2937;
        }
        
        .metric-value-high {
            color: #dc2626;
        }
        
        .metric-label {
            font-size: 1rem;
            color: #4b5563;
            font-weight: 600;
        }
        
        /* 写真セクション（横並びレイアウト） */
        .photo-row {
            display: flex;
            gap: 1.5rem;
            margin-bottom: 2rem;
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            padding: 1.5rem;
            page-break-inside: avoid;
            break-inside: avoid;
        }
        
        .photo-container {
            flex: 0 0 300px;
            max-width: 300px;
        }
        
        .photo-img {
            width: 100%;
            height: auto;
            max-height: 225px;
            object-fit: contain;
            border-radius: 8px;
            border: 2px solid #d1d5db;
            background: #f9fafb;
        }
        
        .content-container {
            flex: 1;
            min-width: 0;
            padding-left: 1rem;
        }
        
        .photo-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 0.8rem;
        }
        
        /* 指摘事項のスタイル */
        .finding-high {
            background: #fee2e2;
            border-left: 3px solid #dc2626;
            padding: 0.6rem;
            margin-bottom: 0.6rem;
            border-radius: 6px;
            color: #7f1d1d;
            font-size: 0.85rem;
        }
        
        .finding-medium {
            background: #fef3c7;
            border-left: 3px solid #f59e0b;
            padding: 0.6rem;
            margin-bottom: 0.6rem;
            border-radius: 6px;
            color: #78350f;
            font-size: 0.85rem;
        }
        
        .finding-low {
            background: #dbeafe;
            border-left: 3px solid #3b82f6;
            padding: 0.6rem;
            margin-bottom: 0.6rem;
            border-radius: 6px;
            color: #1e3a8a;
            font-size: 0.85rem;
        }
        
        .finding-location {
            font-weight: 600;
            margin-bottom: 0.3rem;
        }
        
        .finding-details {
            line-height: 1.4;
        }
        
        .observation-box {
            background: #d1fae5;
            padding: 0.8rem;
            border-radius: 8px;
            color: #064e3b;
            font-size: 0.85rem;
        }
        
        .no-finding-box {
            background: #d1fae5;
            color: #047857;
            padding: 0.8rem;
            text-align: center;
            border-radius: 8px;
            font-size: 0.85rem;
        }
        
        /* 編集エリアのスタイル */
        .edit-container {
            background: #f9fafb;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            border: 1px solid #e5e7eb;
        }
        
        /* ========== 印刷用スタイル ========== */
        @media print {
            /* 背景を白に設定 */
            body, .stApp {
                background: white !important;
                background-color: white !important;
            }
            
            /* Streamlitの要素を非表示 */
            header[data-testid="stHeader"],
            [data-testid="stToolbar"],
            .stAlert,
            .stProgress,
            .stInfo,
            .stSuccess,
            .print-guidance,
            button,
            [data-testid="column"]:has(button),
            .stCaption,
            .st-emotion-cache-1wrcr25,
            .st-emotion-cache-12w0qpk,
            footer,
            .edit-container,
            .stTextInput,
            .stTextArea,
            .stSelectbox {
                display: none !important;
            }
            
            /* メインコンテンツの背景を白に */
            .main, .block-container, section.main > div {
                background: white !important;
                background-color: white !important;
            }
            
            /* ページ設定 */
            @page {
                size: A4;
                margin: 15mm;
            }
            
            /* タイトルとヘッダー */
            .report-header {
                border-bottom: 2px solid #333 !important;
                background: white !important;
            }
            
            h1, h2, h3 {
                color: #000 !important;
                page-break-after: avoid !important;
            }
            
            /* サマリーカード */
            .metric-card {
                background: white !important;
                border: 1px solid #333 !important;
                page-break-inside: avoid !important;
            }
            
            .metric-value {
                color: #000 !important;
            }
            
            .metric-value-high {
                color: #dc2626 !important;
            }
            
            /* 写真行の印刷設定 */
            .photo-row {
                page-break-inside: avoid !important;
                margin-bottom: 15px !important;
                padding: 15px !important;
                background: white !important;
                border: 1px solid #333 !important;
            }
            
            /* 写真のサイズ調整 */
            .photo-container {
                flex: 0 0 200px !important;
                max-width: 200px !important;
            }
            
            .photo-img {
                max-height: 150px !important;
                border: 1px solid #333 !important;
            }
            
            /* テキストスタイル */
            .photo-title {
                font-size: 0.9rem !important;
                color: #000 !important;
            }
            
            .finding-high {
                background: #fee2e2 !important;
                border-left: 3px solid #dc2626 !important;
                color: #7f1d1d !important;
            }
            
            .finding-medium {
                background: #fef3c7 !important;
                border-left: 3px solid #f59e0b !important;
                color: #78350f !important;
            }
            
            .finding-low {
                background: #dbeafe !important;
                border-left: 3px solid #3b82f6 !important;
                color: #1e3a8a !important;
            }
            
            .observation-box {
                background: #d1fae5 !important;
                color: #064e3b !important;
            }
            
            .no-finding-box {
                background: #d1fae5 !important;
                color: #047857 !important;
            }
            
            .finding-details {
                font-size: 0.7rem !important;
            }
            
            /* 全ての要素の背景を白に */
            * {
                background-color: transparent !important;
            }
            
            /* ベースの背景を白に */
            html, body {
                background: white !important;
                background-color: white !important;
            }
        }
        
        /* Ctrl+Pを無効化 */
        @media screen {
            body {
                -webkit-user-select: text;
                -moz-user-select: text;
                -ms-user-select: text;
                user-select: text;
            }
        }
    </style>
    
    <script>
        // Ctrl+P / Cmd+Pを無効化
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
                e.preventDefault();
                alert('PDFとして保存するには、画面右上の「⋮」メニューから「Print」を選択してください。');
                return false;
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
def optimize_image_for_display(file_obj, max_width=800):
    """画像を最適化してbase64エンコード"""
    try:
        file_obj.seek(0)
        img = Image.open(file_obj)
        
        # 画像が大きすぎる場合はリサイズ
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        # JPEGに変換して圧縮
        output = io.BytesIO()
        img = img.convert('RGB') if img.mode != 'RGB' else img
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        return base64.b64encode(output.read()).decode()
    except Exception as e:
        st.warning(f"画像の最適化中にエラーが発生しました: {e}")
        file_obj.seek(0)
        return base64.b64encode(file_obj.read()).decode()

def create_photo_row_html(index, item, img_base64=None):
    """写真と内容を横並びで表示するHTML（読み取り専用）"""
    file_name = html.escape(str(item.get('file_name', '')))
    findings = item.get("findings", [])
    
    # 写真部分（遅延読み込み対応）
    photo_html = f'<img src="data:image/jpeg;base64,{img_base64}" class="photo-img" loading="lazy">' if img_base64 else '<div style="height: 150px; background: #f3f4f6; display: flex; align-items: center; justify-content: center; border-radius: 8px;">画像なし</div>'
    
    # コンテンツ部分のHTML生成
    content_html = f'<div class="photo-title">{index}. {file_name}</div>'
    
    if findings:
        for finding in findings:
            priority = finding.get('priority', '中')
            priority_class = {
                '高': 'finding-high',
                '中': 'finding-medium',
                '低': 'finding-low'
            }.get(priority, 'finding-medium')
            
            priority_emoji = {
                '高': '🔴',
                '中': '🟡', 
                '低': '🔵'
            }.get(priority, '🟡')
            
            location = html.escape(str(finding.get('location', 'N/A')))
            current_state = html.escape(str(finding.get('current_state', 'N/A')))
            suggested_work = html.escape(str(finding.get('suggested_work', 'N/A')))
            
            content_html += f'''
            <div class="{priority_class}">
                <div class="finding-location">{priority_emoji} {location} (緊急度: {priority})</div>
                <div class="finding-details">
                    <div>現状: {current_state}</div>
                    <div>提案: {suggested_work}</div>
            '''
            
            if finding.get('notes'):
                notes = html.escape(str(finding.get('notes', '')))
                content_html += f'<div>備考: {notes}</div>'
            
            content_html += '</div></div>'
    elif item.get("observation"):
        observation = html.escape(str(item.get('observation', '')))
        content_html += f'<div class="observation-box">📋 所見: {observation}</div>'
    else:
        content_html += '<div class="no-finding-box">✅ 修繕必要箇所なし</div>'
    
    # 全体のHTML
    return f'''
    <div class="photo-row">
        <div class="photo-container">
            {photo_html}
        </div>
        <div class="content-container">
            {content_html}
        </div>
    </div>
    '''

def display_editable_report(report_payload, files_dict):
    """編集可能なレポート表示"""
    # 編集用データの初期化
    if st.session_state.edited_report is None:
        st.session_state.edited_report = json.loads(json.dumps(report_payload))
    
    report_data = st.session_state.edited_report.get('report_data', [])
    report_title = st.session_state.edited_report.get('title', '')
    survey_date = st.session_state.edited_report.get('date', '')
    
    # ヘッダー
    st.markdown('<div class="report-header">', unsafe_allow_html=True)
    st.title("🏠 現場分析レポート")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**物件名:** {report_title or '（未設定）'}")
    with col2:
        st.markdown(f"**調査日:** {survey_date}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # サマリー計算
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    
    # サマリー表示
    st.header("📊 分析結果サマリー")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'''
            <div class="metric-card">
                <div class="metric-value">{len(report_data)}</div>
                <div class="metric-label">分析写真枚数</div>
            </div>
        ''', unsafe_allow_html=True)
    
    with col2:
        st.markdown(f'''
            <div class="metric-card">
                <div class="metric-value">{total_findings}</div>
                <div class="metric-label">総指摘件数</div>
            </div>
        ''', unsafe_allow_html=True)
    
    with col3:
        st.markdown(f'''
            <div class="metric-card">
                <div class="metric-value metric-value-high">{high_priority_count}</div>
                <div class="metric-label">緊急度「高」</div>
            </div>
        ''', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 詳細分析結果（編集可能）
    st.header("📋 詳細分析結果")
    
    # 各写真を編集可能な形で表示
    for i, item in enumerate(report_data):
        with st.container():
            # 写真と基本情報の表示
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # 写真表示
                if files_dict and item.get('file_name') in files_dict:
                    try:
                        file_obj = files_dict[item['file_name']]
                        img_base64 = optimize_image_for_display(file_obj)
                        st.markdown(f'<img src="data:image/jpeg;base64,{img_base64}" class="photo-img">', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"画像の表示エラー: {str(e)}")
                        st.info("画像を表示できません")
                else:
                    st.info("画像なし")
                st.caption(f"{i + 1}. {item.get('file_name', '')}")
            
            with col2:
                findings = item.get("findings", [])
                
                if findings:
                    # 指摘事項の編集
                    findings_to_delete = []
                    for j, finding in enumerate(findings):
                        with st.expander(f"指摘事項 {j + 1}: {finding.get('location', '')} ({finding.get('priority', '中')})", expanded=True):
                            # 場所
                            new_location = st.text_input(
                                "場所",
                                value=finding.get('location', ''),
                                key=f"location_{i}_{j}"
                            )
                            
                            # 現状
                            new_current_state = st.text_area(
                                "現状",
                                value=finding.get('current_state', ''),
                                key=f"current_{i}_{j}",
                                height=80
                            )
                            
                            # 提案
                            new_suggested_work = st.text_area(
                                "提案する工事内容",
                                value=finding.get('suggested_work', ''),
                                key=f"suggest_{i}_{j}",
                                height=80
                            )
                            
                            # 緊急度
                            priority_options = ['高', '中', '低']
                            try:
                                current_priority = finding.get('priority', '中')
                                if current_priority not in priority_options:
                                    current_priority = '中'
                                current_priority_index = priority_options.index(current_priority)
                            except ValueError:
                                current_priority_index = 1  # デフォルトは'中'
                                
                            new_priority = st.selectbox(
                                "緊急度",
                                options=priority_options,
                                index=current_priority_index,
                                key=f"priority_{i}_{j}"
                            )
                            
                            # 備考
                            new_notes = st.text_area(
                                "備考",
                                value=finding.get('notes', ''),
                                key=f"notes_{i}_{j}",
                                height=60
                            )
                            
                            # 削除ボタン
                            if st.button(f"🗑️ この指摘事項を削除", key=f"delete_{i}_{j}"):
                                findings_to_delete.append(j)
                            
                            # データ更新（リアルタイムで更新しない）
                            finding['location'] = new_location
                            finding['current_state'] = new_current_state
                            finding['suggested_work'] = new_suggested_work
                            finding['priority'] = new_priority
                            finding['notes'] = new_notes
                    
                    # 削除処理
                    for idx in reversed(findings_to_delete):
                        st.session_state.edited_report['report_data'][i]['findings'].pop(idx)
                        st.rerun()
                    
                    # 新規指摘事項追加ボタン
                    if st.button(f"➕ 指摘事項を追加", key=f"add_finding_{i}"):
                        if 'findings' not in st.session_state.edited_report['report_data'][i]:
                            st.session_state.edited_report['report_data'][i]['findings'] = []
                        st.session_state.edited_report['report_data'][i]['findings'].append({
                            'location': '',
                            'current_state': '',
                            'suggested_work': '',
                            'priority': '中',
                            'notes': ''
                        })
                        st.rerun()
                
                elif item.get("observation"):
                    # 所見の編集
                    new_observation = st.text_area(
                        "所見",
                        value=item.get('observation', ''),
                        key=f"observation_{i}",
                        height=100
                    )
                    st.session_state.edited_report['report_data'][i]['observation'] = new_observation
                    
                    # 指摘事項に変更ボタン
                    if st.button(f"🔄 指摘事項に変更", key=f"convert_{i}"):
                        st.session_state.edited_report['report_data'][i]['observation'] = ''
                        st.session_state.edited_report['report_data'][i]['findings'] = [{
                            'location': '',
                            'current_state': '',
                            'suggested_work': '',
                            'priority': '中',
                            'notes': ''
                        }]
                        st.rerun()
                else:
                    st.info("✅ 修繕必要箇所なし")
                    if st.button(f"➕ 指摘事項を追加", key=f"add_new_{i}"):
                        if 'findings' not in st.session_state.edited_report['report_data'][i]:
                            st.session_state.edited_report['report_data'][i]['findings'] = []
                        st.session_state.edited_report['report_data'][i]['findings'].append({
                            'location': '',
                            'current_state': '',
                            'suggested_work': '',
                            'priority': '中',
                            'notes': ''
                        })
                        st.rerun()
            
            st.markdown("---")

def display_full_report(report_payload, files_dict):
    """読み取り専用のレポート表示（既存の関数）"""
    report_data = report_payload.get('report_data', [])
    report_title = report_payload.get('title', '')
    survey_date = report_payload.get('date', '')
    
    # ヘッダー
    st.markdown('<div class="report-header">', unsafe_allow_html=True)
    st.title("🏠 現場分析レポート")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**物件名:** {report_title or '（未設定）'}")
    with col2:
        st.markdown(f"**調査日:** {survey_date}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # サマリー
    st.header("📊 分析結果サマリー")
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'''
            <div class="metric-card">
                <div class="metric-value">{len(report_data)}</div>
                <div class="metric-label">分析写真枚数</div>
            </div>
        ''', unsafe_allow_html=True)
    
    with col2:
        st.markdown(f'''
            <div class="metric-card">
                <div class="metric-value">{total_findings}</div>
                <div class="metric-label">総指摘件数</div>
            </div>
        ''', unsafe_allow_html=True)
    
    with col3:
        st.markdown(f'''
            <div class="metric-card">
                <div class="metric-value metric-value-high">{high_priority_count}</div>
                <div class="metric-label">緊急度「高」</div>
            </div>
        ''', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 詳細分析結果
    st.header("📋 詳細分析結果")
    
    # プログレスバーで画像処理状況を表示
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 各写真を横並びレイアウトで表示
    for i, item in enumerate(report_data):
        # 進捗状況を更新
        progress = (i + 1) / len(report_data)
        progress_bar.progress(progress)
        status_text.text(f"画像を処理中... ({i + 1}/{len(report_data)})")
        
        img_base64 = None
        if files_dict and item.get('file_name') in files_dict:
            file_obj = files_dict[item['file_name']]
            # 画像を最適化
            img_base64 = optimize_image_for_display(file_obj)
        
        # 横並びの写真行を表示
        photo_row_html = create_photo_row_html(i + 1, item, img_base64)
        st.markdown(photo_row_html, unsafe_allow_html=True)
    
    # プログレスバーを削除
    progress_bar.empty()
    status_text.empty()

# ----------------------------------------------------------------------
# 5. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    # CSSを最初に注入して全体のスタイルを設定
    inject_custom_css()
    
    model = initialize_vertexai()

    # --- 状態1: レポートが生成済み ---
    if st.session_state.report_payload is not None:
        st.success("✅ レポートの作成が完了しました！")
        
        # 編集モードの切り替えボタン
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.session_state.edit_mode:
                if st.button("💾 編集を保存して表示モードへ", key="save_edit", use_container_width=True):
                    # 編集内容を保存
                    st.session_state.report_payload = json.loads(json.dumps(st.session_state.edited_report))
                    st.session_state.edit_mode = False
                    st.rerun()
            else:
                if st.button("✏️ レポートを編集", key="start_edit", use_container_width=True):
                    st.session_state.edit_mode = True
                    st.session_state.edited_report = None  # 編集データをリセット
                    st.rerun()
        
        with col2:
            if st.session_state.edit_mode:
                if st.button("❌ 編集をキャンセル", key="cancel_edit", use_container_width=True):
                    st.session_state.edit_mode = False
                    st.session_state.edited_report = None
                    st.rerun()
        
        with col3:
            if st.button("🔄 新しいレポートを作成", key="new_from_result", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        
        # 印刷ガイダンス（表示モードのみ）
        if not st.session_state.edit_mode:
            st.markdown("""
                <div class="print-guidance">
                    <strong>📄 PDFとして保存する方法：</strong><br>
                    画面右上の「⋮」（3点メニュー）をクリックして、<br>
                    <strong style="font-size: 1.3rem;">「Print」</strong> を選択してください
                </div>
            """, unsafe_allow_html=True)
        
        # レポート表示
        if st.session_state.edit_mode:
            display_editable_report(st.session_state.report_payload, st.session_state.files_dict)
        else:
            display_full_report(st.session_state.report_payload, st.session_state.files_dict)
        return

    # --- 状態2: 初期画面（入力フォーム） ---
    st.title("📷 AIリフォーム箇所分析＆報告書作成")
    st.markdown("現場写真をアップロードすると、AIがクライアント向けの修繕提案レポートを自動作成します。")

    if not model:
        st.warning("AIモデルを読み込めませんでした。")
        st.stop()

    # 処理中の場合、警告メッセージを表示
    if st.session_state.processing:
        st.warning("⏳ 現在処理中です。しばらくお待ちください...")
        
    report_title = st.text_input("物件名・案件名", "（例）〇〇ビル 301号室 原状回復工事", disabled=st.session_state.processing)
    survey_date = st.date_input("調査日", date.today(), disabled=st.session_state.processing)
    
    uploaded_files = st.file_uploader(
        "分析したい写真を選択",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="file_uploader",
        disabled=st.session_state.processing
    )
    
    if uploaded_files and not st.session_state.processing:
        st.success(f"✅ {len(uploaded_files)}件の写真がアップロードされました。")
    
    # ボタンの作成（処理中は無効化）
    button_label = "処理中..." if st.session_state.processing else "レポートを作成する"
    button_disabled = not uploaded_files or st.session_state.processing
    
    submitted = st.button(
        button_label,
        type="primary",
        use_container_width=True,
        disabled=button_disabled,
        key="submit_button"
    )

    if submitted and not st.session_state.processing:
        # 処理開始前に即座にprocessingフラグを設定
        st.session_state.processing = True
        st.rerun()  # 画面を更新してボタンを無効化
        
    # 処理中の場合、実際の処理を実行
    if st.session_state.processing and uploaded_files:
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
                
                # レポートの保存
                st.session_state.files_dict = {f.name: f for f in uploaded_files}
                st.session_state.report_payload = {
                    "title": report_title,
                    "date": survey_date.strftime('%Y年%m月%d日'),
                    "report_data": final_report_data
                }
                
            except Exception as e:
                st.error(f"分析処理全体で予期せぬエラーが発生しました: {e}")
                st.session_state.processing = False
                st.session_state.report_payload = None
            finally:
                # 処理完了後にフラグをリセット
                st.session_state.processing = False
                ui_placeholder.empty()
                st.rerun()

if __name__ == "__main__":
    main()
