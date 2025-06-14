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
# パスワード認証機能
# ----------------------------------------------------------------------
# secrets.tomlから安全にパスワード取得
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
            font-weight: 300 !important;
            letter-spacing: -0.02em !important;
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
            font-weight: 500 !important;
            opacity: 1 !important;
            font-size: 0.875rem !important;
            letter-spacing: 0.05em !important;
        }
        
        /* テキスト入力フィールド */
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
        
        /* 日付入力フィールド */
        [data-testid="stDateInput"] input,
        .stDateInput input {
            background-color: #ffffff !important;
            color: #1f2937 !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 0 !important;
        }
        
        /* ファイルアップローダー */
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
        
        /* テキストエリア */
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
        
        /* セレクトボックス */
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
        /* 成功メッセージ */
        .stSuccess, [data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
            background-color: #f0fdf4 !important;
            color: #14532d !important;
            border-left: 3px solid #22c55e !important;
            border-radius: 0 !important;
        }
        
        .stSuccess svg {
            color: #22c55e !important;
        }
        
        /* 警告メッセージ */
        .stWarning, [data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
            background-color: #fffbeb !important;
            color: #581c0c !important;
            border-left: 3px solid #f59e0b !important;
            border-radius: 0 !important;
        }
        
        .stWarning svg {
            color: #f59e0b !important;
        }
        
        /* 情報メッセージ */
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
        
        /* エクスパンダー */
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
        
        /* セクション区切り線 */
        hr {
            border: none !important;
            border-top: 1px solid #e5e7eb !important;
            margin: 2rem 0 !important;
        }
        
        /* ========== カスタムスタイル ========== */
        /* 基本スタイル */
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
        
        /* 印刷ガイダンス */
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
        
        /* サマリーカード */
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
        
        /* 写真セクション（横並びレイアウト） */
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
        
        /* 指摘事項のスタイル */
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
        
        /* 交換部材情報のスタイル */
        .parts-info-box {
            background: #f0f9ff;
            border: 1px solid #0ea5e9;
            border-radius: 0;
            padding: 1rem;
            margin-top: 0.5rem;
            font-size: 0.8rem;
        }
        
        .parts-info-title {
            font-weight: 600;
            color: #0369a1;
            margin-bottom: 0.5rem;
        }
        
        /* 新人向けアドバイスのスタイル */
        .advice-box {
            background: #fef3c7;
            border: 1px solid #f59e0b;
            border-radius: 0;
            padding: 1rem;
            margin-top: 0.5rem;
            font-size: 0.8rem;
        }
        
        .advice-title {
            font-weight: 600;
            color: #92400e;
            margin-bottom: 0.5rem;
        }
        
        /* 編集エリアのスタイル */
        .edit-container {
            background: #fafafa;
            padding: 1.5rem;
            border-radius: 0;
            margin-bottom: 1rem;
            border: 1px solid #e5e7eb;
        }
        
        /* Section headers */
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
            /* 背景を白に設定 */
            body, .stApp {
                background: white !important;
                background-color: white !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            
            /* ページの余白を設定 */
            @page {
                size: A4;
                margin: 20mm 15mm 20mm 15mm;
            }
            
            /* ブラウザのヘッダー/フッターを非表示 */
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
            
            /* リンクのURLを非表示 */
            a[href]:after {
                content: none !important;
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
            
            /* タイトルとヘッダー */
            .report-header {
                border-bottom: 1px solid #333 !important;
                background: white !important;
                page-break-after: avoid !important;
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
            
            .parts-info-box {
                background: #e0f2fe !important;
                color: #075985 !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
            
            .advice-box {
                background: #fef3c7 !important;
                color: #92400e !important;
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
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
# 3. 交換部材データベースと新人向けアドバイス
# ----------------------------------------------------------------------
def get_parts_database():
    """交換部材の代表的なメーカー・シリーズ・品番・定価情報"""
    return {
        # 電気設備
        "分電盤": {
            "メーカー": "Panasonic",
            "シリーズ": "コスモパネル",
            "品番": "BQR8162",
            "定価": "8,500円"
        },
        "分電盤カバー": {
            "メーカー": "Panasonic",
            "シリーズ": "コスモパネル",
            "品番": "BQR8162",
            "定価": "8,500円"
        },
        "ブレーカー": {
            "メーカー": "Panasonic",
            "シリーズ": "安全ブレーカ",
            "品番": "BS2022",
            "定価": "2,800円"
        },
        "コンセント": {
            "メーカー": "Panasonic",
            "シリーズ": "コスモシリーズワイド21",
            "品番": "WTP1532WKP",
            "定価": "1,200円"
        },
        "スイッチ": {
            "メーカー": "Panasonic",
            "シリーズ": "コスモシリーズワイド21",
            "品番": "WTP50011WP",
            "定価": "980円"
        },
        "照明器具": {
            "メーカー": "Panasonic",
            "シリーズ": "LEDシーリングライト",
            "品番": "LGC31120",
            "定価": "12,800円"
        },
        "LED照明": {
            "メーカー": "Panasonic",
            "シリーズ": "LEDシーリングライト",
            "品番": "LGC31120",
            "定価": "12,800円"
        },
        
        # 水回り設備
        "トイレ": {
            "メーカー": "TOTO",
            "シリーズ": "ピュアレストQR",
            "品番": "CS232B+SH233BA",
            "定価": "98,000円"
        },
        "便器": {
            "メーカー": "TOTO",
            "シリーズ": "ピュアレストQR",
            "品番": "CS232B",
            "定価": "58,000円"
        },
        "便座": {
            "メーカー": "TOTO",
            "シリーズ": "ウォシュレット",
            "品番": "TCF8GM23",
            "定価": "45,000円"
        },
        "ウォシュレット": {
            "メーカー": "TOTO",
            "シリーズ": "ウォシュレット",
            "品番": "TCF8GM23",
            "定価": "45,000円"
        },
        "洗面台": {
            "メーカー": "LIXIL",
            "シリーズ": "ピアラ",
            "品番": "AR3N-755SY",
            "定価": "78,000円"
        },
        "洗面器": {
            "メーカー": "LIXIL",
            "シリーズ": "ピアラ",
            "品番": "L-555ANC",
            "定価": "28,000円"
        },
        "水栓": {
            "メーカー": "TOTO",
            "シリーズ": "シングルレバー混合栓",
            "品番": "TKS05301J",
            "定価": "19,800円"
        },
        "蛇口": {
            "メーカー": "TOTO",
            "シリーズ": "シングルレバー混合栓",
            "品番": "TKS05301J",
            "定価": "19,800円"
        },
        "キッチン水栓": {
            "メーカー": "TOTO",
            "シリーズ": "GGシリーズ",
            "品番": "TKS05301J",
            "定価": "24,800円"
        },
        "シャワーヘッド": {
            "メーカー": "TOTO",
            "シリーズ": "エアインシャワー",
            "品番": "THC7C",
            "定価": "8,500円"
        },
        "シャワーホース": {
            "メーカー": "TOTO",
            "シリーズ": "メタルホース",
            "品番": "THY478ELLR",
            "定価": "4,200円"
        },
        
        # 建具・内装
        "ドア": {
            "メーカー": "Panasonic",
            "シリーズ": "ベリティス",
            "品番": "XMJE1PC◇N01R7△",
            "定価": "48,000円"
        },
        "室内ドア": {
            "メーカー": "Panasonic",
            "シリーズ": "ベリティス",
            "品番": "XMJE1PC◇N01R7△",
            "定価": "48,000円"
        },
        "ドアノブ": {
            "メーカー": "GOAL",
            "シリーズ": "レバーハンドル",
            "品番": "LX-5",
            "定価": "12,000円"
        },
        "ドアクローザー": {
            "メーカー": "RYOBI",
            "シリーズ": "取替用ドアクローザー",
            "品番": "S-202P",
            "定価": "8,500円"
        },
        "床材": {
            "メーカー": "東リ",
            "シリーズ": "CFシート",
            "品番": "CF9435",
            "定価": "3,800円/㎡"
        },
        "フローリング": {
            "メーカー": "Panasonic",
            "シリーズ": "ベリティスフロアーS",
            "品番": "KESWV3SY",
            "定価": "8,200円/㎡"
        },
        "クロス": {
            "メーカー": "サンゲツ",
            "シリーズ": "SP",
            "品番": "SP2801",
            "定価": "1,200円/㎡"
        },
        "壁紙": {
            "メーカー": "サンゲツ",
            "シリーズ": "SP",
            "品番": "SP2801",
            "定価": "1,200円/㎡"
        },
        
        # 空調・換気
        "エアコン": {
            "メーカー": "ダイキン",
            "シリーズ": "Eシリーズ",
            "品番": "AN22ZES-W",
            "定価": "78,000円"
        },
        "換気扇": {
            "メーカー": "Panasonic",
            "シリーズ": "天井埋込形換気扇",
            "品番": "FY-24CPG8",
            "定価": "15,800円"
        },
        "レンジフード": {
            "メーカー": "Panasonic",
            "シリーズ": "スマートスクエアフード",
            "品番": "FY-6HZC4-S",
            "定価": "98,000円"
        },
        
        # その他
        "給湯器": {
            "メーカー": "リンナイ",
            "シリーズ": "エコジョーズ",
            "品番": "RUF-E2406SAW",
            "定価": "298,000円"
        },
        "インターホン": {
            "メーカー": "Panasonic",
            "シリーズ": "どこでもドアホン",
            "品番": "VL-SWH705KL",
            "定価": "58,000円"
        },
        "火災報知器": {
            "メーカー": "Panasonic",
            "シリーズ": "けむり当番",
            "品番": "SHK48455",
            "定価": "3,800円"
        }
    }

def get_contractor_advice():
    """新人現場監督向けアドバイスデータベース"""
    return {
        # 電気設備
        "分電盤": {
            "注意点": "必ず電気工事士の有資格者が作業すること。停電作業が必要。",
            "交換手順": [
                "1. 事前に停電の告知・調整",
                "2. 主幹ブレーカーをOFF",
                "3. 既存分電盤の配線をマーキング",
                "4. 新規分電盤へ配線を移設",
                "5. 絶縁抵抗測定・動作確認"
            ],
            "必要な職人": ["電気工事士"],
            "依頼先": ["電気工事会社"],
            "費用目安": {
                "作業費": "30,000円～50,000円",
                "材料費": "本体価格＋20%（配線材料等）"
            },
            "材料費提案": [
                {"品名": "分電盤本体", "参考価格": "8,500円"},
                {"品名": "配線材料一式", "参考価格": "3,000円"},
                {"品名": "その他部材", "参考価格": "2,000円"}
            ]
        },
        "コンセント": {
            "注意点": "電気工事士の資格が必要。配線の劣化も確認すること。",
            "交換手順": [
                "1. ブレーカーをOFF",
                "2. 既存コンセントを取り外し",
                "3. 配線の状態確認",
                "4. 新規コンセント取付",
                "5. 絶縁確認・動作テスト"
            ],
            "必要な職人": ["電気工事士"],
            "依頼先": ["電気工事会社", "電気設備会社"],
            "費用目安": {
                "作業費": "3,000円～5,000円/箇所",
                "材料費": "1,200円～2,000円/箇所"
            },
            "材料費提案": [
                {"品名": "コンセント本体", "参考価格": "1,200円"},
                {"品名": "プレート", "参考価格": "300円"}
            ]
        },
        
        # 水回り設備
        "トイレ": {
            "注意点": "既存の排水芯を確認。止水栓を必ず閉める。床の防水処理も確認。",
            "交換手順": [
                "1. 止水栓を閉める",
                "2. 既存便器の水を抜く",
                "3. 便器・タンクを取り外し",
                "4. 排水ソケット確認・清掃",
                "5. 新規便器設置・配管接続",
                "6. 水漏れ確認"
            ],
            "必要な職人": ["設備工事士", "水道工事士"],
            "依頼先": ["水道工事会社", "リフォーム会社"],
            "費用目安": {
                "作業費": "30,000円～50,000円",
                "材料費": "便器本体価格＋配管部材"
            },
            "材料費提案": [
                {"品名": "便器・タンクセット", "参考価格": "98,000円"},
                {"品名": "給水管", "参考価格": "2,000円"},
                {"品名": "パッキン類", "参考価格": "1,500円"}
            ]
        },
        "水栓": {
            "注意点": "止水栓の位置を事前確認。パッキンの予備を準備。",
            "交換手順": [
                "1. 止水栓を閉める",
                "2. 既存水栓を取り外し",
                "3. 配管接続部の清掃",
                "4. 新規水栓取付",
                "5. 水漏れ確認・流量調整"
            ],
            "必要な職人": ["水道工事士", "設備工事士"],
            "依頼先": ["水道工事会社", "設備工事会社"],
            "費用目安": {
                "作業費": "8,000円～15,000円",
                "材料費": "本体価格＋接続部材"
            },
            "材料費提案": [
                {"品名": "水栓本体", "参考価格": "19,800円"},
                {"品名": "フレキホース", "参考価格": "1,500円"},
                {"品名": "シールテープ", "参考価格": "300円"}
            ]
        },
        
        # 建具・内装
        "ドア": {
            "注意点": "開き勝手の確認。枠の水平・垂直を正確に。",
            "交換手順": [
                "1. 既存ドアの採寸",
                "2. 丁番・ラッチの位置確認",
                "3. 既存ドア撤去",
                "4. 新規ドア吊り込み",
                "5. 建付け調整"
            ],
            "必要な職人": ["建具工", "大工"],
            "依頼先": ["建具店", "リフォーム会社"],
            "費用目安": {
                "作業費": "15,000円～25,000円",
                "材料費": "ドア本体価格"
            },
            "材料費提案": [
                {"品名": "室内ドア本体", "参考価格": "48,000円"},
                {"品名": "丁番", "参考価格": "2,000円"},
                {"品名": "ドアノブ", "参考価格": "8,000円"}
            ]
        },
        "クロス": {
            "注意点": "下地の状態確認が重要。パテ処理を丁寧に。",
            "交換手順": [
                "1. 既存クロス剥がし",
                "2. 下地処理・パテ埋め",
                "3. プライマー塗布",
                "4. 新規クロス貼り",
                "5. エア抜き・仕上げ"
            ],
            "必要な職人": ["クロス工", "内装工"],
            "依頼先": ["内装工事会社", "リフォーム会社"],
            "費用目安": {
                "作業費": "1,000円～1,500円/㎡",
                "材料費": "1,200円～2,000円/㎡"
            },
            "材料費提案": [
                {"品名": "クロス材", "参考価格": "1,200円/㎡"},
                {"品名": "接着剤", "参考価格": "300円/㎡"},
                {"品名": "下地材", "参考価格": "200円/㎡"}
            ]
        },
        
        # 空調・換気
        "エアコン": {
            "注意点": "電源容量の確認。冷媒ガスの適正処理。",
            "交換手順": [
                "1. 冷媒ガス回収",
                "2. 室内機・室外機撤去",
                "3. 配管洗浄・確認",
                "4. 新規機器設置",
                "5. 真空引き・試運転"
            ],
            "必要な職人": ["空調設備工", "電気工事士"],
            "依頼先": ["空調設備会社", "電器店"],
            "費用目安": {
                "作業費": "15,000円～30,000円",
                "材料費": "本体価格＋配管材料"
            },
            "材料費提案": [
                {"品名": "エアコン本体", "参考価格": "78,000円"},
                {"品名": "配管材料", "参考価格": "5,000円"},
                {"品名": "ドレンホース", "参考価格": "1,000円"}
            ]
        }
    }

def extract_required_parts(suggested_work):
    """提案工事内容から必要な部材を抽出"""
    parts_db = get_parts_database()
    required_parts = []
    
    # 部材名をチェック
    for part_name in parts_db.keys():
        if part_name in suggested_work:
            required_parts.append(part_name)
    
    return required_parts

def generate_parts_info_html(parts_list):
    """部材情報のHTML生成"""
    if not parts_list:
        return ""
    
    parts_db = get_parts_database()
    html = '<div class="parts-info-box">'
    html += '<div class="parts-info-title">【交換部材情報】</div>'
    
    for part in parts_list:
        if part in parts_db:
            info = parts_db[part]
            html += f'''
            <div style="margin-bottom: 0.5rem;">
                <strong>{part}</strong><br>
                メーカー: {info['メーカー']} / シリーズ: {info['シリーズ']}<br>
                品番: {info['品番']} / 定価: {info['定価']}
            </div>
            '''
    
    html += '</div>'
    return html

def generate_advice_html(parts_list):
    """新人向けアドバイスのHTML生成"""
    if not parts_list:
        return ""
    
    advice_db = get_contractor_advice()
    html = '<div class="advice-box">'
    html += '<div class="advice-title">【新人現場監督向けアドバイス】</div>'
    
    for part in parts_list:
        if part in advice_db:
            advice = advice_db[part]
            html += f'''
            <div style="margin-bottom: 0.5rem;">
                <strong>{part}の交換</strong><br>
                ⚠️ 注意点: {advice['注意点']}<br>
                👷 必要な職人: {', '.join(advice['必要な職人'])}<br>
                📞 依頼先: {', '.join(advice['依頼先'])}<br>
                💰 費用目安: 作業費 {advice['費用目安']['作業費']}
            </div>
            '''
    
    html += '</div>'
    return html

# ----------------------------------------------------------------------
# 4. AIとデータ処理の関数
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
    - "suggested_work": (string) 提案する工事内容。具体的な部材名（トイレ、水栓、クロス、エアコン等）を含めること。
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
        st.error("応答をJSONとして解析できませんでした。")
        st.info("生の応答:"); st.code(text, language="text")
        return None

# ----------------------------------------------------------------------
# 5. レポート表示の関数
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
    
    # コンテンツ部分のHTML生成（番号とファイル名を分離）
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
            
            # 部材情報とアドバイスを追加
            required_parts = extract_required_parts(suggested_work)
            if required_parts:
                content_html += generate_parts_info_html(required_parts)
                content_html += generate_advice_html(required_parts)
    
    elif item.get("observation"):
        observation = html.escape(str(item.get('observation', '')))
        content_html += f'<div class="observation-box">所見: {observation}</div>'
    else:
        content_html += '<div class="no-finding-box">修繕必要箇所なし</div>'
    
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
    st.title("現場分析レポート")
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
    
    # 詳細分析結果（編集可能）
    st.header("詳細分析結果")
    
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
                # ファイル名をグレーで小さく表示
                st.markdown(f'<p style="margin-top: 0.5rem; font-size: 0.85rem; color: #9ca3af;">{i + 1}. {item.get("file_name", "")}</p>', unsafe_allow_html=True)
            
            with col2:
                findings = item.get("findings", [])
                
                if findings:
                    # 指摘事項の編集
                    findings_to_delete = []
                    for j, finding in enumerate(findings):
                        # 現在の場所の値を取得（リアルタイム更新のため）
                        current_location = finding.get('location', '')
                        current_priority = finding.get('priority', '中')
                        
                        with st.expander(f"指摘事項 {j + 1}: {current_location if current_location else '(未入力)'} ({current_priority})", expanded=True):
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
                                height=80
                            )
                            
                            # 部材情報とアドバイスの表示（編集モードでも表示）
                            required_parts = extract_required_parts(new_suggested_work)
                            if required_parts:
                                st.markdown(generate_parts_info_html(required_parts), unsafe_allow_html=True)
                                st.markdown(generate_advice_html(required_parts), unsafe_allow_html=True)
                            
                            # 削除ボタン
                            if st.button(f"この指摘事項を削除", key=f"delete_{i}_{j}"):
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
                    # 所見の編集
                    new_observation = st.text_area(
                        "所見",
                        value=item.get('observation', ''),
                        key=f"observation_{i}",
                        height=100
                    )
                    st.session_state.edited_report['report_data'][i]['observation'] = new_observation
                    
                    # 指摘事項に変更ボタン
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
    """読み取り専用のレポート表示（既存の関数）"""
    report_data = report_payload.get('report_data', [])
    report_title = report_payload.get('title', '')
    survey_date = report_payload.get('date', '')
    
    # ヘッダー
    st.markdown('<div class="report-header">', unsafe_allow_html=True)
    st.title("現場分析レポート")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**物件名:** {report_title or '（未設定）'}")
    with col2:
        st.markdown(f"**調査日:** {survey_date}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # サマリー
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
    
    # 詳細分析結果
    st.header("詳細分析結果")
    
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
# 6. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    # CSSを最初に注入して全体のスタイルを設定（認証画面でも適用）
    inject_custom_css()
    
    # パスワード認証チェック
    if not check_password():
        return
    
    model = initialize_vertexai()

    # --- 状態1: レポートが生成済み ---
    if st.session_state.report_payload is not None:
        st.success("レポートの作成が完了しました")
        
        # 編集モードの切り替えボタン
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.session_state.edit_mode:
                if st.button("編集を保存して表示モードへ", key="save_edit", use_container_width=True):
                    # 編集内容を保存
                    st.session_state.report_payload = json.loads(json.dumps(st.session_state.edited_report))
                    st.session_state.edit_mode = False
                    st.rerun()
            else:
                if st.button("レポートを編集", key="start_edit", use_container_width=True):
                    st.session_state.edit_mode = True
                    st.session_state.edited_report = None  # 編集データをリセット
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
        
        # 印刷ガイダンス（表示モードのみ）
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
        
        # レポート表示
        if st.session_state.edit_mode:
            display_editable_report(st.session_state.report_payload, st.session_state.files_dict)
        else:
            display_full_report(st.session_state.report_payload, st.session_state.files_dict)
        return

    # --- 状態2: 初期画面（入力フォーム） ---
    st.title("現場写真分析・報告書作成システム")
    st.markdown("現場写真をアップロードすると、修繕提案レポートを自動作成します。")

    if not model:
        st.warning("モデルを読み込めませんでした。")
        st.stop()

    # 処理中の場合、警告メッセージを表示
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
    
    # ボタンの作成（処理中は無効化）
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
        # 処理開始前に即座にprocessingフラグを設定
        st.session_state.processing = True
        
        # すぐに処理を開始（rerunnを使わない）
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
                
                # レポートの保存
                st.session_state.files_dict = {f.name: f for f in uploaded_files}
                st.session_state.report_payload = {
                    "title": report_title,
                    "date": survey_date.strftime('%Y年%m月%d日'),
                    "report_data": final_report_data
                }
                
            except Exception as e:
                st.error(f"分析処理でエラーが発生しました: {e}")
                st.session_state.processing = False
                st.session_state.report_payload = None
            finally:
                # 処理完了後にフラグをリセット
                st.session_state.processing = False
                ui_placeholder.empty()
                st.rerun()

if __name__ == "__main__":
    main()
