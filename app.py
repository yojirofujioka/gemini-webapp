import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account

# ----------------------------------------------------------------------
# 1. 設定と定数
# ----------------------------------------------------------------------
# Streamlitページの基本的な設定
st.set_page_config(
    page_title="AIリフォーム箇所分析レポート",
    page_icon="🏠",
    layout="wide"
)

# GCP関連の定数
try:
    GCP_SECRETS = st.secrets["gcp"]
    GCP_PROJECT_ID = GCP_SECRETS["project_id"]
    GCP_REGION = "asia-northeast1"
    MODEL_NAME = "gemini-1.5-pro"  # ご指定のモデル名に変更
    SERVICE_ACCOUNT_INFO = json.loads(GCP_SECRETS["gcp_service_account"])
except Exception as e:
    st.error(f"StreamlitのSecrets設定の読み込みに失敗しました。`[gcp]`セクションと`project_id`, `gcp_service_account`を確認してください。エラー: {e}")
    st.stop()


# ----------------------------------------------------------------------
# 2. 補助関数（機能を部品化）
# ----------------------------------------------------------------------

@st.cache_resource
def initialize_vertexai():
    """
    GCPサービスアカウント情報を使ってVertex AIを初期化し、生成モデルを返す。
    成功した場合はモデルオブジェクトを、失敗した場合はNoneを返す。
    st.cache_resourceにより、一度初期化したら再実行しない。
    """
    try:
        credentials = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO)
        vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION, credentials=credentials)
        model = GenerativeModel(MODEL_NAME)
        return model
    except Exception as e:
        st.error(f"GCPの認証またはVertex AIの初期化に失敗しました。エラー: {e}")
        return None

def create_report_prompt(filenames):
    """
    AIに渡すための詳細なプロンプトを生成する。
    JSON形式での出力を厳密に指示する。
    """
    file_list_str = "\n".join([f"- {name}" for name in filenames])

    return f"""
あなたは、日本のリフォーム・原状回復工事を専門とする、経験豊富な現場監督です。
あなたの仕事は、提供された現場写真を分析し、クライアントに提出するための、丁寧で分かりやすい修繕提案レポートを作成することです。

以下の写真（ファイル名と共に提示）を一枚ずつ詳細に確認し、修繕や交換が必要と思われる箇所をすべて特定してください。
特定した各箇所について、以下のJSON形式で報告書を作成してください。

**最重要**:
あなたの出力は、純粋なJSON文字列のみでなければなりません。
説明文や ```json ... ``` のようなマークダウンは絶対に含めないでください。

**JSONの構造**:
出力は、JSONオブジェクトのリスト形式 `[ ... ]` としてください。各オブジェクトは1枚の写真に対応します。

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
    """
    画像とプロンプトをVertex AIに送信し、分析レポートを生成する。
    """
    image_parts = [Part.from_data(f.getvalue(), mime_type=f.type) for f in uploaded_files]
    contents = [prompt] + image_parts
    response = model.generate_content(contents)
    return response.text

def parse_json_response(text):
    """
    AIからのテキスト応答をパースしてPythonの辞書オブジェクトに変換する。
    応答にありがちなマークダウンの```json ...```を先に除去する。
    """
    match = re.search(r'```(json)?\s*(.*?)\s*```', text, re.DOTALL)
    json_str = match.group(2) if match else text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        st.error("AIの応答をJSONとして解析できませんでした。")
        st.info("AIからの生の応答:")
        st.code(text, language="text")
        return None

def display_report(report_data, uploaded_files_dict):
    """
    解析されたレポートデータを、PDF化に適した一枚のレポート形式で表示する。
    """
    # 1. レポート全体のサマリーを表示
    total_findings = sum(len(item.get("findings", [])) for item in report_data)
    high_priority_count = sum(
        1 for item in report_data 
        for finding in item.get("findings", []) 
        if finding.get("priority") == "高"
    )

    st.header("【現場分析レポート】")
    st.markdown("---")
    st.subheader("📊 分析結果サマリー")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("分析写真枚数", f"{len(report_data)} 枚")
    col2.metric("総指摘件数", f"{total_findings} 件")
    col3.metric("緊急度「高」の件数", f"{high_priority_count} 件")
    
    st.markdown("---")

    # 2. 個別の詳細レポートを順に表示
    st.subheader("📋 個別分析レポート")

    for i, report_item in enumerate(report_data):
        file_name = report_item.get("file_name")
        findings = report_item.get("findings", [])
        image_file = uploaded_files_dict.get(file_name)

        if not image_file:
            st.warning(f"レポート内のファイル名 `{file_name}` に一致するファイルが見つかりません。")
            continue

        st.markdown(f"### **{i + 1}. 写真ファイル: `{file_name}`**")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            # 警告が出ないように use_container_width=True に変更
            st.image(image_file, caption=f"分析対象: {file_name}", use_container_width=True)

        with col2:
            if not findings:
                st.success("✅ 特に修繕が必要な箇所は見つかりませんでした。")
            else:
                for j, finding in enumerate(findings, 1):
                    st.markdown(f"**指摘 {j}: {finding.get('location', 'N/A')}**")
                    
                    priority = finding.get('priority', 'N/A')
                    if priority == "高":
                        st.error(f"**緊急度:** {priority}")
                    elif priority == "中":
                        st.warning(f"**緊急度:** {priority}")
                    else:
                        st.info(f"**緊急度:** {priority}")
                    
                    st.markdown(f"- **現状:** {finding.get('current_state', 'N/A')}")
                    st.markdown(f"- **提案工事:** {finding.get('suggested_work', 'N/A')}")
                    if finding.get('notes'):
                        st.markdown(f"- **備考:** {finding.get('notes', 'N/A')}")
                    
                    if j < len(findings):
                        st.markdown("---")
        
        # 各写真レポートの区切り線
        st.markdown("<hr style='border:2px solid #ddd'>", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 3. メインアプリケーション
# ----------------------------------------------------------------------
def main():
    st.title("📷 AIリフォーム箇所分析＆報告書作成サービス")
    st.markdown("""
    リフォームや原状回復が必要な現場の写真をアップロードしてください。  
    AIが写真を詳細に分析し、クライアント向けの修繕提案レポートを項目ごとに作成します。
    """)

    model = initialize_vertexai()
    if not model:
        st.warning("AIモデルを読み込めませんでした。管理者にお問い合わせください。")
        st.stop()

    uploaded_files = st.file_uploader(
        "分析したい写真を選択してください（複数選択可）",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    if not uploaded_files:
        st.info("分析を開始するには、まず写真をアップロードしてください。")
        st.stop()

    if st.button("レポートを作成する", type="primary", use_container_width=True):
        with st.spinner("AIが写真を分析し、レポートを作成中です…"):
            try:
                filenames = [f.name for f in uploaded_files]
                prompt = create_report_prompt(filenames)
                response_text = generate_report(model, uploaded_files, prompt)
                report_data = parse_json_response(response_text)
                
                if report_data:
                    # セッションステートに結果を保存
                    st.session_state.report_data = report_data
                    st.session_state.uploaded_files_dict = {f.name: f for f in uploaded_files}
                    st.success("✅ レポートの作成が完了しました！下にスクロールして結果をご確認ください。")
                else:
                    st.error("レポートデータの生成に失敗しました。")

            except Exception as e:
                st.error(f"分析中に予期せぬエラーが発生しました: {e}")

    # セッションステートにレポートデータがあれば表示する
    if 'report_data' in st.session_state:
        display_report(st.session_state.report_data, st.session_state.uploaded_files_dict)
        st.info("💡 レポートをPDFとして保存するには、ブラウザの印刷機能（Ctrl+P または Cmd+P）を使い、「送信先」で「PDFとして保存」を選択してください。")


if __name__ == "__main__":
    main()
