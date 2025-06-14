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
    page_title="現場分析レポート",
    page_icon="▪",
    layout="wide",
    initial_sidebar_state="collapsed"
)
BATCH_SIZE = 10

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
# パスワード認証機能
# ----------------------------------------------------------------------
try:
    PASSWORD = st.secrets["PASSWORD"]
except KeyError:
    st.error("パスワードが設定されていません。管理者に連絡してください。")
    st.info("secrets.tomlファイルに'PASSWORD'を設定する必要があります。")
    st.stop()

def check_password():
    def password_entered():
        if st.session_state["password"] == PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    
    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.stop()
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("パスワードが間違っています。")
        st.stop()
    else:
        return True

# ----------------------------------------------------------------------
# 2. デザインとGCP初期化
# ----------------------------------------------------------------------
def inject_custom_css():
    """印刷用のカスタムCSSを注入する。"""
    st.markdown("""
    <style>
        /* ========== グローバルテーマ設定 ========== */
        :root {
            color-scheme: light !important;
        }
        
        html, body, .stApp, [data-testid="stAppViewContainer"], .main {
            background-color: #ffffff !important;
            color: #1f2937 !important;
        }
        
        /* ========== テキスト要素のスタイル ========== */
        h1, h2, h3, h4, h5, h6,
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
            color: #1f2937 !important;
            font-weight: 300 !important;
            letter-spacing: -0.02em !important;
        }
        
        p, span, label, .stMarkdown, .stText {
            color: #374151 !important;
        }
        
        /* ========== 入力要素のスタイル ========== */
        [data-testid="stTextInput"] label,
        [data-testid="stDateInput"] label,
        [data-testid="stFileUploader"] label,
        .stTextInput label,
        .stDateInput label,
        .stFileUploader label {
            color: #1f2937 !important;
            font-weight: 500 !important;
            opacity: 1 !important;
            font-size: 0.875rem !important;
            letter-spacing: 0.05em !important;
        }
        
        [data-testid="stTextInput"] input,
        .stTextInput input {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 0 !important;
            transition: border-color 0.2s !important;
        }
        
        [data-testid="stTextInput"] input:focus,
        .stTextInput input:focus {
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 1px #3b82f6 !important;
        }
        
        [data-testid="stDateInput"] input,
        .stDateInput input {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 0 !important;
        }
        
        [data-testid="stFileUploadDropzone"],
        .stFileUploader > div {
            background-color: #fafafa !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 0 !important;
            transition: all 0.2s !important;
        }
        
        [data-testid="stFileUploadDropzone"]:hover {
            border-color: #3b82f6 !important;
            background-color: #f9fafb !important;
        }
        
        [data-testid="stFileUploadDropzone"] svg {
            color: #9ca3af !important;
        }
        
        [data-testid="stFileUploadDropzone"] p,
        [data-testid="stFileUploadDropzone"] span {
            color: #6b7280 !important;
            font-size: 0.875rem !important;
        }
        
        [data-testid="stTextArea"] textarea,
        .stTextArea textarea {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 0 !important;
            font-size: 0.875rem !important;
        }
        
        [data-testid="stTextArea"] textarea:focus,
        .stTextArea textarea:focus {
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 1px #3b82f6 !important;
        }
        
        [data-testid="stSelectbox"] > div > div,
        .stSelectbox > div > div {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 0 !important;
        }
        
        /* ========== ボタンのスタイル ========== */
        .stButton > button {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 2px solid #1f2937 !important;
            font-weight: 600 !important;
            border-radius: 0 !important;
            padding: 0.75rem 2rem !important;
            letter-spacing: 0.05em !important;
            font-size: 0.875rem !important;
            transition: all 0.2s !important;
        }
        
        .stButton > button:hover:not(:disabled) {
            background-color: #1f2937 !important;
            color: #ffffff !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
        }
        
        .stButton > button:disabled {
            background-color: #f3f4f6 !important;
            color: #9ca3af !important;
            border-color: #e5e7eb !important;
            opacity: 0.6 !important;
        }
        
        /* ========== アラートメッセージ ========== */
        .stSuccess, [data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
            background-color: #f0fdf4 !important;
            color: #14532d !important;
            border-left: 3px solid #22c55e !important;
            border-radius: 0 !important;
        }
        
        .stSuccess svg {
            color: #22c55e !important;
        }
        
        .stWarning, [data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
            background-color: #fffbeb !important;
            color: #581c0c !important;
            border-left: 3px solid #f59e0b !important;
            border-radius: 0 !important;
        }
        
        .stWarning svg {
            color: #f59e0b !important;
        }
        
        .stInfo, [data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
            background-color: #eff6ff !important;
            color: #1e3a8a !important;
            border-left: 3px solid #3b82f6 !important;
            border-radius: 0 !important;
        }
        
        .stInfo svg {
            color: #3b82f6 !important;
        }
        
        /* ========== プログレスバー ========== */
        .stProgress > div > div {
            background-color: #f3f4f6 !important;
            border-radius: 0 !important;
        }
        
        .stProgress > div > div > div {
            background-color: #1f2937 !important;
            border-radius: 0 !important;
        }
        
        [data-testid="stExpander"] {
            border: 1px solid #e5e7eb !important;
            border-radius: 0 !important;
            background-color: #ffffff !important;
        }
        
        [data-testid="stExpander"] summary {
            background-color: #f9fafb !important;
            font-weight: 500 !important;
            color: #1f2937 !important;
        }
        
        [data-testid="stExpander"] summary:hover {
            background-color: #f3f4f6 !important;
        }
        
        hr {
            border: none !important;
            border-top: 1px solid #e5e7eb !important;
            margin: 2rem 0 !important;
        }
        
        /* ========== カスタムスタイル ========== */
        .report-header {
            text-align: center;
            padding: 3rem 0 2rem;
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 3rem;
            background: #ffffff;
        }
        
        .report-header h1 {
            font-size: 2.5rem !important;
            font-weight: 200 !important;
            letter-spacing: -0.03em !important;
            margin-bottom: 0.5rem !important;
        }
        
        .print-guidance {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 0;
            padding: 1.5rem;
            margin-bottom: 3rem;
            text-align: left;
            line-height: 1.8;
        }
        
        .print-guidance strong {
            color: #1f2937;
            font-size: 1rem;
            font-weight: 600;
            display: block;
            margin-bottom: 0.5rem;
        }
        
        .metric-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            padding: 2rem;
            border-radius: 0;
            text-align: center;
            height: 100%;
            transition: all 0.2s;
        }
        
        .metric-card:hover {
            border-color: #d1d5db;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        }
        
        .metric-value {
            font-size: 3.5rem;
            font-weight: 200;
            margin-bottom: 0.5rem;
            color: #1f2937;
            letter-spacing: -0.03em;
        }
        
        .metric-value-high {
            color: #dc2626;
        }
        
        .metric-label {
            font-size: 0.875rem;
            color: #6b7280;
            font-weight: 500;
            letter-spacing: 0.05em;
        }
        
        .photo-row {
            display: flex;
            gap: 2rem;
            margin-bottom: 2rem;
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 0;
            padding: 2rem;
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
            border-radius: 0;
            border: 1px solid #e5e7eb;
            background: #fafafa;
        }
        
        .content-container {
            flex: 1;
            min-width: 0;
            padding-left: 1.5rem;
        }
        
        .photo-title {
            font-size: 1rem;
            font-weight: 500;
            color: #1f2937;
            margin-bottom: 1rem;
            letter-spacing: 0.05em;
        }
        
        .photo-filename {
            font-size: 0.75rem;
            color: #9ca3af;
            font-weight: 400;
            text-transform: none;
            letter-spacing: normal;
        }
        
        .finding-high {
            background: #fef2f2;
            border-left: 3px solid #dc2626;
            padding: 0.75rem 1rem;
            margin-bottom: 0.75rem;
            border-radius: 0;
            color: #7f1d1d;
            font-size: 0.875rem;
        }
        
        .finding-medium {
            background: #fffbeb;
            border-left: 3px solid #f59e0b;
            padding: 0.75rem 1rem;
            margin-bottom: 0.75rem;
            border-radius: 0;
            color: #78350f;
            font-size: 0.875rem;
        }
        
        .finding-low {
            background: #eff6ff;
            border-left: 3px solid #3b82f6;
            padding: 0.75rem 1rem;
            margin-bottom: 0.75rem;
            border-radius: 0;
            color: #1e3a8a;
            font-size: 0.875rem;
        }
        
        .finding-location {
            font-weight: 600;
            margin-bottom: 0.5rem;
            font-size: 0.875rem;
            letter-spacing: 0.05em;
        }
        
        .finding-details {
            line-height: 1.6;
            font-size: 0.875rem;
        }
        
        .finding-details > div {
            margin-bottom: 0.25rem;
        }
        
        .observation-box {
            background: #f0fdf4;
            padding: 1rem;
            border-radius: 0;
            color: #14532d;
            font-size: 0.875rem;
            border-left: 3px solid #22c55e;
        }
        
        .no-finding-box {
            background: #f0fdf4;
            color: #14532d;
            padding: 1rem;
            text-align: center;
            border-radius: 0;
            font-size: 0.875rem;
            border: 1px solid #bbf7d0;
        }
        
        .edit-container {
            background: #fafafa;
            padding: 1.5rem;
            border-radius: 0;
            margin-bottom: 1rem;
            border: 1px solid #e5e7eb;
        }
        
        h2 {
            font-size: 1.5rem !important;
            font-weight: 300 !important;
            margin-bottom: 1.5rem !important;
            margin-top: 2rem !important;
            padding-bottom: 0.5rem !important;
            border-bottom: 1px solid #e5e7eb !important;
        }
        
        /* ========== 印刷用スタイル ========== */
        @media print {
            body, .stApp {
                background: white !important;
                background-color: white !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            
            @page {
                size: A4;
                margin: 20mm 15mm 20mm 15mm;
            }
            
            @page {
                @top-left-corner { content: none !important; }
                @top-left { content: none !important; }
                @top-center { content: none !important; }
                @top-right { content: none !important; }
                @top-right-corner { content: none !important; }
                @bottom-left-corner { content: none !important; }
                @bottom-left { content: none !important; }
                @bottom-center { content: none !important; }
                @bottom-right { content: none !important; }
                @bottom-right-corner { content: none !important; }
            }
            
            a[href]:after {
                content: none !important;
            }
            
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
            
            .main, .block-container, section.main > div {
                background: white !important;
                background-color: white !important;
            }
            
            .report-header {
                border-bottom: 1px solid #333 !important;
                background: white !important;
                page-break-after: avoid !important;
            }
            
            h1, h2, h3 {
                color: #000 !important;
                page-break-after: avoid !important;
            }
            
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
            
            .photo-row {
                page-break-inside: avoid !important;
                margin-bottom: 15px !important;
                padding: 15px !important;
                background: white !important;
                border: 1px solid #333 !important;
            }
            
            .photo-container {
                flex: 0 0 200px !important;
                max-width: 200px !important;
            }
            
            .photo-img {
                max-height: 150px !important;
                border: 1px solid #333 !important;
            }
            
            .photo-title {
                font-size: 0.9rem !important;
                color: #000 !important;
            }
            
            .photo-filename {
                font-size: 0.75rem !important;
                color: #6b7280 !important;
                font-weight: normal !important;
            }
            
            .finding-high {
                background: #fee2e2 !important;
                border-left: 3px solid #dc2626 !important;
                color: #7f1d1d !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
            
            .finding-medium {
                background: #fef3c7 !important;
                border-left: 3px solid #f59e0b !important;
                color: #78350f !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
            
            .finding-low {
                background: #dbeafe !important;
                border-left: 3px solid #3b82f6 !important;
                color: #1e3a8a !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
            
            .observation-box {
                background: #d1fae5 !important;
                color: #064e3b !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
            
            .no-finding-box {
                background: #d1fae5 !important;
                color: #047857 !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
            
            .finding-details {
                font-size: 0.7rem !important;
            }
            
            * {
                background-color: transparent !important;
            }
            
            html, body {
                background: white !important;
                background-color: white !important;
            }
        }
        
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
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
                e.preventDefault();
                alert('PDFとして保存するには、画面右上の「⋮」メニューから「Print」を選択してください。\\n\\n印刷設定で「ヘッダーとフッター」のチェックを外すと、URLや日付が表示されません。');
                return false;
            }
        });
    </script>
    """, unsafe_allow_html=True)

@st.cache_resource
def initialize_vertexai():
    try:
        if "gcp" not in st.secrets:
            st.error("GCP認証情報が設定されていません。")
            st.info("secrets.tomlファイルにGCPの認証情報を設定してください。")
            return None
        gcp_secrets = st.secrets["gcp"]
        service_account_info = json.loads(gcp_secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        vertexai.init(project=gcp_secrets["project_id"], location="asia-northeast1", credentials=credentials)
        return GenerativeModel("gemini-1.5-pro")
    except Exception as e:
        st.error(f"GCP認証の初期化に失敗しました: {e}")
        return None

# ----------------------------------------------------------------------
# 3. AIとデータ処理の関数
# ----------------------------------------------------------------------
def create_report_prompt(filenames):
    """より詳細で多面的な分析を行うためのプロンプト"""
    file_list_str = "\n".join([f"- {name}" for name in filenames])
    return f"""
    あなたは、日本のリフォーム・原状回復工事を専門とする、20年以上の経験を持つベテラン現場監督です。
    あなたの仕事は、提供された現場写真を詳細に分析し、新人現場監督に提出するための包括的で実用的な修繕提案レポートを作成することです。
    
    以下の写真（ファイル名と共に提示）を一枚ずつ丁寧に確認し、修繕や交換が必要と思われる箇所をすべて特定してください。
    分析にあたっては、以下の観点を考慮してください：
    
    【分析の観点】
    1. 物理的損傷（傷、凹み、ひび割れ、剥がれ、変色など）
    2. 機能的問題（動作不良、水漏れ、電気系統の異常など）
    3. 経年劣化（使用年数による自然な劣化、寿命が近い設備など）
    4. 美観上の問題（汚れ、黄ばみ、カビ、錆びなど）
    5. 安全性の問題（破損による怪我のリスク、構造的な問題など）
    6. 法令・規格への適合性（現行の建築基準、消防法などへの適合）
    7. 予防保全の観点（今は問題ないが、近い将来に問題となる可能性がある箇所）
    
    【詳細な報告内容】
    各指摘事項について、以下の情報を含めて詳細に記述してください：
    - 具体的な場所（例：「北側壁面の窓枠下部」「トイレ便器の給水管接続部」）
    - 現状の詳細な説明（損傷の大きさ、範囲、程度などを数値や比較で表現）
    - 推定される原因（なぜその問題が発生したのか）
    - 放置した場合のリスク（どのような二次的問題が発生する可能性があるか）
    - 推奨する工事内容（具体的な工法、使用材料、作業手順など）
    - どのジャンルの職人に依頼すべきか、また工法、工事の手順はどのようなものか
    - 工事の推奨時期（緊急性の判断根拠と共に）
    - 正確な判断、見積作成の為に、何を確認すべきか、どこの寸法を測っておくべきかなど
    - 見落とし、見積もり間違いの注意点など（異なるサイズ、排水芯、排気）によるトラブルを未然に防ぐ為
    
    **最重要**: あなたの出力は、純粋なJSON文字列のみでなければなりません。説明文や ```json ... ``` のようなマークダウンは絶対に含めないでください。
    
    **JSONの構造**:
    出力は、JSONオブジェクトのリスト形式 `[ ... ]` としてください。各オブジェクトは1枚の写真に対応します。
    
    各写真オブジェクトには、以下のキーを含めてください。
    - "file_name": (string) 分析対象の写真のファイル名。
    - "findings": (array) その写真から見つかった指摘事項のリスト。指摘がない場合は空のリスト `[]` としてください。
    - "observation": (string) 【重要】"findings"が空の場合にのみ、写真から読み取れる詳細な状態を記述してください。設備の型番、メーカー、推定年式、全体的な状態、今後の保守推奨事項など、できる限り詳しく記載してください。"findings"がある場合は空文字列 `""` としてください。
    
    "findings" 配列の各指摘事項オブジェクトには、以下のキーを含めてください。
    - "location": (string) 指摘箇所の具体的な場所。方角、高さ、他の設備との位置関係なども含めて詳細に記述。
    - "current_state": (string) 現状の詳細な説明。損傷の種類、大きさ、範囲、進行度合い、周辺への影響などを具体的に記述。可能な限り数値化（例：「幅約15cm、深さ約3mmの亀裂」）。
    - "suggested_work": (string) 提案する工事内容。具体的な工法、使用する材料、作業手順、推定作業時間なども含めて詳細に記述。
    - "priority": (string) 工事の緊急度を「高」「中」「低」の3段階で評価。
      - 高：安全性に関わる、または1ヶ月以内の対応が必要
      - 中：機能性に影響があり、3ヶ月以内の対応を推奨
      - 低：美観上の問題で、6ヶ月以内の対応で問題ない
    - "notes": (string) 新人現場監督への補足事項。原因の推定、放置した場合のリスク、費用の目安、代替案、関連する他の箇所への影響など、判断に役立つ追加情報を記載。
    
    ---
    分析対象のファイルリスト: 
    {file_list_str}
    ---
    
    それでは、以下の写真の詳細な分析を開始してください。プロの視点から、見落としがないよう細部まで注意深く確認し、クライアントにとって最も有益な情報を提供してください。
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
        st.error("応答をJSONとして解析できませんでした。")
        st.info("生の応答:")
        st.code(text, language="text")
        return None

# ----------------------------------------------------------------------
# 4. レポート表示の関数
# ----------------------------------------------------------------------
def optimize_image_for_display(file_obj, max_width=800):
    """画像を最適化してbase64エンコード"""
    try:
        file_obj.seek(0)
        img = Image.open(file_obj)
        
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        output = io.BytesIO()
        img = img.convert('RGB') if img.mode != 'RGB' else img
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        return base64.b64encode(output.read()).decode()
    except Exception as e:
        # エラーメッセージを単純化
        st.warning(f"画像の最適化中にエラーが発生しました: {str(e)}")
        try:
            file_obj.seek(0)
            return base64.b64encode(file_obj.read()).decode()
        except Exception:
            return None

def create_photo_row_html(index, item, img_base64=None):
    """写真と内容を横並びで表示するHTML（読み取り専用）"""
    file_name = html.escape(str(item.get('file_name', '')))
    findings = item.get("findings", [])
    
    if img_base64:
        photo_html = f'<img src="data:image/jpeg;base64,{img_base64}" class="photo-img" loading="lazy">'
    else:
        photo_html = '<div style="height: 150px; background: #f3f4f6; display: flex; align-items: center; justify-content: center; border-radius: 8px;">画像なし</div>'
    
    content_html = f'<div class="photo-title">{index}. <span class="photo-filename">{file_name}</span></div>'
    
    if findings:
        for finding in findings:
            priority = finding.get('priority', '中')
            priority_class = {
                '高': 'finding-high',
                '中': 'finding-medium',
                '低': 'finding-low'
            }.get(priority, 'finding-medium')
            
            location = html.escape(str(finding.get('location', 'N/A')))
            current_state = html.escape(str(finding.get('current_state', 'N/A')))
            suggested_work = html.escape(str(finding.get('suggested_work', 'N/A')))
            
            content_html += f'''
            <div class="{priority_class}">
                <div class="finding-location">{location} [緊急度: {priority}]</div>
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
        content_html += f'<div class="observation-box">所見: {observation}</div>'
    else:
        content_html += '<div class="no-finding-box">修繕必要箇所なし</div>'
    
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
    if st.session_state.edited_report is None:
        st.session_state.edited_report = json.loads(json.dumps(report_payload))
    
    report_data = st.session_state.edited_report.get('report_data', [])
    report_title = st.session_state.edited_report.get('title', '')
    survey_date = st.session_state.edited_report.get('date', '')
    
    st.markdown('<div class="report-header">', unsafe_allow_html=True)
    st.title("現場分析レポート")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**物件名:** {report_title or '（未設定）'}")
    with col2:
        st.markdown(f"**調査日:** {survey_date}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for f in item.get("findings", []) if f.get("priority") == "高")
    
    st.header("分析結果サマリー")
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
    
    st.header("詳細分析結果")
    
    for i, item in enumerate(report_data):
        with st.container():
            col1, col2 = st.columns([1, 2])
            
            with col1:
                if files_dict and item.get('file_name') in files_dict:
                    try:
                        file_obj = files_dict[item['file_name']]
                        img_base64 = optimize_image_for_display(file_obj)
                        if img_base64:
                            st.markdown(f'<img src="data:image/jpeg;base64,{img_base64}" class="photo-img">', unsafe_allow_html=True)
                        else:
                            st.info("画像を表示できません")
                    except Exception as e:
                        st.error(f"画像の表示エラー: {str(e)}")
                        st.info("画像を表示できません")
                else:
                    st.info("画像なし")
                st.markdown(f'<p style="margin-top: 0.5rem; font-size: 0.85rem; color: #9ca3af;">{i + 1}. {item.get("file_name", "")}</p>', unsafe_allow_html=True)
            
            with col2:
                findings = item.get("findings", [])
                
                if findings:
                    findings_to_delete = []
                    for j, finding in enumerate(findings):
                        current_location = finding.get('location', '')
                        current_priority = finding.get('priority', '中')
                        
                        with st.expander(f"指摘事項 {j + 1}: {current_location if current_location else '(未入力)'} ({current_priority})", expanded=True):
                            new_location = st.text_input(
                                "場所",
                                value=finding.get('location', ''),
                                key=f"location_{i}_{j}"
                            )
                            
                            new_current_state = st.text_area(
                                "現状",
                                value=finding.get('current_state', ''),
                                key=f"current_{i}_{j}",
                                height=80
                            )
                            
                            new_suggested_work = st.text_area(
                                "提案する工事内容",
                                value=finding.get('suggested_work', ''),
                                key=f"suggest_{i}_{j}",
                                height=80
                            )
                            
                            priority_options = ['高', '中', '低']
                            try:
                                current_priority = finding.get('priority', '中')
                                if current_priority not in priority_options:
                                    current_priority = '中'
                                current_priority_index = priority_options.index(current_priority)
                            except ValueError:
                                current_priority_index = 1
                                
                            new_priority = st.selectbox(
                                "緊急度",
                                options=priority_options,
                                index=current_priority_index,
                                key=f"priority_{i}_{j}"
                            )
                            
                            new_notes = st.text_area(
                                "備考",
                                value=finding.get('notes', ''),
                                key=f"notes_{i}_{j}",
                                height=80
                            )
                            
                            if st.button(f"この指摘事項を削除", key=f"delete_{i}_{j}"):
                                findings_to_delete.append(j)
                            
                            finding['location'] = new_location
                            finding['current_state'] = new_current_state
                            finding['suggested_work'] = new_suggested_work
                            finding['priority'] = new_priority
                            finding['notes'] = new_notes
                    
                    for idx in reversed(findings_to_delete):
                        st.session_state.edited_report['report_data'][i]['findings'].pop(idx)
                        st.rerun()
                    
                    if st.button(f"指摘事項を追加", key=f"add_finding_{i}"):
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
                    new_observation = st.text_area(
                        "所見",
                        value=item.get('observation', ''),
                        key=f"observation_{i}",
                        height=100
                    )
                    st.session_state.edited_report['report_data'][i]['observation'] = new_observation
                    
                    if st.button(f"指摘事項に変更", key=f"convert_{i}"):
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
                    st.info("修繕必要箇所なし")
                    if st.button(f"指摘事項を追加", key=f"add_new_{i}"):
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
    """読み取り専用のレポート表示"""
    report_data = report_payload.get('report_data', [])
    report_title = report_payload.get('title', '')
    survey_date = report_payload.get('date', '')
    
    st.markdown('<div class="report-header">', unsafe_allow_html=True)
    st.title("現場分析レポート")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**物件名:** {report_title or '（未設定）'}")
    with col2:
        st.markdown(f"**調査日:** {survey_date}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.header("分析結果サマリー")
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
    
    st.header("詳細分析結果")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, item in enumerate(report_data):
        progress = (i + 1) / len(report_data)
        progress_bar.progress(progress)
        status_text.text(f"画像を処理中... ({i + 1}/{len(report_data)})")
        
        img_base64 = None
        if files_dict and item.get('file_name') in files_dict:
            file_obj = files_dict[item['file_name']]
            img_base64 = optimize_image_for_display(file_obj)
        
        photo_row_html = create_photo_row_html(i + 1, item, img_base64)
        st.markdown(photo_row_html, unsafe_allow_html=True)
    
    progress_bar.empty()
    status_text.empty()

# ----------------------------------------------------------------------
# 5. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    inject_custom_css()
    
    if not check_password():
        return
    
    model = initialize_vertexai()

    if st.session_state.report_payload is not None:
        st.success("レポートの作成が完了しました")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.session_state.edit_mode:
                if st.button("編集を保存して表示モードへ", key="save_edit", use_container_width=True):
                    st.session_state.report_payload = json.loads(json.dumps(st.session_state.edited_report))
                    st.session_state.edit_mode = False
                    st.rerun()
            else:
                if st.button("レポートを編集", key="start_edit", use_container_width=True):
                    st.session_state.edit_mode = True
                    st.session_state.edited_report = None
                    st.rerun()
        
        with col2:
            if st.session_state.edit_mode:
                if st.button("編集をキャンセル", key="cancel_edit", use_container_width=True):
                    st.session_state.edit_mode = False
                    st.session_state.edited_report = None
                    st.rerun()
        
        with col3:
            if st.button("新しいレポートを作成", key="new_from_result", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        
        if not st.session_state.edit_mode:
            st.markdown("""
                <div class="print-guidance">
                    <strong>PDFとして保存する方法</strong><br>
                    1. 画面右上の「⋮」（3点メニュー）をクリック<br>
                    2. 「Print」を選択<br>
                    3. 印刷設定で「ヘッダーとフッター」のチェックを外す<br>
                    4. 「PDFに保存」を選択
                </div>
            """, unsafe_allow_html=True)
        
        if st.session_state.edit_mode:
            display_editable_report(st.session_state.report_payload, st.session_state.files_dict)
        else:
            display_full_report(st.session_state.report_payload, st.session_state.files_dict)
        return

    st.title("現場写真分析・報告書作成システム（現場監督用）")
    st.markdown("現場写真をアップロードすると、修繕提案レポートを自動作成します。")

    if not model:
        st.warning("モデルを読み込めませんでした。")
        st.stop()

    if st.session_state.processing:
        st.warning("現在処理中です。しばらくお待ちください...")
        
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
        st.success(f"{len(uploaded_files)}件の写真がアップロードされました。")
    
    button_label = "処理中..." if st.session_state.processing else "レポートを作成"
    button_disabled = not uploaded_files or st.session_state.processing
    
    submitted = st.button(
        button_label,
        type="primary",
        use_container_width=True,
        disabled=button_disabled,
        key="submit_button"
    )

    if submitted and not st.session_state.processing and uploaded_files:
        st.session_state.processing = True
        
        ui_placeholder = st.empty()
        with ui_placeholder.container():
            total_batches = math.ceil(len(uploaded_files) / BATCH_SIZE)
            progress_bar = st.progress(0, text="分析の準備をしています...")
            
            final_report_data = []
            try:
                for i in range(0, len(uploaded_files), BATCH_SIZE):
                    current_batch_num = (i // BATCH_SIZE) + 1
                    progress_text = f"写真を分析中... (バッチ {current_batch_num}/{total_batches})"
                    progress_bar.progress(i / len(uploaded_files), text=progress_text)

                    file_batch = uploaded_files[i:i + BATCH_SIZE]
                    filenames = [f.name for f in file_batch]
                    prompt = create_report_prompt(filenames)
                    
                    response_text = generate_ai_report(model, file_batch, prompt)
                    batch_report_data = parse_json_response(response_text)
                    
                    if batch_report_data:
                        final_report_data.extend(batch_report_data)
                    else:
                        st.error(f"バッチ {current_batch_num} の分析でエラーが発生しました。")
                
                progress_bar.progress(1.0, text="分析完了")
                
                st.session_state.files_dict = {f.name: f for f in uploaded_files}
                st.session_state.report_payload = {
                    "title": report_title,
                    "date": survey_date.strftime('%Y年%m月%d日'),
                    "report_data": final_report_data
                }
                
            except Exception as e:
                st.error(f"分析処理でエラーが発生しました: {str(e)}")
                st.session_state.processing = False
                st.session_state.report_payload = None
            finally:
                st.session_state.processing = False
                ui_placeholder.empty()
                st.rerun()

if __name__ == "__main__":
    main()
