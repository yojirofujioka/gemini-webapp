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
    印刷時（PDF化）に不要なUIを非表示にする設定も含む。
    """
    st.markdown("""
    <style>
        /* --- 全体的なスタイル --- */
        .stApp {
            background-color: #f0f2f6;
        }
        
        /* --- ボタンとUI要素 --- */
        .stButton>button {
            border-radius: 20px;
            font-weight: bold;
        }

        /* --- レポートコンテナ --- */
        .report-container {
            background-color: #ffffff;
            border-radius: 10px;
            padding: 2em 3em;
            box-shadow: 0 6px 20px rgba(0,0,0,0.08);
            margin-top: 2em;
        }
        
        /* --- 指摘事項カード --- */
        .finding-card {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1.5em;
            margin-top: 1.5em;
            background-color: #fafafa;
            page-break-inside: avoid; /* PDF化でカードが分割されるのを防ぐ */
        }

        .finding-card h5 {
            margin-top: 0;
            margin-bottom: 0.5rem;
        }
        
        /* --- 緊急度バッジ --- */
        .priority-badge {
            display: inline-block;
            padding: 0.3em 0.9em;
            border-radius: 15px;
            font-weight: 500;
            color: white;
            font-size: 0.9em;
            margin-left: 10px;
        }
        .priority-high { background-color: #c73636; } /* 落ち着いた赤 */
        .priority-medium { background-color: #e69100; } /* 落ち着いたオレンジ */
        .priority-low { background-color: #367ac7; } /* 落ち着いた青 */

        /* --- Markdownの調整 --- */
        .stMarkdown p {
            line-height: 1.6;
        }
        .stMarkdown h3 {
            border-bottom: 2px solid #f0f2f6;
            padding-bottom: 0.3em;
            margin-top: 1.5em;
        }

        /* --- 画像キャプションを非表示に --- */
        .stImage > figcaption {
            display: none;
        }

        /* --- 印刷（PDF化）用のスタイル --- */
        @media print {
            /* 画面上部の操作UIを非表示 */
            .main > div:first-child {
                display: none !important;
            }
            /* レポートの余白や影を調整 */
            .report-container {
                box-shadow: none;
                border: 1px solid #ccc;
                padding: 1em 1.5em;
            }
            /* 改ページ制御 */
            .page-break {
                page-break-after: always;
            }
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
- "location": (string) 指摘箇所の具体的な場所（例：「リビング南側の壁紙」、「キッチンのシンク下収納扉」）。
- "current_state": (string) 現状の客観的な説明（例：「壁紙に幅約5cm、長さ約10cmの黒ずんだカビが発生している」、「扉の化粧シートが角から剥がれかけており、中の木材が露出している」）。
- "suggested_work": (string) 提案する工事内容（例：「防カビ剤による下地処理後、壁紙の部分的な張り替えを提案します」、「既存の化粧シートを剥がし、新しいダイノックシートを貼り付けます」）。
- "priority": (string) 工事の緊急度を「高」「中」「低」の3段階で評価してください。
- "notes": (string) クライアントへの補足事項やアドバイス（例：「カビの発生原因として、部屋の換気不足が考えられます。定期的な換気をおすすめします」）。
---
分析対象のファイルリスト:
{file_list_str}
---
それでは、以下の写真の分析を開始してください。
"""

def generate_report(model, uploaded_files, prompt):
    image_parts = [Part.from_data(f.getvalue(), mime_type=f.type) for f in uploaded_files]
    contents = [prompt] + image_parts
    response = model.generate_content(contents, request_options={"timeout": 600})
    return response.text

def parse_json_response(text):
    match = re.search(r'```(json)?\s*(.*?)\s*```', text, re.DOTALL)
    json_str = match.group(2) if match else text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        st.error("AIの応答をJSONとして解析できませんでした。")
        st.info("AIからの生の応答:")
        st.code(text, language="text")
        return None

def display_report(report_data, uploaded_files_dict, report_title, survey_date):
    """プロフェッショナルなデザインでレポートを表示する"""
    
    with st.container():
        st.markdown('<div class="report-container">', unsafe_allow_html=True)
        
        # 1. レポートヘッダー
        st.title("現場分析レポート")
        col1, col2 = st.columns(2)
        col1.markdown(f"**物件名・案件名:** {report_title if report_title else '（未設定）'}")
        col2.markdown(f"**調査日:** {survey_date}")
        st.markdown("---")

        # 2. サマリー
        total_findings = sum(len(item.get("findings", [])) for item in report_data)
        high_priority_count = sum(1 for item in report_data for finding in item.get("findings", []) if finding.get("priority") == "高")
        st.subheader("📊 分析結果サマリー")
        c1, c2, c3 = st.columns(3)
        c1.metric("分析写真枚数", f"{len(report_data)} 枚")
        c2.metric("総指摘件数", f"{total_findings} 件")
        c3.metric("緊急度「高」の件数", f"{high_priority_count} 件")
        
        # サマリーと詳細の間に改ページを挿入
        st.markdown('<div class="page-break"></div>', unsafe_allow_html=True)
        st.markdown("---")
        
        # 3. 個別分析
        st.subheader("📋 詳細分析結果")
        for i, report_item in enumerate(report_data):
            file_name = report_item.get("file_name")
            findings = report_item.get("findings", [])
            image_file = uploaded_files_dict.get(file_name)

            if not image_file: continue

            st.markdown(f"### **{i + 1}. 写真ファイル:** `{file_name}`")
            st.image(image_file, use_container_width=True)
            
            if not findings:
                st.success("✅ 特に修繕が必要な箇所は見つかりませんでした。")
            else:
                for j, finding in enumerate(findings, 1):
                    with st.container():
                        st.markdown('<div class="finding-card">', unsafe_allow_html=True)
                        
                        priority = finding.get('priority', 'N/A')
                        p_class = {"高": "high", "中": "medium", "低": "low"}.get(priority, "")
                        
                        st.markdown(f"""
                        <h5>指摘 {j}: {finding.get('location', 'N/A')}
                            <span class="priority-badge priority-{p_class}">緊急度: {priority}</span>
                        </h5>
                        """, unsafe_allow_html=True)
                        
                        st.markdown(f"**現状:** {finding.get('current_state', 'N/A')}")
                        st.markdown(f"**提案工事:** {finding.get('suggested_work', 'N/A')}")
                        if finding.get('notes'):
                            st.markdown(f"**備考:** {finding.get('notes', 'N/A')}")
                        
                        st.markdown('</div>', unsafe_allow_html=True)

            if i < len(report_data) - 1:
                st.markdown("<hr style='border:1px solid #e0e0e0; margin-top: 2.5em; margin-bottom: 1.5em;'>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------------------------------------------------
# 3. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    inject_custom_css()

    st.title("📷 AIリフォーム箇所分析＆報告書作成サービス")
    st.markdown("リフォームや原状回復が必要な現場の写真をアップロードすると、AIがクライアント向けの修繕提案レポートを自動作成します。")

    model = initialize_vertexai()
    if not model:
        st.warning("AIモデルを読み込めませんでした。管理者にお問い合わせください。")
        st.stop()
    
    with st.form("report_form"):
        st.subheader("1. レポート情報入力")
        report_title = st.text_input("物件名・案件名")
        survey_date = st.date_input("調査日", date.today())
        
        st.subheader("2. 写真アップロード")
        uploaded_files = st.file_uploader(
            "分析したい写真を選択してください（複数選択可）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        
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
                        st.rerun() # 結果表示のために再実行
                    else:
                        st.error("レポートデータの生成に失敗しました。")
                except Exception as e:
                    st.error(f"分析中に予期せぬエラーが発生しました: {e}")

    if 'report_data' in st.session_state:
        display_report(
            st.session_state.report_data,
            st.session_state.uploaded_files_dict,
            st.session_state.report_title,
            st.session_state.survey_date
        )
        st.info("💡 レポートをPDFとして保存するには、ブラウザの印刷機能（Ctrl+P または Cmd+P）を使い、「送信先」で「PDFとして保存」を選択してください。")

if __name__ == "__main__":
    main()
