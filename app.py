import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account
from datetime import date

# ----------------------------------------------------------------------
# 1. 設定と定数
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="AIリフォーム箇所分析レポート",
    page_icon="🏠",
    layout="wide"
)

try:
    GCP_SECRETS = st.secrets["gcp"]
    GCP_PROJECT_ID = GCP_SECRETS["project_id"]
    GCP_REGION = "asia-northeast1"
    MODEL_NAME = "gemini-1.5-pro"
    SERVICE_ACCOUNT_INFO = json.loads(GCP_SECRETS["gcp_service_account"])
except Exception as e:
    st.error(f"StreamlitのSecrets設定の読み込みに失敗しました。`[gcp]`セクションと`project_id`, `gcp_service_account`を確認してください。エラー: {e}")
    st.stop()


# ----------------------------------------------------------------------
# 2. デザインと補助関数
# ----------------------------------------------------------------------

def inject_custom_css():
    """
    レポートデザインを向上させるためのカスタムCSSを注入する。
    印刷時に不要なUIを非表示にし、レイアウト崩れを防ぐ。
    """
    st.markdown("""
    <style>
        /* --- レポート部分のデザイン --- */
        .report-container {
            background-color: #ffffff; /* ダークモードでも白背景を強制 */
            color: #333333;           /* ダークモードでも文字色を黒に強制 */
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            padding: 2.5em 3.5em;
            box-shadow: 0 8px 30px rgba(0,0,0,0.05);
            margin-top: 2em;
            margin-bottom: 2em;
        }
        .report-container h1 { color: #1F2937; font-size: 2.5em; border-bottom: 3px solid #D1D5DB; padding-bottom: 0.4em; }
        .report-container h2 { color: #1F2937; font-size: 1.8em; border-bottom: 2px solid #E5E7EB; padding-bottom: 0.3em; margin-top: 2em; }
        .report-container hr { border: 1px solid #e0e0e0; margin: 2.5em 0; }

        /* --- 写真ごとの分析セクション --- */
        .photo-section {
            page-break-inside: avoid !important; /* ★ページまたぎを強力に禁止 */
            padding-top: 2rem;
            margin-top: 2rem;
            border-top: 1px solid #e0e0e0;
        }
        /* 最初の写真セクションには上線と余白は不要 */
        .report-container .photo-section:first-of-type {
            border-top: none;
            padding-top: 0;
            margin-top: 0;
        }
        .photo-section h3 { color: #374151; font-size: 1.4em; margin-top: 0; margin-bottom: 1em; font-weight: 600; }
        

        /* --- 緊急度バッジ --- */
        .priority-badge { display: inline-block; padding: 0.3em 0.9em; border-radius: 15px; font-weight: 600; color: white; font-size: 0.9em; margin-left: 10px; }
        .priority-high { background-color: #DC2626; }
        .priority-medium { background-color: #F59E0B; }
        .priority-low { background-color: #3B82F6; }

        /* --- 印刷（PDF化）用のスタイル --- */
        .no-print {
            /* このクラスを持つ要素は印刷しない */
        }
        @media print {
            .no-print { display: none !important; }
            .stApp > header, .stApp > footer, .stToolbar { display: none !important; }
            .report-container { box-shadow: none; border: 1px solid #ccc; padding: 1em; margin: 0; }
        }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def initialize_vertexai():
    try:
        credentials = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO)
        vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION, credentials=credentials)
        return GenerativeModel(MODEL_NAME)
    except Exception as e:
        st.error(f"GCPの認証またはVertex AIの初期化に失敗しました: {e}")
        return None

def create_report_prompt(filenames):
    file_list_str = "\n".join([f"- {name}" for name in filenames])
    return f"""
あなたは、日本のリフォーム・原状回復工事を専門とする、経験豊富な現場監督です。あなたの仕事は、提供された現場写真を分析し、クライアントに提出するための、丁寧で分かりやすい修繕提案レポートを作成することです。以下の写真（ファイル名と共に提示）を一枚ずつ詳細に確認し、修繕や交換が必要と思われる箇所をすべて特定してください。特定した各箇所について、以下のJSON形式で報告書を作成してください。
**最重要**: あなたの出力は、純粋なJSON文字列のみでなければなりません。説明文や ```json ... ``` のようなマークダウンは絶対に含めないでください。
**JSONの構造**: 出力は、JSONオブジェクトのリスト形式 `[ ... ]` としてください。各オブジェクトは1枚の写真に対応します。
各写真オブジェクトには、以下のキーを含めてください。
- "file_name": (string) 分析対象の写真のファイル名。
- "findings": (array) その写真から見つかった指摘事項のリスト。指摘がない場合は空のリスト `[]` としてください。
"findings" 配列の各指摘事項オブジェクトには、以下のキーを含めてください。
- "location": (string) 指摘箇所の具体的な場所。
- "current_state": (string) 現状の客観的な説明。
- "suggested_work": (string) 提案する工事内容。
- "priority": (string) 工事の緊急度を「高」「中」「低」の3段階で評価。
- "notes": (string) クライアントへの補足事項。
---
分析対象のファイルリスト:
{file_list_str}
---
それでは、以下の写真の分析を開始してください。
"""

def generate_report(model, uploaded_files, prompt):
    image_parts = [Part.from_data(f.getvalue(), mime_type=f.type) for f in uploaded_files]
    contents = [prompt] + image_parts
    response = model.generate_content(contents)
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

def display_report_content(finding):
    """指摘事項の詳細をMarkdownとして表示する共通関数"""
    priority = finding.get('priority', 'N/A')
    p_class = {"高": "high", "中": "medium", "低": "low"}.get(priority, "")
    
    st.markdown(f"**指摘箇所: {finding.get('location', 'N/A')}** <span class='priority-badge priority-{p_class}'>緊急度: {priority}</span>", unsafe_allow_html=True)
    st.markdown(f"- **現状:** {finding.get('current_state', 'N/A')}")
    st.markdown(f"- **提案工事:** {finding.get('suggested_work', 'N/A')}")
    if finding.get('notes'):
        st.markdown(f"- **備考:** {finding.get('notes', 'N/A')}")

def display_report(report_data, uploaded_files_dict, report_title, survey_date):
    """プロフェッショナルなデザインでレポートを表示する"""
    
    st.markdown('<div class="report-container">', unsafe_allow_html=True)
    
    # 1. ヘッダーとサマリー
    st.markdown(f"<h1>現場分析レポート</h1>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    col1.markdown(f"**物件名・案件名:**<br>{report_title if report_title else '（未設定）'}", unsafe_allow_html=True)
    col2.markdown(f"**調査日:**<br>{survey_date}", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>📊 分析結果サマリー</h2>", unsafe_allow_html=True)
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(1 for item in report_data for finding in item.get("findings", []) if finding.get("priority") == "高")
    c1, c2, c3 = st.columns(3)
    c1.metric("分析写真枚数", f"{len(report_data)} 枚")
    c2.metric("総指摘件数", f"{total_findings} 件")
    c3.metric("緊急度「高」の件数", f"{high_priority_count} 件")
    st.markdown("<hr>", unsafe_allow_html=True)
    
    # 2. 詳細分析
    st.markdown("<h2>📋 詳細分析結果</h2>", unsafe_allow_html=True)
    
    for i, report_item in enumerate(report_data):
        file_name = report_item.get("file_name")
        findings = report_item.get("findings", [])
        image_file = uploaded_files_dict.get(file_name)
        if not image_file: continue

        # ★タイトル・写真・テキストを一つのグループとして囲む
        st.markdown(f'<div class="photo-section">', unsafe_allow_html=True)
        
        st.markdown(f"<h3>{i + 1}. 写真ファイル: {file_name}</h3>", unsafe_allow_html=True)
        col1, col2 = st.columns([2, 3])
        with col1:
            st.image(image_file, use_container_width=True)
        with col2:
            if not findings:
                st.success("✅ 特に修繕が必要な箇所は見つかりませんでした。")
            else:
                for finding in findings:
                    display_report_content(finding)
        
        st.markdown(f'</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------------------------------------------------
# 4. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    inject_custom_css()
    
    # --- 1. UI入力部分（印刷時には非表示） ---
    st.markdown('<div class="no-print">', unsafe_allow_html=True)
    st.title("📷 AIリフォーム箇所分析＆報告書作成")
    st.markdown("現場写真をアップロードすると、AIがクライアント向けの修繕提案レポートを自動作成します。")

    model = initialize_vertexai()
    if not model:
        st.warning("AIモデルを読み込めませんでした。"); st.stop()
    
    with st.form("report_form"):
        st.subheader("1. レポート情報入力")
        report_title = st.text_input("物件名・案件名", "（例）〇〇ビル 301号室 原状回復工事")
        survey_date = st.date_input("調査日", date.today())
        
        st.subheader("2. 写真アップロード")
        uploaded_files = st.file_uploader("分析したい写真を選択してください", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        
        submitted = st.form_submit_button("レポートを作成する", type="primary", use_container_width=True)

    if submitted:
        if not uploaded_files:
            st.warning("分析を開始するには、写真をアップロードしてください。")
        else:
            with st.spinner("AIが写真を分析し、レポートを作成中です… この処理には数分かかることがあります。"):
                try:
                    filenames = [f.name for f in uploaded_files]
                    prompt = create_report_prompt(filenames)
                    response_text = generate_report(model, uploaded_files, prompt)
                    report_data = parse_json_response(response_text)
                    
                    if report_data:
                        st.session_state.report_data = report_data
                        st.session_state.uploaded_files_dict = {f.name: f for f in uploaded_files}
                        st.session_state.report_title = report_title
                        st.session_state.survey_date = survey_date.strftime('%Y年%m月%d日')
                        st.success("✅ レポートの作成が完了しました！")
                        st.rerun()
                    else: st.error("レポートデータの生成に失敗しました。")
                except Exception as e:
                    st.error(f"分析中に予期せぬエラーが発生しました: {e}")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 2. レポート表示部分 ---
    if 'report_data' in st.session_state:
        st.markdown('<div class="no-print">', unsafe_allow_html=True)
        st.info("💡 レポートをPDFとして保存するには、ブラウザの印刷機能（Ctrl+P または Cmd+P）を使い、「送信先」で「PDFとして保存」を選択してください。")
        st.markdown('</div>', unsafe_allow_html=True)

        display_report(
            st.session_state.report_data,
            st.session_state.uploaded_files_dict,
            st.session_state.report_title,
            st.session_state.survey_date
        )

if __name__ == "__main__":
    main()
