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
    layout="wide"
)
BATCH_SIZE = 10 # 一度にAIに送信する写真の枚数

# ----------------------------------------------------------------------
# 2. デザインとGCP初期化
# ----------------------------------------------------------------------
def inject_custom_css():
    """印刷用のカスタムCSSを注入する。"""
    st.markdown("""
    <style>
        /* 基本スタイル */
        .report-header {
            text-align: center;
            padding: 2rem 0;
            border-bottom: 3px solid #1F2937;
            margin-bottom: 2rem;
        }
        
        /* サマリーカード */
        .metric-card {
            background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
            padding: 1.5rem;
            border-radius: 12px;
            text-align: center;
            height: 100%;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        .metric-value {
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .metric-value-high {
            background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
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
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(229, 231, 235, 0.2);
            border-radius: 12px;
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
            border: 1px solid #e5e7eb;
        }
        
        .content-container {
            flex: 1;
            min-width: 0;
            padding-left: 1rem;
        }
        
        .photo-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #374151;
            margin-bottom: 0.8rem;
        }
        
        /* 指摘事項のスタイル（コンパクト版） */
        .finding-high {
            background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
            border-left: 3px solid #dc2626;
            padding: 0.6rem;
            margin-bottom: 0.6rem;
            border-radius: 6px;
            color: #7f1d1d;
            font-size: 0.85rem;
        }
        
        .finding-medium {
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border-left: 3px solid #f59e0b;
            padding: 0.6rem;
            margin-bottom: 0.6rem;
            border-radius: 6px;
            color: #78350f;
            font-size: 0.85rem;
        }
        
        .finding-low {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
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
            background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
            padding: 0.8rem;
            border-radius: 8px;
            color: #064e3b;
            font-size: 0.85rem;
        }
        
        .no-finding-box {
            background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
            color: #047857;
            padding: 0.8rem;
            text-align: center;
            border-radius: 8px;
            font-size: 0.85rem;
        }
        
        /* ダークモード対応 */
        @media (prefers-color-scheme: dark) {
            .metric-card {
                background: linear-gradient(135deg, #374151 0%, #1f2937 100%);
            }
            
            .metric-label {
                color: #d1d5db;
            }
            
            .photo-row {
                background-color: rgba(255, 255, 255, 0.1);
                border-color: rgba(229, 231, 235, 0.3);
            }
            
            .photo-title {
                color: #e5e7eb;
            }
        }
        
        /* 印刷用スタイル */
        @media print {
            /* Streamlitの要素を非表示 */
            .stApp > header,
            .stButton,
            .stAlert,
            button,
            div[data-testid="stDecoration"],
            div[data-testid="stToolbar"],
            section[data-testid="stSidebar"] {
                display: none !important;
            }
            
            /* ページ設定 */
            @page {
                size: A4;
                margin: 15mm;
            }
            
            /* メインコンテナ */
            .main .block-container {
                padding: 0 !important;
                max-width: 100% !important;
            }
            
            /* 写真行の印刷設定 */
            .photo-row {
                page-break-inside: avoid !important;
                break-inside: avoid !important;
                margin-bottom: 15px !important;
                padding: 15px !important;
                background: white !important;
                border: 1px solid #ddd !important;
            }
            
            /* 写真のサイズ調整 */
            .photo-container {
                flex: 0 0 200px !important;
                max-width: 200px !important;
            }
            
            .photo-img {
                max-height: 150px !important;
            }
            
            /* テキストサイズ調整 */
            .photo-title {
                font-size: 0.9rem !important;
            }
            
            .finding-high,
            .finding-medium,
            .finding-low,
            .observation-box,
            .no-finding-box {
                font-size: 0.75rem !important;
                padding: 0.5rem !important;
                margin-bottom: 0.4rem !important;
            }
            
            /* 指摘事項の詳細 */
            .finding-details {
                font-size: 0.7rem !important;
            }
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
def create_photo_row_html(index, item, img_base64=None):
    """写真と内容を横並びで表示するHTML"""
    file_name = html.escape(str(item.get('file_name', '')))
    findings = item.get("findings", [])
    
    # 写真部分
    photo_html = f'<img src="data:image/jpeg;base64,{img_base64}" class="photo-img">' if img_base64 else '<div style="height: 150px; background: #f3f4f6; display: flex; align-items: center; justify-content: center; border-radius: 8px;">画像なし</div>'
    
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

def display_full_report(report_payload, files_dict):
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
    
    # 各写真を横並びレイアウトで表示
    for i, item in enumerate(report_data):
        img_base64 = None
        if files_dict and item.get('file_name') in files_dict:
            file_obj = files_dict[item['file_name']]
            file_obj.seek(0)
            img_data = file_obj.read()
            img_base64 = base64.b64encode(img_data).decode()
        
        # 横並びの写真行を表示
        photo_row_html = create_photo_row_html(i + 1, item, img_base64)
        st.markdown(photo_row_html, unsafe_allow_html=True)

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
