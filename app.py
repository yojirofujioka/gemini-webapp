# -----------------------------------------------
# 1. 必要なライブラリを準備
# -----------------------------------------------
import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
from google.oauth2 import service_account

# -----------------------------------------------
# 2. ★★★ GCP認証と初期設定 ★★★
# -----------------------------------------------
try:
    # secrets.toml の [gcp] セクションをまるごと読み込む
    gcp_cfg = st.secrets["gcp"]
    GCP_PROJECT_ID = gcp_cfg["project_id"]
    GCP_REGION     = "asia-northeast1"

    # JSON文字列を辞書に戻す
    service_account_info = json.loads(gcp_cfg["gcp_service_account"])

    # 認証情報オブジェクトを作成
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )

    # Vertex AI 初期化
    vertexai.init(
        project   = GCP_PROJECT_ID,
        location  = GCP_REGION,
        credentials = credentials
    )
    model = GenerativeModel("gemini-1.5-pro-latest")

    GCP_AUTH_SUCCESS = True

except Exception as e:
    GCP_AUTH_SUCCESS = False
    st.error(f"GCPの認証に失敗しました。\nStreamlitのSecrets設定を確認してください。\nエラー: {e}")

# -----------------------------------------------
# 3. UI 部分
# -----------------------------------------------
st.title("📷 AIによるリフォーム箇所分析アプリ")
st.markdown("""
360度写真や、気になる箇所の詳細な写真をアップロードしてください。  
AIが写真を分析し、リフォームや修繕が必要な箇所を自動でリストアップします。
""")

uploaded = st.file_uploader(
    "分析したい写真を選択してください（複数選択可）",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

prompt = """
以下の全ての写真について、
1. これは何の写真か（場所・設備など）  
2. リフォーム・修繕が必要な箇所があれば指摘  

の２点をファイル名ごとにリスト形式でまとめてください。
"""

# -----------------------------------------------
# 4. 分析ボタン押下時の処理
# -----------------------------------------------
if st.button("分析を開始する"):
    if not GCP_AUTH_SUCCESS:
        # 認証エラーは上部で表示済み
        st.stop()

    if not uploaded:
        st.warning("まずはファイルをアップロードしてください。")
        st.stop()

    with st.spinner("AIが写真を分析中です…"):
        try:
            parts = [
                Part.from_data(data=f.getvalue(), mime_type=f.type)
                for f in uploaded
            ]
            contents = [prompt] + parts
            res = model.generate_content(contents, request_options={"timeout":1800})

            st.subheader("🔍 分析結果")
            st.markdown(res.text)
            st.success("✅ 分析が完了しました！")

        except Exception as e:
            st.error(f"分析中にエラーが発生しました: {e}")
