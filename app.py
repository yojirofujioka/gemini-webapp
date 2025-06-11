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
    # .streamlit/secrets.toml の [gcp] セクションを読み込む
    gcp_cfg = st.secrets["gcp"]
    GCP_PROJECT_ID = gcp_cfg["project_id"]
    GCP_REGION     = "asia-northeast1"

    # JSON文字列を辞書化
    service_account_info = json.loads(gcp_cfg["gcp_service_account"])

    # 認証用オブジェクトを作成
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )

    # Vertex AI 初期化
    vertexai.init(
        project     = GCP_PROJECT_ID,
        location    = GCP_REGION,
        credentials = credentials
    )
    model = GenerativeModel("gemini-2.5-pro-preview-latest")

    GCP_AUTH_SUCCESS = True

except Exception as e:
    GCP_AUTH_SUCCESS = False
    st.error(f"GCPの認証に失敗しました。\nStreamlitのSecrets設定を確認してください。\nエラー: {e}")

# -----------------------------------------------
# 3. UI（画面）部分
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
# 4. 分析開始ボタン押下時の処理
# -----------------------------------------------
if st.button("分析を開始する"):
    if not GCP_AUTH_SUCCESS:
        st.stop()  # 認証エラーは上部で報告済み

    if not uploaded:
        st.warning("まずはファイルをアップロードしてください。")
        st.stop()

    with st.spinner("AIが写真を分析中です…"):
        try:
            # 画像データを Part オブジェクトに変換
            parts = [
                Part.from_data(data=f.getvalue(), mime_type=f.type)
                for f in uploaded
            ]

            # ここで request_options を外しています
            contents = [prompt] + parts
            response = model.generate_content(contents)

            st.subheader("🔍 分析結果")
            st.markdown(response.text)
            st.success("✅ 分析が完了しました！")

        except Exception as e:
            st.error(f"分析中にエラーが発生しました: {e}")
